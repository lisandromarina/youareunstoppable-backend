import enum
import calendar
from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from src.core.security import utcnow
from src.domain.catalog import (
    CatalogDirection,
    CatalogIdentity,
    find_direction,
    find_identity,
)
from src.models.transformation import (
    CommitmentStatus,
    Day,
    DayCommitment,
    DayStatus,
    Origin,
    PathPhase,
    PlannedCommitment,
    PlannedImplementation,
    Transformation,
    TransformationPath,
)
from src.models.user import User
from src.schemas.transformation import (
    CommitmentResponse,
    ImplementationResponse,
    PhaseResponse,
    ProgressResponse,
    SelectionRequest,
    SelectionResponse,
    TodayGroupResponse,
    TodayResponse,
    TomorrowItemResponse,
    TransformationResponse,
    UpcomingResponse,
    YearDayResponse,
    YearIdentityResponse,
)
from src.services.errors import DomainError


PROGRESS_DAYS_TO_GAIN = 3
MISS_DAYS_TO_LOSE = 2


def read_transformation(db: Session, user: User, on: date) -> TransformationResponse:
    _check_date(on)
    transformation = _load(db, user.id)
    if transformation is None:
        raise DomainError(404, "Transformation has not started.")
    _ensure_today(db, transformation, on)
    return _finish(db, user.id, on)


def start_transformation(
    db: Session,
    user: User,
    on: date,
    selections: list[SelectionRequest],
) -> TransformationResponse:
    _check_date(on)
    if _load(db, user.id) is not None:
        raise DomainError(409, "A transformation has already started.")
    resolved = _resolve(selections)
    transformation = Transformation(
        user_id=user.id,
        started_on=on,
        origin=Origin.catalog,
    )
    for index, (identity, direction) in enumerate(resolved):
        transformation.paths.append(_copy_path(identity, direction, index))
    db.add(transformation)
    db.flush()
    _ensure_today(db, transformation, on)
    return _finish(db, user.id, on)


def update_transformation(
    db: Session,
    user: User,
    on: date,
    selections: list[SelectionRequest],
) -> TransformationResponse:
    _check_date(on)
    transformation = _load(db, user.id)
    if transformation is None:
        raise DomainError(404, "Transformation has not started.")
    resolved = _resolve(selections)
    day = _find_day(transformation, on)
    if day is not None and _status(day.status) == DayStatus.open.value:
        _clear_commitments(day)
        db.flush()

    incoming = {identity.id: direction.id for identity, direction in resolved}
    for path in list(transformation.paths):
        direction_id = incoming.get(path.identity_id)
        if direction_id != path.direction_id:
            _drop_path(db, transformation, path)
    db.flush()

    for index, (identity, direction) in enumerate(resolved):
        current = _path_for(transformation, identity.id)
        if current is not None:
            current.sort_order = index
            continue
        transformation.paths.append(_copy_path(identity, direction, index))
    db.flush()

    if _status(transformation.origin) == Origin.adaptive.value and not any(
        _path_is_adaptive(transformation, path) for path in transformation.paths
    ):
        transformation.origin = Origin.catalog
    if day is not None and _status(day.status) == DayStatus.open.value:
        _schedule(day, transformation)
    return _finish(db, user.id, on)


def reset_transformation(db: Session, user: User) -> None:
    transformation = db.scalar(select(Transformation.id).where(Transformation.user_id == user.id))
    if transformation is None:
        return
    transformation_id = transformation
    day_ids = list(
        db.scalars(select(Day.id).where(Day.transformation_id == transformation_id)).all()
    )
    if day_ids:
        db.execute(delete(DayCommitment).where(DayCommitment.day_id.in_(day_ids)))
        db.execute(delete(Day).where(Day.id.in_(day_ids)))
    path_ids = list(
        db.scalars(
            select(TransformationPath.id).where(
                TransformationPath.transformation_id == transformation_id
            )
        ).all()
    )
    if path_ids:
        phase_ids = list(
            db.scalars(select(PathPhase.id).where(PathPhase.path_id.in_(path_ids))).all()
        )
        if phase_ids:
            commitment_ids = list(
                db.scalars(
                    select(PlannedCommitment.id).where(PlannedCommitment.phase_id.in_(phase_ids))
                ).all()
            )
            if commitment_ids:
                db.execute(
                    delete(PlannedImplementation).where(
                        PlannedImplementation.commitment_id.in_(commitment_ids)
                    )
                )
                db.execute(delete(PlannedCommitment).where(PlannedCommitment.id.in_(commitment_ids)))
            db.execute(delete(PathPhase).where(PathPhase.id.in_(phase_ids)))
        db.execute(delete(TransformationPath).where(TransformationPath.id.in_(path_ids)))
    db.execute(delete(Transformation).where(Transformation.id == transformation_id))
    db.commit()


def toggle_commitment(
    db: Session,
    user: User,
    on: date,
    commitment_id: UUID,
) -> TransformationResponse:
    transformation, day, commitment = _open_commitment(db, user, on, commitment_id)
    status = _status(commitment.status)
    if status == CommitmentStatus.done.value:
        commitment.status = CommitmentStatus.open
    else:
        commitment.status = CommitmentStatus.done
    return _finish(db, transformation.user_id, on)


def replace_commitment(
    db: Session,
    user: User,
    on: date,
    commitment_id: UUID,
    implementation_id: UUID,
) -> TransformationResponse:
    transformation, _day, commitment = _open_commitment(db, user, on, commitment_id)
    if commitment.planned is None:
        raise DomainError(404, "Commitment was not found.")
    chosen = next(
        (item for item in commitment.planned.implementations if item.id == implementation_id),
        None,
    )
    if chosen is None:
        raise DomainError(422, "That is not a way to complete this commitment.")
    commitment.implementation_id = chosen.id
    commitment.title_snapshot = chosen.title
    return _finish(db, transformation.user_id, on)


def skip_commitment(
    db: Session,
    user: User,
    on: date,
    commitment_id: UUID,
) -> TransformationResponse:
    transformation, _day, commitment = _open_commitment(db, user, on, commitment_id)
    commitment.status = CommitmentStatus.skipped
    return _finish(db, transformation.user_id, on)


def showed_up(db: Session, user: User, on: date) -> TransformationResponse:
    _check_date(on)
    transformation = _load(db, user.id)
    if transformation is None:
        raise DomainError(404, "Transformation has not started.")
    day = _ensure_today(db, transformation, on)
    if _status(day.status) == DayStatus.closed.value:
        raise DomainError(409, "This day is already closed.")
    if any(_status(item.status) == CommitmentStatus.open.value for item in day.commitments):
        raise DomainError(409, "Finish or skip every commitment first.")
    day.status = DayStatus.closed
    day.closed_at = utcnow()
    for path in transformation.paths:
        _advance(path, day)
    return _finish(db, user.id, on)


def set_schedule(
    db: Session,
    user: User,
    on: date,
    planned_id: UUID,
    weekdays: list[int] | None,
    month_day: int | None,
) -> TransformationResponse:
    _check_date(on)
    transformation = _load(db, user.id)
    if transformation is None:
        raise DomainError(404, "Transformation has not started.")
    planned, path = _find_planned(transformation, planned_id)
    if planned is None or path is None:
        raise DomainError(404, "Commitment was not found.")
    _apply_schedule(planned, weekdays, month_day)
    day = _find_day(transformation, on)
    if day is not None and _status(day.status) == DayStatus.open.value:
        _sync_occurrence(day, transformation, path, planned)
    return _finish(db, user.id, on)


def _open_commitment(
    db: Session,
    user: User,
    on: date,
    commitment_id: UUID,
) -> tuple[Transformation, Day, DayCommitment]:
    _check_date(on)
    transformation = _load(db, user.id)
    if transformation is None:
        raise DomainError(404, "Transformation has not started.")
    day = _ensure_today(db, transformation, on)
    commitment = next((item for item in day.commitments if item.id == commitment_id), None)
    if commitment is None:
        raise DomainError(404, "Commitment was not found.")
    if _status(day.status) == DayStatus.closed.value:
        raise DomainError(409, "This day is already closed.")
    return transformation, day, commitment


def _finish(db: Session, user_id: UUID, on: date) -> TransformationResponse:
    db.commit()
    transformation = _load(db, user_id)
    if transformation is None:
        raise DomainError(404, "Transformation has not started.")
    return _present(transformation, on)


def _resolve(
    selections: list[SelectionRequest],
) -> list[tuple[CatalogIdentity, CatalogDirection]]:
    if len(selections) > 2:
        raise DomainError(422, "Choose at most two identities.")
    resolved: list[tuple[CatalogIdentity, CatalogDirection]] = []
    seen: set[str] = set()
    for selection in selections:
        if selection.identity_id in seen:
            raise DomainError(422, "Each identity can be chosen once.")
        seen.add(selection.identity_id)
        identity = find_identity(selection.identity_id)
        if identity is None:
            raise DomainError(422, "Unknown identity.")
        direction = find_direction(identity, selection.direction_id)
        if direction is None:
            raise DomainError(422, "That direction is not part of this identity.")
        resolved.append((identity, direction))
    return resolved


def _copy_path(
    identity: CatalogIdentity,
    direction: CatalogDirection,
    sort_order: int,
) -> TransformationPath:
    path = TransformationPath(
        identity_id=identity.id,
        direction_id=direction.id,
        sort_order=sort_order,
        current_phase_position=0,
        day_in_phase=1,
        commitment_streak=0,
        completed=False,
    )
    for index, phase in enumerate(direction.phases):
        row = PathPhase(
            position=index,
            name=phase.name,
            headline=phase.headline,
            length_days=phase.length_days,
            catalog_phase_id=phase.id,
        )
        for commitment_index, commitment in enumerate(phase.commitments):
            planned = PlannedCommitment(
                position=commitment_index,
                unlock_streak=commitment.unlock_streak,
                objective=commitment.objective,
                catalog_commitment_id=commitment.id,
                recurrence=commitment.recurrence,
                times_per_week=commitment.times_per_week,
                weekdays=list(commitment.weekdays),
                month_day=commitment.month_day,
            )
            for implementation_index, implementation in enumerate(commitment.implementations):
                planned.implementations.append(
                    PlannedImplementation(
                        position=implementation_index,
                        title=implementation.title,
                        is_default=implementation_index == 0,
                    )
                )
            row.commitments.append(planned)
        path.phases.append(row)
    return path


def _ensure_today(db: Session, transformation: Transformation, on: date) -> Day:
    existing = _find_day(transformation, on)
    if existing is not None:
        if _status(existing.status) == DayStatus.open.value:
            _reconcile_open_day(existing, transformation)
        return existing
    _reset_unlock_if_gap(transformation, on)
    day = Day(calendar_date=on, status=DayStatus.open)
    transformation.days.append(day)
    _schedule(day, transformation)
    db.flush()
    return day


def _schedule(day: Day, transformation: Transformation) -> None:
    on = _as_date(day.calendar_date)
    existing = {item.planned_commitment_id for item in day.commitments}
    for path, planned, title in _due_pairs(transformation, on, materialize=True):
        if planned.id in existing:
            _apply_title_override(day, planned.id, title)
            continue
        _append_occurrence(day, path, planned, title)


def _append_occurrence(
    day: Day,
    path: TransformationPath,
    planned: PlannedCommitment,
    title: str | None = None,
) -> None:
    chosen = _default_implementation(planned)
    day.commitments.append(
        DayCommitment(
            path=path,
            planned=planned,
            implementation=chosen,
            status=CommitmentStatus.open,
            objective_snapshot=planned.objective,
            title_snapshot=title or chosen.title,
        )
    )


def _apply_title_override(day: Day, planned_id: UUID, title: str | None) -> None:
    if not title:
        return
    for item in day.commitments:
        if item.planned_commitment_id == planned_id and _status(item.status) == CommitmentStatus.open.value:
            item.title_snapshot = title


def _ordered_commitments(path: TransformationPath) -> list[PlannedCommitment]:
    rows: list[PlannedCommitment] = []
    for phase in sorted(path.phases, key=lambda item: item.position):
        rows.extend(sorted(phase.commitments, key=lambda item: item.position))
    return rows


def _made_progress(path: TransformationPath, transformation: Transformation, on: date) -> bool:
    day = _find_day(transformation, on)
    if day is None:
        return False
    return any(
        item.path_id == path.id and _status(item.status) == CommitmentStatus.done.value
        for item in day.commitments
    )


def _active_limit(path: TransformationPath, transformation: Transformation, on: date) -> int:
    ordered = _ordered_commitments(path)
    if not ordered:
        raise DomainError(500, "This path has no commitment.")
    active = 1
    progress_run = 0
    miss_run = 0
    day = _as_date(transformation.started_on)
    while day < on:
        if _made_progress(path, transformation, day):
            miss_run = 0
            progress_run += 1
            if progress_run >= PROGRESS_DAYS_TO_GAIN:
                if active < len(ordered):
                    active += 1
                progress_run = 0
        else:
            progress_run = 0
            miss_run += 1
            if miss_run >= MISS_DAYS_TO_LOSE:
                active = max(1, active - 1)
                miss_run = 0
        day += timedelta(days=1)
    return active


def _active_commitments(
    path: TransformationPath,
    transformation: Transformation,
    on: date,
) -> list[PlannedCommitment]:
    return _ordered_commitments(path)[: _active_limit(path, transformation, on)]


def _due_commitments(
    path: TransformationPath,
    transformation: Transformation,
    on: date,
) -> list[PlannedCommitment]:
    return [item for item in _active_commitments(path, transformation, on) if _is_due(on, item)]


_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _weekdays(planned: PlannedCommitment) -> set[int]:
    return {int(item) for item in (planned.weekdays or [])}


def _is_due(on: date, planned: PlannedCommitment) -> bool:
    if planned.recurrence == "once":
        return planned.due_on is not None and _as_date(planned.due_on) == on
    if planned.recurrence == "daily":
        return True
    if planned.recurrence in {"weekly", "times_per_week"}:
        return on.weekday() in _weekdays(planned)
    if planned.recurrence == "monthly":
        scheduled = planned.month_day or 1
        last = calendar.monthrange(on.year, on.month)[1]
        return on.day == min(scheduled, last)
    return False


def _cadence(planned: PlannedCommitment) -> str:
    if planned.recurrence == "once":
        return "Once"
    if planned.recurrence == "daily":
        return "Daily"
    if planned.recurrence == "weekly":
        return "Weekly"
    if planned.recurrence == "monthly":
        return "Monthly"
    count = planned.times_per_week or len(_weekdays(planned))
    if count == 1:
        return "Weekly"
    return f"{count} times per week"


def _when(planned: PlannedCommitment) -> str:
    if planned.recurrence == "once" and planned.due_on is not None:
        due = _as_date(planned.due_on)
        return f"{due.strftime('%b')} {due.day}"
    if planned.recurrence == "monthly":
        return f"Day {planned.month_day or 1}"
    names = [_WEEKDAYS[day] for day in sorted(_weekdays(planned)) if 0 <= day <= 6]
    return ", ".join(names)


def _path_is_adaptive(transformation: Transformation, path: TransformationPath) -> bool:
    if _status(transformation.origin) != Origin.adaptive.value:
        return False
    phase = _phase_at(path, path.current_phase_position)
    if phase is None or not phase.commitments:
        return False
    return all(item.catalog_commitment_id is None for item in phase.commitments)


def _current_commitments(path: TransformationPath) -> list[PlannedCommitment]:
    phase = _phase_at(path, path.current_phase_position)
    if phase is None:
        return []
    return sorted(phase.commitments, key=lambda item: item.position)


def _once_settled(transformation: Transformation, planned_id: UUID) -> bool:
    for day in transformation.days:
        if _status(day.status) != DayStatus.closed.value:
            continue
        for item in day.commitments:
            if item.planned_commitment_id != planned_id:
                continue
            if _status(item.status) in {CommitmentStatus.done.value, CommitmentStatus.skipped.value}:
                return True
    return False


def _once_eligible(
    transformation: Transformation,
    planned: PlannedCommitment,
    on: date,
    *,
    include_overdue: bool,
) -> bool:
    if planned.due_on is None or _once_settled(transformation, planned.id):
        return False
    due = _as_date(planned.due_on)
    if due == on:
        return True
    return include_overdue and due < on


def _today_override(transformation: Transformation, on: date) -> list[dict] | None:
    context = transformation.context if isinstance(transformation.context, dict) else None
    if context is None:
        return None
    raw = context.get("today_override")
    if not isinstance(raw, dict) or raw.get("on") != on.isoformat():
        return None
    goals = raw.get("goals")
    if not isinstance(goals, list) or not goals:
        return None
    return [item for item in goals if isinstance(item, dict)][:5]


def _preview_streak(path: TransformationPath, transformation: Transformation, today: date) -> int:
    day = _find_day(transformation, today)
    if day is None or _status(day.status) == DayStatus.closed.value:
        return path.commitment_streak
    own = [item for item in day.commitments if item.path_id == path.id]
    if any(_status(item.status) == CommitmentStatus.done.value for item in own):
        return path.commitment_streak + 1
    return path.commitment_streak


def _slide_once(eligible: list[PlannedCommitment], chosen_ids: set[UUID], on: date) -> None:
    nxt = on + timedelta(days=1)
    seen: set[UUID] = set()
    for planned in eligible:
        if planned.id in seen:
            continue
        seen.add(planned.id)
        planned.due_on = on if planned.id in chosen_ids else nxt


def _override_pairs(
    transformation: Transformation,
    goals: list[dict],
) -> list[tuple[TransformationPath, PlannedCommitment, str | None]]:
    rows: list[tuple[TransformationPath, PlannedCommitment, str | None]] = []
    for goal in goals[:5]:
        raw_id = goal.get("planned_commitment_id")
        if not isinstance(raw_id, str):
            continue
        try:
            planned_id = UUID(raw_id)
        except ValueError:
            continue
        planned, path = _find_planned(transformation, planned_id)
        if planned is None or path is None:
            continue
        title = goal.get("title")
        rows.append((path, planned, title.strip() if isinstance(title, str) and title.strip() else None))
    return rows


def _adaptive_selected(
    transformation: Transformation,
    paths: list[TransformationPath],
    on: date,
    streaks: dict[UUID, int],
    *,
    materialize: bool,
) -> list[tuple[TransformationPath, PlannedCommitment, str | None]]:
    override = _today_override(transformation, on)
    if override is not None:
        return _override_pairs(transformation, override)

    quicks: list[tuple[TransformationPath, PlannedCommitment]] = []
    onces: list[tuple[TransformationPath, PlannedCommitment]] = []
    rest: list[tuple[TransformationPath, PlannedCommitment]] = []
    eligible_once: list[PlannedCommitment] = []
    for path in paths:
        ordered = _current_commitments(path)
        if not ordered:
            continue
        prefix = min(5, max(0, streaks.get(path.id, 0)) + 1)
        repeating = [item for item in ordered if item.recurrence != "once" and _is_due(on, item)]
        shown = repeating[:prefix]
        once = [
            item
            for item in ordered
            if item.recurrence == "once"
            and _once_eligible(transformation, item, on, include_overdue=materialize)
        ]
        eligible_once.extend(once)
        shown_ids = {item.id for item in shown}
        once_ids = {item.id for item in once}
        quick = next((item for item in ordered if item.id in shown_ids or item.id in once_ids), None)
        if quick is not None:
            quicks.append((path, quick))
        for item in once:
            if quick is None or item.id != quick.id:
                onces.append((path, item))
        for item in shown:
            if quick is None or item.id != quick.id:
                rest.append((path, item))
    chosen = (quicks + onces + rest)[:5]
    if materialize:
        _slide_once(eligible_once, {planned.id for _, planned in chosen}, on)
    return [(path, planned, None) for path, planned in chosen]


def _due_pairs(
    transformation: Transformation,
    on: date,
    *,
    materialize: bool,
    preview_from: date | None = None,
) -> list[tuple[TransformationPath, PlannedCommitment, str | None]]:
    override = _today_override(transformation, on)
    if override is not None:
        return _override_pairs(transformation, override)
    paths = sorted(transformation.paths, key=lambda item: item.sort_order)
    pairs: list[tuple[TransformationPath, PlannedCommitment, str | None]] = []
    adaptive: list[TransformationPath] = []
    for path in paths:
        if _path_is_adaptive(transformation, path):
            adaptive.append(path)
            continue
        for planned in _due_commitments(path, transformation, on):
            pairs.append((path, planned, None))
    if not adaptive:
        return pairs
    streaks = {
        path.id: (
            _preview_streak(path, transformation, preview_from)
            if preview_from is not None
            else path.commitment_streak
        )
        for path in adaptive
    }
    pairs.extend(_adaptive_selected(transformation, adaptive, on, streaks, materialize=materialize))
    return pairs


def _coming_up(
    day: Day,
    transformation: Transformation,
    paths: list[TransformationPath],
) -> list[UpcomingResponse]:
    on = _as_date(day.calendar_date)
    present = {item.planned_commitment_id for item in day.commitments}
    rows: list[UpcomingResponse] = []
    for path in paths:
        if _path_is_adaptive(transformation, path):
            continue
        identity = find_identity(path.identity_id)
        identity_name = identity.name if identity is not None else path.identity_id
        for planned in _active_commitments(path, transformation, on):
            if planned.id in present or _is_due(on, planned):
                continue
            rows.append(_upcoming(path, planned, identity_name))
    if any(_path_is_adaptive(transformation, path) for path in paths):
        target = on + timedelta(days=1)
        for path, planned, _title in _due_pairs(transformation, target, materialize=False, preview_from=on):
            if not _path_is_adaptive(transformation, path) or planned.id in present:
                continue
            identity = find_identity(path.identity_id)
            identity_name = identity.name if identity is not None else path.identity_id
            rows.append(_upcoming(path, planned, identity_name))
    return rows


def _upcoming(path: TransformationPath, planned: PlannedCommitment, identity_name: str) -> UpcomingResponse:
    del path
    chosen = _default_implementation(planned)
    return UpcomingResponse(
        planned_commitment_id=planned.id,
        identity_name=identity_name,
        objective=planned.objective,
        title=chosen.title,
        cadence=_cadence(planned),
        recurrence=planned.recurrence,  # type: ignore[arg-type]
        times_per_week=planned.times_per_week,
        weekdays=sorted(_weekdays(planned)),
        month_day=planned.month_day,
        due_on=_as_date(planned.due_on) if planned.due_on is not None else None,
        when=_when(planned),
    )


def _find_planned(
    transformation: Transformation,
    planned_id: UUID,
) -> tuple[PlannedCommitment | None, TransformationPath | None]:
    for path in transformation.paths:
        for phase in path.phases:
            for planned in phase.commitments:
                if planned.id == planned_id:
                    return planned, path
    return None, None


def _apply_schedule(
    planned: PlannedCommitment,
    weekdays: list[int] | None,
    month_day: int | None,
) -> None:
    if planned.recurrence == "once":
        raise DomainError(422, "This commitment happens once.")
    if planned.recurrence == "daily":
        raise DomainError(422, "This commitment is due every day.")
    if planned.recurrence == "monthly":
        if month_day is None or month_day < 1 or month_day > 28:
            raise DomainError(422, "Choose a day from 1 to 28.")
        planned.month_day = month_day
        return
    if weekdays is None:
        raise DomainError(422, "Choose the days for this commitment.")
    chosen = sorted(set(weekdays))
    if any(day < 0 or day > 6 for day in chosen):
        raise DomainError(422, "Choose the days for this commitment.")
    expected = 1 if planned.recurrence == "weekly" else planned.times_per_week
    if expected is None or len(chosen) != expected:
        count = expected or 0
        noun = "day" if count == 1 else "days"
        raise DomainError(422, f"Select exactly {count} {noun}.")
    planned.weekdays = chosen


def _reconcile_open_day(day: Day, transformation: Transformation) -> None:
    on = _as_date(day.calendar_date)
    due = _due_pairs(transformation, on, materialize=True)
    due_ids = {planned.id for _, planned, _title in due}
    for path, planned, title in due:
        if not any(item.planned_commitment_id == planned.id for item in day.commitments):
            _append_occurrence(day, path, planned, title)
        else:
            _apply_title_override(day, planned.id, title)
    for item in list(day.commitments):
        if item.planned_commitment_id not in due_ids and _status(item.status) == CommitmentStatus.open.value:
            day.commitments.remove(item)


def _sync_occurrence(
    day: Day,
    transformation: Transformation,
    path: TransformationPath,
    planned: PlannedCommitment,
) -> None:
    on = _as_date(day.calendar_date)
    existing = [item for item in day.commitments if item.planned_commitment_id == planned.id]
    due_ids = {item.id for _path, item, _title in _due_pairs(transformation, on, materialize=True)}
    if planned.id in due_ids:
        if not existing:
            _append_occurrence(day, path, planned)
        return
    for item in existing:
        if _status(item.status) == CommitmentStatus.open.value:
            day.commitments.remove(item)


def _advance(path: TransformationPath, day: Day) -> None:
    own = [item for item in day.commitments if item.path_id == path.id]
    if own:
        succeeded = any(_status(item.status) == CommitmentStatus.done.value for item in own)
        if succeeded:
            path.commitment_streak += 1
        else:
            path.commitment_streak = 0
    if path.completed:
        return
    phase = _phase_at(path, path.current_phase_position)
    if phase is None:
        raise DomainError(500, "The current phase is missing.")
    if path.day_in_phase < phase.length_days:
        path.day_in_phase += 1
        return
    if _phase_at(path, path.current_phase_position + 1) is None:
        path.completed = True
        return
    path.current_phase_position += 1
    path.day_in_phase = 1


def _reset_unlock_if_gap(transformation: Transformation, on: date) -> None:
    closed = [
        _as_date(day.calendar_date)
        for day in transformation.days
        if _status(day.status) == DayStatus.closed.value
    ]
    if not closed:
        return
    if max(closed) < on - timedelta(days=1):
        for path in transformation.paths:
            path.commitment_streak = 0


def _drop_path(db: Session, transformation: Transformation, path: TransformationPath) -> None:
    linked = db.scalars(select(DayCommitment).where(DayCommitment.path_id == path.id)).all()
    for row in linked:
        row.path = None
        row.planned = None
        row.implementation = None
    db.flush()
    transformation.paths.remove(path)


def _clear_commitments(day: Day) -> None:
    for row in list(day.commitments):
        day.commitments.remove(row)


def _present(transformation: Transformation, on: date) -> TransformationResponse:
    paths = sorted(transformation.paths, key=lambda item: item.sort_order)
    day = _find_day(transformation, on)
    if day is None:
        raise DomainError(500, "Today is missing.")
    names = [_identity_name(path.identity_id) for path in paths]
    selections = [_selection(path, day) for path in paths]
    first = paths[0]
    phase = _phase_at(first, first.current_phase_position)
    if phase is None:
        raise DomainError(500, "The current phase is missing.")
    following = None if first.completed else _phase_at(first, first.current_phase_position + 1)
    done, total = _commitment_counts(transformation)
    return TransformationResponse(
        statement=_statement(transformation, names),
        selections=selections,
        today=_today(day, transformation, paths),
        progress=ProgressResponse(
            phase_name=phase.headline,
            day_in_phase=first.day_in_phase,
            length_days=phase.length_days,
            commitments_done=done,
            commitments_total=total,
            next_phase_name=None if following is None else following.headline,
        ),
        year=_year(transformation, on),
        promises_kept=_promises_kept(transformation),
        started_on=transformation.started_on,
        tomorrow=_tomorrow(transformation, paths, on),
        prior_closed_on=_prior_closed_on(transformation, on),
    )


def _selection(path: TransformationPath, day: Day) -> SelectionResponse:
    phase = _phase_at(path, path.current_phase_position)
    if phase is None:
        raise DomainError(500, "The current phase is missing.")
    identity = find_identity(path.identity_id)
    direction = find_direction(identity, path.direction_id) if identity is not None else None
    active = sum(1 for item in day.commitments if item.path_id == path.id)
    return SelectionResponse(
        identity_id=path.identity_id,
        identity_name=identity.name if identity is not None else path.identity_id,
        direction_id=path.direction_id,
        direction_name=direction.name if direction is not None else path.direction_id,
        phase_name=phase.headline,
        stage_name=phase.name,
        day_in_phase=path.day_in_phase,
        length_days=phase.length_days,
        active_commitments=active,
        completed=path.completed,
        phases=[_phase_response(path, item) for item in sorted(path.phases, key=lambda row: row.position)],
    )


def _phase_response(path: TransformationPath, phase: PathPhase) -> PhaseResponse:
    if path.completed or phase.position < path.current_phase_position:
        status = "complete"
    elif phase.position == path.current_phase_position:
        status = "current"
    else:
        status = "upcoming"
    return PhaseResponse(
        name=phase.name,
        headline=phase.headline,
        status=status,
        length_days=phase.length_days,
    )


def _today(day: Day, transformation: Transformation, paths: list[TransformationPath]) -> TodayResponse:
    groups = []
    for path in paths:
        identity = find_identity(path.identity_id)
        rows = [item for item in day.commitments if item.path_id == path.id]
        rows.sort(key=lambda item: item.planned.position if item.planned is not None else 0)
        groups.append(
            TodayGroupResponse(
                identity_id=path.identity_id,
                identity_name=identity.name if identity is not None else path.identity_id,
                commitments=[_commitment_response(item) for item in rows],
            )
        )
    return TodayResponse(
        date=_as_date(day.calendar_date),
        closed=_status(day.status) == DayStatus.closed.value,
        groups=groups,
        coming_up=_coming_up(day, transformation, paths),
    )


def _commitment_response(commitment: DayCommitment) -> CommitmentResponse:
    planned = commitment.planned
    implementations = []
    if planned is not None:
        for item in sorted(planned.implementations, key=lambda row: row.position):
            implementations.append(ImplementationResponse(id=item.id, title=item.title))
    chosen_id = commitment.implementation_id
    if chosen_id is None:
        chosen_id = commitment.id
    if not implementations:
        implementations.append(
            ImplementationResponse(id=chosen_id, title=commitment.title_snapshot)
        )
    recurrence = planned.recurrence if planned is not None else "daily"
    return CommitmentResponse(
        id=commitment.id,
        planned_commitment_id=planned.id if planned is not None else None,
        objective=commitment.objective_snapshot,
        cadence=_cadence(planned) if planned is not None else "Daily",
        recurrence=recurrence,  # type: ignore[arg-type]
        times_per_week=planned.times_per_week if planned is not None else None,
        weekdays=sorted(_weekdays(planned)) if planned is not None else [],
        month_day=planned.month_day if planned is not None else None,
        due_on=_as_date(planned.due_on) if planned is not None and planned.due_on is not None else None,
        reason=planned.reason if planned is not None else None,
        implementation=ImplementationResponse(id=chosen_id, title=commitment.title_snapshot),
        implementations=implementations,
        status=_status(commitment.status),  # type: ignore[arg-type]
    )


def _year(transformation: Transformation, on: date) -> list[YearDayResponse]:
    by_date = {_as_date(day.calendar_date): day for day in transformation.days}
    days = []
    current = date(on.year, 1, 1)
    end = date(on.year, 12, 31)
    while current <= end:
        record = by_date.get(current)
        commitments = [] if record is None else record.commitments
        days.append(
            YearDayResponse(
                date=current,
                intensity=_intensity(commitments),
                closed=record is not None and _status(record.status) == DayStatus.closed.value,
                today=current == on,
                identities=_year_identities(transformation, commitments),
            )
        )
        current += timedelta(days=1)
    return days


def _year_identities(transformation: Transformation, commitments: list[DayCommitment]) -> list[YearIdentityResponse]:
    paths = sorted(transformation.paths, key=lambda item: item.sort_order)
    rows = []
    for path in paths:
        own = [item for item in commitments if item.path_id == path.id]
        rows.append(YearIdentityResponse(identity_id=path.identity_id, intensity=_intensity(own)))
    return rows


def _intensity(commitments: list[DayCommitment]) -> int:
    total = len(commitments)
    if total == 0:
        return 0
    done = sum(1 for item in commitments if _status(item.status) == CommitmentStatus.done.value)
    if done <= 0:
        return 0
    if done >= total:
        return 2
    return 1


def _commitment_counts(transformation: Transformation) -> tuple[int, int]:
    done = 0
    total = 0
    for day in transformation.days:
        if _status(day.status) != DayStatus.closed.value:
            continue
        for item in day.commitments:
            total += 1
            if _status(item.status) == CommitmentStatus.done.value:
                done += 1
    return done, total


def _promises_kept(transformation: Transformation) -> int:
    return sum(1 for day in transformation.days if _status(day.status) == DayStatus.closed.value)


def _prior_closed_on(transformation: Transformation, on: date) -> date | None:
    closed = [
        _as_date(day.calendar_date)
        for day in transformation.days
        if _status(day.status) == DayStatus.closed.value and _as_date(day.calendar_date) < on
    ]
    if not closed:
        return None
    return max(closed)


def _tomorrow(
    transformation: Transformation,
    paths: list[TransformationPath],
    on: date,
) -> list[TomorrowItemResponse]:
    del paths
    target = on + timedelta(days=1)
    rows: list[TomorrowItemResponse] = []
    for path, planned, title in _due_pairs(transformation, target, materialize=False, preview_from=on):
        identity = find_identity(path.identity_id)
        chosen = _default_implementation(planned)
        rows.append(
            TomorrowItemResponse(
                identity_name=identity.name if identity is not None else path.identity_id,
                title=title or chosen.title,
                cadence=_cadence(planned),
            )
        )
    return rows


def install_coach_plan(
    db: Session,
    transformation: Transformation,
    on: date,
    goals: list[dict],
    rationale: str | None,
) -> None:
    transformation.origin = Origin.adaptive
    text = rationale.strip() if isinstance(rationale, str) else ""
    if text:
        if transformation.rationale and transformation.rationale.strip():
            transformation.rationale = transformation.rationale.rstrip() + "\n" + text
        else:
            transformation.rationale = text
    grouped: dict[str, list[dict]] = {}
    for goal in goals:
        grouped.setdefault(str(goal["identity_id"]), []).append(goal)
    for identity_id, items in grouped.items():
        path = _path_for(transformation, identity_id)
        if path is None:
            raise DomainError(422, "The coach response could not be used.")
        phase = _phase_at(path, path.current_phase_position)
        if phase is None:
            raise DomainError(500, "The current phase is missing.")
        _replace_commitments(db, phase, items)
    day = _find_day(transformation, on)
    if day is not None:
        _rebuild_open(day, transformation)


def install_today_override(transformation: Transformation, on: date, goals: list[dict]) -> None:
    context = dict(transformation.context or {})
    context["today_override"] = {"on": on.isoformat(), "goals": goals[:5]}
    context.pop("proposal", None)
    transformation.context = context
    day = _find_day(transformation, on)
    if day is not None:
        _rebuild_open(day, transformation)


def _replace_commitments(db: Session, phase: PathPhase, goals: list[dict]) -> None:
    _detach_planned(db, [item.id for item in list(phase.commitments)])
    for item in list(phase.commitments):
        phase.commitments.remove(item)
    db.flush()
    for goal in sorted(goals, key=lambda item: int(item["position"])):
        due_on = goal.get("due_on")
        planned = PlannedCommitment(
            position=int(goal["position"]),
            unlock_streak=0,
            objective=str(goal["objective"]),
            catalog_commitment_id=None,
            recurrence=str(goal["recurrence"]),
            times_per_week=goal.get("times_per_week"),
            weekdays=list(goal.get("weekdays") or []),
            month_day=goal.get("month_day"),
            due_on=due_on if isinstance(due_on, date) else None,
            reason=goal.get("reason"),
        )
        planned.implementations.append(
            PlannedImplementation(position=0, title=str(goal["title"]), is_default=True)
        )
        phase.commitments.append(planned)
    db.flush()


def _detach_planned(db: Session, planned_ids: list[UUID]) -> None:
    if not planned_ids:
        return
    rows = db.scalars(
        select(DayCommitment).where(DayCommitment.planned_commitment_id.in_(planned_ids))
    ).all()
    for row in rows:
        row.planned_commitment_id = None
        row.implementation_id = None
        row.planned = None
        row.implementation = None
    db.flush()


def _rebuild_open(day: Day, transformation: Transformation) -> None:
    if _status(day.status) != DayStatus.open.value:
        return
    for item in list(day.commitments):
        if _status(item.status) == CommitmentStatus.open.value:
            day.commitments.remove(item)
    _schedule(day, transformation)


def _load(db: Session, user_id: UUID) -> Transformation | None:
    return db.scalar(
        select(Transformation)
        .where(Transformation.user_id == user_id)
        .options(
            selectinload(Transformation.paths)
            .selectinload(TransformationPath.phases)
            .selectinload(PathPhase.commitments)
            .selectinload(PlannedCommitment.implementations),
            selectinload(Transformation.days).selectinload(Day.commitments),
        )
    )


def _find_day(transformation: Transformation, on: date) -> Day | None:
    for day in transformation.days:
        if _as_date(day.calendar_date) == on:
            return day
    return None


def _path_for(transformation: Transformation, identity_id: str) -> TransformationPath | None:
    for path in transformation.paths:
        if path.identity_id == identity_id:
            return path
    return None


def _phase_at(path: TransformationPath, position: int) -> PathPhase | None:
    for phase in path.phases:
        if phase.position == position:
            return phase
    return None


def _default_implementation(planned: PlannedCommitment) -> PlannedImplementation:
    ordered = sorted(planned.implementations, key=lambda item: item.position)
    for item in ordered:
        if item.is_default:
            return item
    return ordered[0]


def _identity_name(identity_id: str) -> str:
    identity = find_identity(identity_id)
    if identity is None:
        return identity_id
    return identity.name


def _statement(transformation: Transformation, names: list[str]) -> str:
    context = transformation.context if isinstance(transformation.context, dict) else None
    statement = context.get("statement") if context is not None else None
    if isinstance(statement, str) and statement.strip():
        return statement.strip()
    lowered = [name.lower() for name in names]
    if len(lowered) == 1:
        return f"I'm becoming {lowered[0]}."
    return f"I'm becoming {lowered[0]} and {lowered[1]}."


def _check_date(on: date) -> None:
    today = utcnow().date()
    if abs((on - today).days) > 1:
        raise DomainError(422, "That date is outside the allowed range.")


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _status(value: enum.Enum | str) -> str:
    if isinstance(value, enum.Enum):
        return str(value.value)
    return str(value)
