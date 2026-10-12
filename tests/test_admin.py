from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from src.core.security import utcnow
from src.models.onboarding import OnboardingStep
from src.models.refresh_token import RefreshToken
from src.models.subscription import Subscription
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
from src.models.user import Role, User
from src.services.analytics import snapshot


def register(client, email, password="password123"):
    return client.post("/api/auth/register", json={"email": email, "password": password})


def test_analytics_is_hidden_from_members(client):
    register(client, "ada@example.com")
    hidden = client.get("/api/admin/analytics", params={"on": utcnow().date().isoformat()})
    assert hidden.status_code == 404
    marked = client.post("/api/onboarding", json={"step": "begin"})
    assert marked.status_code == 204
    again = client.post("/api/onboarding", json={"step": "begin"})
    assert again.status_code == 204


def test_snapshot_counts_dropoff_and_return(db):
    _clear(db)
    today = date(2026, 9, 29)
    signed = today - timedelta(days=10)
    returned = _user(db, "returned@example.com", signed)
    never = _user(db, "never@example.com", signed)
    fresh = _user(db, "fresh@example.com", today)
    stopped = _user(db, "stopped@example.com", today)
    finished = _user(db, "finished@example.com", today - timedelta(days=9))
    assert never.id != returned.id
    db.add(OnboardingStep(user_id=stopped.id, step="begin"))
    transformation = Transformation(
        user_id=returned.id,
        started_on=signed,
        origin=Origin.catalog,
    )
    first = Transformation(
        user_id=finished.id,
        started_on=today - timedelta(days=9),
        origin=Origin.catalog,
    )
    db.add(transformation)
    db.add(first)
    db.flush()
    closed_days = []
    for offset in (1, 3, 10):
        day = Day(
            transformation_id=transformation.id,
            calendar_date=signed + timedelta(days=offset),
            status=DayStatus.closed,
        )
        db.add(day)
        closed_days.append(day)
    opened_later = Day(
        transformation_id=transformation.id,
        calendar_date=signed + timedelta(days=7),
        status=DayStatus.open,
    )
    db.add(opened_later)
    started = Day(
        transformation_id=first.id,
        calendar_date=first.started_on,
        status=DayStatus.closed,
    )
    db.add(started)
    db.flush()
    db.add(
        DayCommitment(
            day_id=opened_later.id,
            status=CommitmentStatus.skipped,
            objective_snapshot="Keep one promise",
            title_snapshot="Leave it for later",
        )
    )
    db.add(
        DayCommitment(
            day_id=closed_days[0].id,
            status=CommitmentStatus.done,
            objective_snapshot="Keep one promise",
            title_snapshot="Do the thing",
        )
    )
    db.commit()

    body = snapshot(db, today)
    overview = body.overview
    assert overview.total_users == 5
    assert overview.new_users_today == 2
    assert overview.new_users_7d == 2
    assert overview.new_users_30d == 5
    assert overview.started_path == 2
    assert overview.days_completed == 4
    assert overview.active_users == 1
    assert overview.opened_today == 1
    assert overview.closed_today == 1
    assert overview.commitments_done == 1
    assert overview.commitments_skipped == 1
    assert overview.return_1d == 33.3
    assert overview.closed_1d == 33.3
    assert overview.return_3d == 33.3
    assert overview.closed_3d == 33.3
    assert overview.return_7d == 33.3
    assert overview.closed_7d == 0.0
    assert overview.day1_closure == 50.0

    counts = {step.key: step for step in body.funnel}
    assert counts["signup"].count == 5
    assert counts["begin"].count == 3
    assert counts["identity"].count == 2
    assert counts["direction"].count == 2
    assert counts["start"].count == 2
    assert counts["day1"].count == 1
    assert counts["begin"].percent_of_previous == 60.0
    assert counts["start"].percent_of_signups == 40.0

    older = next(row for row in body.cohorts if row.date == signed)
    assert older.size == 2
    assert older.day_1 is not None
    assert older.day_1.returned == 50.0
    assert older.day_1.closed == 50.0
    assert older.day_3 is not None
    assert older.day_3.returned == 50.0
    assert older.day_3.closed == 50.0
    assert older.day_7 is not None
    assert older.day_7.returned == 50.0
    assert older.day_7.closed == 0.0
    assert older.day_14 is None

    same_day = next(row for row in body.cohorts if row.date == today)
    assert same_day.day_1 is None
    assert same_day.day_7 is None


def test_admin_can_read_the_dashboard(client, db):
    register(client, "ada@example.com")
    user = db.scalar(select(User).where(User.email == "ada@example.com"))
    assert user is not None
    user.role = Role.admin
    db.commit()

    today = utcnow().date().isoformat()
    response = client.get("/api/admin/analytics", params={"on": today})
    assert response.status_code == 200
    body = response.json()
    assert body["overview"]["total_users"] == 1
    assert body["overview"]["return_1d"] is None
    assert body["overview"]["day1_closure"] is None
    assert body["funnel"][0]["label"] == "Sign up"
    assert body["cohorts"][0]["day_14"] is None

    far = client.get("/api/admin/analytics", params={"on": "2020-01-01"})
    assert far.status_code == 422


def _clear(db) -> None:
    db.query(DayCommitment).delete()
    db.query(Day).delete()
    db.query(PlannedImplementation).delete()
    db.query(PlannedCommitment).delete()
    db.query(PathPhase).delete()
    db.query(TransformationPath).delete()
    db.query(Transformation).delete()
    db.query(RefreshToken).delete()
    db.query(OnboardingStep).delete()
    db.query(Subscription).delete()
    db.query(User).delete()
    db.commit()


def _user(db, email: str, signed: date) -> User:
    user = User(
        email=email,
        role=Role.user,
        created_at=datetime(signed.year, signed.month, signed.day, 12, tzinfo=timezone.utc),
    )
    db.add(user)
    db.flush()
    return user
