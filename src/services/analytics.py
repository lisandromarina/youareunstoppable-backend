import enum
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.onboarding import OnboardingStep
from src.models.transformation import CommitmentStatus, Day, DayCommitment, DayStatus, Transformation
from src.models.user import User
from src.schemas.admin import (
    AnalyticsResponse,
    CohortDayResponse,
    CohortResponse,
    FunnelStepResponse,
    OverviewResponse,
)
from src.services.errors import DomainError

_FUNNEL = (
    ("signup", "Sign up"),
    ("begin", "Begin"),
    ("identity", "Choose identity"),
    ("direction", "Choose direction"),
    ("start", "Start path"),
    ("day1", "Complete day 1"),
)
_RETENTION_DAYS = (1, 3, 7, 14)


def mark_onboarding(db: Session, user: User, step: str) -> None:
    if step not in {"begin", "identity", "direction"}:
        raise DomainError(422, "Unknown step.")
    existing = db.scalar(
        select(OnboardingStep.id).where(
            OnboardingStep.user_id == user.id,
            OnboardingStep.step == step,
        )
    )
    if existing is not None:
        return
    db.add(OnboardingStep(user_id=user.id, step=step))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()


def snapshot(db: Session, today: date) -> AnalyticsResponse:
    users = list(db.scalars(select(User).where(User.deleted_at.is_(None))))
    signup = {user.id: _as_date(user.created_at) for user in users}
    ids = set(signup)

    starts: dict[UUID, date] = {}
    for user_id, started_on in db.execute(select(Transformation.user_id, Transformation.started_on)):
        if user_id in ids:
            starts[user_id] = _as_date(started_on)
    started = set(starts)

    opened: dict[UUID, set[date]] = defaultdict(set)
    closed: dict[UUID, set[date]] = defaultdict(set)
    day_rows = db.execute(
        select(Transformation.user_id, Day.calendar_date, Day.status).join(
            Day, Day.transformation_id == Transformation.id
        )
    ).all()
    for user_id, calendar_date, status in day_rows:
        if user_id not in ids:
            continue
        day = _as_date(calendar_date)
        opened[user_id].add(day)
        if _value(status) == DayStatus.closed.value:
            closed[user_id].add(day)

    commitments_done = 0
    commitments_skipped = 0
    commitment_rows = db.execute(
        select(Transformation.user_id, DayCommitment.status)
        .join(Day, Day.id == DayCommitment.day_id)
        .join(Transformation, Transformation.id == Day.transformation_id)
    ).all()
    for user_id, status in commitment_rows:
        if user_id not in ids:
            continue
        value = _value(status)
        if value == CommitmentStatus.done.value:
            commitments_done += 1
        elif value == CommitmentStatus.skipped.value:
            commitments_skipped += 1

    marks: dict[UUID, set[str]] = defaultdict(set)
    for user_id, step in db.execute(select(OnboardingStep.user_id, OnboardingStep.step)):
        if user_id in ids:
            marks[user_id].add(step)

    def closed_first_day(user_id: UUID) -> bool:
        start = starts.get(user_id)
        return start is not None and start <= today and start in closed[user_id]

    def reached(user_id: UUID, key: str) -> bool:
        own = marks[user_id]
        has_start = user_id in started
        if key == "signup":
            return True
        if key == "begin":
            return bool(own) or has_start
        if key == "identity":
            return "identity" in own or "direction" in own or has_start
        if key == "direction":
            return "direction" in own or has_start
        if key == "start":
            return has_start
        return closed_first_day(user_id)

    counts = {key: sum(1 for user_id in ids if reached(user_id, key)) for key, _label in _FUNNEL}
    funnel: list[FunnelStepResponse] = []
    previous = 0
    for index, (key, label) in enumerate(_FUNNEL):
        count = counts[key]
        funnel.append(
            FunnelStepResponse(
                key=key,
                label=label,
                count=count,
                percent_of_signups=_percent(count, counts["signup"]),
                percent_of_previous=None if index == 0 else _percent(count, previous),
            )
        )
        previous = count

    active_since = today - timedelta(days=6)
    active = sum(
        1
        for days in opened.values()
        if any(active_since <= day <= today for day in days)
    )
    first_days = [user_id for user_id, start in starts.items() if start <= today]
    overview = OverviewResponse(
        total_users=len(ids),
        new_users_today=sum(1 for signed in signup.values() if signed == today),
        new_users_7d=sum(1 for signed in signup.values() if signed >= today - timedelta(days=6)),
        new_users_30d=sum(1 for signed in signup.values() if signed >= today - timedelta(days=29)),
        started_path=len(started),
        days_completed=sum(len(days) for days in closed.values()),
        active_users=active,
        opened_today=sum(1 for days in opened.values() if today in days),
        closed_today=sum(1 for days in closed.values() if today in days),
        commitments_done=commitments_done,
        commitments_skipped=commitments_skipped,
        return_1d=_rate(signup, opened, today, 1),
        closed_1d=_rate(signup, closed, today, 1),
        return_3d=_rate(signup, opened, today, 3),
        closed_3d=_rate(signup, closed, today, 3),
        return_7d=_rate(signup, opened, today, 7),
        closed_7d=_rate(signup, closed, today, 7),
        day1_closure=_percent(sum(1 for user_id in first_days if closed_first_day(user_id)), len(first_days)),
    )

    grouped: dict[date, list[UUID]] = defaultdict(list)
    for user_id, signed in signup.items():
        grouped[signed].append(user_id)
    cohorts = [
        _cohort(signed, grouped[signed], opened, closed, today)
        for signed in sorted(grouped, reverse=True)[:14]
    ]
    return AnalyticsResponse(overview=overview, funnel=funnel, cohorts=cohorts)


def _rate(
    signup: dict[UUID, date],
    days_by_user: dict[UUID, set[date]],
    today: date,
    offset: int,
) -> float | None:
    eligible = [
        user_id
        for user_id, signed in signup.items()
        if signed + timedelta(days=offset) <= today
    ]
    if not eligible:
        return None
    kept = sum(
        1
        for user_id in eligible
        if signup[user_id] + timedelta(days=offset) in days_by_user[user_id]
    )
    return _percent(kept, len(eligible))


def _cohort(
    signed: date,
    members: list[UUID],
    opened: dict[UUID, set[date]],
    closed: dict[UUID, set[date]],
    today: date,
) -> CohortResponse:
    def cell(offset: int) -> CohortDayResponse | None:
        target = signed + timedelta(days=offset)
        if target > today:
            return None
        return CohortDayResponse(
            returned=_percent(sum(1 for user_id in members if target in opened[user_id]), len(members)),
            closed=_percent(sum(1 for user_id in members if target in closed[user_id]), len(members)),
        )

    return CohortResponse(
        date=signed,
        size=len(members),
        day_1=cell(1),
        day_3=cell(3),
        day_7=cell(7),
        day_14=cell(14),
    )


def _percent(part: int, whole: int) -> float | None:
    if whole <= 0:
        return None
    return round(100 * part / whole, 1)


def _as_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).date()
    return value


def _value(status: enum.Enum | str) -> str:
    if isinstance(status, enum.Enum):
        return str(status.value)
    return str(status)
