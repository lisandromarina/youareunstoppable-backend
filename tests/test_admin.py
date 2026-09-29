from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from src.models.onboarding import OnboardingStep
from src.models.refresh_token import RefreshToken
from src.models.subscription import Subscription
from src.models.transformation import (
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
    assert client.get("/api/admin/analytics").status_code == 404
    marked = client.post("/api/onboarding", json={"step": "begin"})
    assert marked.status_code == 204
    again = client.post("/api/onboarding", json={"step": "begin"})
    assert again.status_code == 204


def test_snapshot_counts_dropoff_and_return(db):
    _clear(db)
    today = date(2026, 9, 29)
    returned = _user(db, "returned@example.com", today - timedelta(days=10))
    fresh = _user(db, "fresh@example.com", today)
    stopped = _user(db, "stopped@example.com", today)
    db.add(OnboardingStep(user_id=stopped.id, step="begin"))
    transformation = Transformation(
        user_id=returned.id,
        started_on=today - timedelta(days=10),
        origin=Origin.catalog,
    )
    db.add(transformation)
    db.flush()
    for offset in (1, 3, 10):
        db.add(
            Day(
                transformation_id=transformation.id,
                calendar_date=today - timedelta(days=10) + timedelta(days=offset),
                status=DayStatus.closed,
            )
        )
    db.commit()

    body = snapshot(db, today)
    overview = body.overview
    assert overview.total_users == 3
    assert overview.new_users_today == 2
    assert overview.new_users_7d == 2
    assert overview.new_users_30d == 3
    assert overview.started_path == 1
    assert overview.days_completed == 3
    assert overview.active_users == 1
    assert overview.retention_1d == 100.0
    assert overview.retention_3d == 100.0
    assert overview.retention_7d == 0.0

    counts = {step.key: step for step in body.funnel}
    assert counts["signup"].count == 3
    assert counts["begin"].count == 2
    assert counts["identity"].count == 1
    assert counts["direction"].count == 1
    assert counts["start"].count == 1
    assert counts["day1"].count == 1
    assert counts["begin"].percent_of_previous == 66.7
    assert counts["start"].percent_of_signups == 33.3

    older = next(row for row in body.cohorts if row.date == today - timedelta(days=10))
    assert older.size == 1
    assert older.day_1 == 100.0
    assert older.day_3 == 100.0
    assert older.day_7 == 0.0
    assert older.day_14 is None


def test_admin_can_read_the_dashboard(client, db):
    register(client, "ada@example.com")
    user = db.scalar(select(User).where(User.email == "ada@example.com"))
    assert user is not None
    user.role = Role.admin
    db.commit()

    response = client.get("/api/admin/analytics")
    assert response.status_code == 200
    body = response.json()
    assert body["overview"]["total_users"] == 1
    assert body["funnel"][0]["label"] == "Sign up"
    assert body["cohorts"][0]["day_14"] is None


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
