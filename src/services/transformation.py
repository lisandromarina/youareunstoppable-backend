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
    _close_finished_days(transformation, on)
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


def _close_finished_days(transformation: Transformation, on: date) -> None:
    pending = [
        day
        for day in transformation.days
        if _as_date(day.calendar_date) < on and _status(day.status) == DayStatus.open.value
    ]
    pending.sort(key=lambda day: _as_date(day.calendar_date))
    for day in pending:
        done = any(_status(item.status) == CommitmentStatus.done.value for item in day.commitments)
        if not done:
            continue
        day.status = DayStatus.closed
        day.closed_at = utcnow()
        for path in transformation.paths:
            _advance(path)


def _schedule(day: Day, transformation: Transformation) -> None:
    on = _as_date(day.calendar_date)
    for path in sorted(transformation.paths, key=lambda item: item.sort_order):
        for planned in _due_commitments(path, transformation, on):
            _append_occurrence(day, path, planned)


def _append_occurrence(day: Day, path: TransformationPath, planned: PlannedCommitment) -> None:
    chosen = _default_implementation(planned)
    day.commitments.append(
        DayCommitment(
            path=path,
            planned=planned,
            implementation=chosen,
            status=CommitmentStatus.open,
            objective_snapshot=planned.objective,
            title_snapshot=chosen.title,
        )
    )


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
    if planned.recurrence == "monthly":
        return f"Day {planned.month_day or 1}"
    names = [_WEEKDAYS[day] for day in sorted(_weekdays(planned)) if 0 <= day <= 6]
    return ", ".join(names)


def _coming_up(
    day: Day,
    transformation: Transformation,
    paths: list[TransformationPath],
) -> list[UpcomingResponse]:
    on = _as_date(day.calendar_date)
    present = {item.planned_commitment_id for item in day.commitments}
    rows: list[UpcomingResponse] = []
    for path in paths:
        identity = find_identity(path.identity_id)
        identity_name = identity.name if identity is not None else path.identity_id
        for planned in _active_commitments(path, transformation, on):
            if planned.id in present or _is_due(on, planned):
                continue
            chosen = _default_implementation(planned)
            rows.append(
                UpcomingResponse(
                    planned_commitment_id=planned.id,
                    identity_name=identity_name,
                    objective=planned.objective,
                    title=chosen.title,
                    cadence=_cadence(planned),
                    recurrence=planned.recurrence,  # type: ignore[arg-type]
                    times_per_week=planned.times_per_week,
                    weekdays=sorted(_weekdays(planned)),
                    month_day=planned.month_day,
                    when=_when(planned),
                )
            )
    return rows


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
    due: dict[UUID, tuple[TransformationPath, PlannedCommitment]] = {}
    for path in transformation.paths:
        for planned in _due_commitments(path, transformation, on):
            due[planned.id] = (path, planned)
            if not any(item.planned_commitment_id == planned.id for item in day.commitments):
                _append_occurrence(day, path, planned)
    for item in list(day.commitments):
        if item.planned_commitment_id not in due and _status(item.status) == CommitmentStatus.open.value:
            day.commitments.remove(item)


def _sync_occurrence(
    day: Day,
    transformation: Transformation,
    path: TransformationPath,
    planned: PlannedCommitment,
) -> None:
    on = _as_date(day.calendar_date)
    existing = [item for item in day.commitments if item.planned_commitment_id == planned.id]
    active = {item.id for item in _active_commitments(path, transformation, on)}
    if planned.id in active and _is_due(on, planned):
        if not existing:
            _append_occurrence(day, path, planned)
        return
    for item in existing:
        if _status(item.status) == CommitmentStatus.open.value:
            day.commitments.remove(item)


def _advance(path: TransformationPath) -> None:
    path.commitment_streak += 1
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
        statement=_statement(names),
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
        started_on=_as_date(transformation.started_on),
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
    target = on + timedelta(days=1)
    rows: list[TomorrowItemResponse] = []
    for path in paths:
        identity = find_identity(path.identity_id)
        identity_name = identity.name if identity is not None else path.identity_id
        for planned in _due_commitments(path, transformation, target):
            chosen = _default_implementation(planned)
            rows.append(
                TomorrowItemResponse(
                    identity_name=identity_name,
                    title=chosen.title,
                    cadence=_cadence(planned),
                )
            )
    return rows


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


def _statement(names: list[str]) -> str:
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
