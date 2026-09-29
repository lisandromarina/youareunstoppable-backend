from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.onboarding import OnboardingStep
from src.models.transformation import Day, DayStatus, Transformation
from src.models.user import User
from src.schemas.admin import (
    AnalyticsResponse,
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

    started = {user_id for user_id in db.scalars(select(Transformation.user_id)) if user_id in ids}
    closed: dict[UUID, set[date]] = defaultdict(set)
    rows = db.execute(
        select(Transformation.user_id, Day.calendar_date)
        .join(Day, Day.transformation_id == Transformation.id)
        .where(Day.status == DayStatus.closed)
    ).all()
    for user_id, calendar_date in rows:
        if user_id in ids:
            closed[user_id].add(_as_date(calendar_date))

    marks: dict[UUID, set[str]] = defaultdict(set)
    for user_id, step in db.execute(select(OnboardingStep.user_id, OnboardingStep.step)):
        if user_id in ids:
            marks[user_id].add(step)

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
        return bool(closed.get(user_id))

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
    active = sum(1 for days in closed.values() if any(day >= active_since for day in days))
    overview = OverviewResponse(
        total_users=len(ids),
        new_users_today=sum(1 for signed in signup.values() if signed == today),
        new_users_7d=sum(1 for signed in signup.values() if signed >= today - timedelta(days=6)),
        new_users_30d=sum(1 for signed in signup.values() if signed >= today - timedelta(days=29)),
        started_path=len(started),
        days_completed=sum(len(days) for days in closed.values()),
        active_users=active,
        retention_1d=_retention(signup, closed, today, 1),
        retention_3d=_retention(signup, closed, today, 3),
        retention_7d=_retention(signup, closed, today, 7),
    )

    grouped: dict[date, list[UUID]] = defaultdict(list)
    for user_id, signed in signup.items():
        grouped[signed].append(user_id)
    cohorts = [
        _cohort(signed, grouped[signed], closed, today)
        for signed in sorted(grouped, reverse=True)[:14]
    ]
    return AnalyticsResponse(overview=overview, funnel=funnel, cohorts=cohorts)


def _retention(
    signup: dict[UUID, date],
    closed: dict[UUID, set[date]],
    today: date,
    offset: int,
) -> float | None:
    eligible = [user_id for user_id, signed in signup.items() if signed <= today - timedelta(days=offset)]
    if not eligible:
        return None
    kept = sum(1 for user_id in eligible if signup[user_id] + timedelta(days=offset) in closed[user_id])
    return _percent(kept, len(eligible))


def _cohort(
    signed: date,
    members: list[UUID],
    closed: dict[UUID, set[date]],
    today: date,
) -> CohortResponse:
    values = {}
    for offset in _RETENTION_DAYS:
        target = signed + timedelta(days=offset)
        if target > today:
            values[offset] = None
        else:
            kept = sum(1 for user_id in members if target in closed[user_id])
            values[offset] = _percent(kept, len(members))
    return CohortResponse(
        date=signed,
        size=len(members),
        day_1=values[1],
        day_3=values[3],
        day_7=values[7],
        day_14=values[14],
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
