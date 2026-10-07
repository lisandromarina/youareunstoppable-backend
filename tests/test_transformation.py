from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from src.models.user import Role, User

def register(client, email="ada@example.com", password="password123"):
    return client.post("/api/auth/register", json={"email": email, "password": password})


def selections(*pairs: tuple[str, str]) -> dict:
    return {
        "selections": [
            {"identity_id": identity_id, "direction_id": direction_id}
            for identity_id, direction_id in pairs
        ]
    }


BOTH = selections(
    ("disciplined", "master-deep-work"),
    ("healthy", "move-daily"),
)


@pytest.fixture
def clock(monkeypatch):
    state = {"day": date(2026, 9, 26)}

    def fake_now() -> datetime:
        current = state["day"]
        return datetime(current.year, current.month, current.day, 15, tzinfo=timezone.utc)

    monkeypatch.setattr("src.services.transformation.utcnow", fake_now)
    return state


def on(clock) -> str:
    return clock["day"].isoformat()


def start(client, clock, body=BOTH):
    response = client.post("/api/transformation", params={"on": on(clock)}, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def titles(body, identity_id: str) -> list[str]:
    for group in body["today"]["groups"]:
        if group["identity_id"] == identity_id:
            return [item["implementation"]["title"] for item in group["commitments"]]
    raise AssertionError(identity_id)


def settle(client, clock, body):
    current = on(clock)
    if body["today"]["date"] != current or body["today"]["closed"]:
        fetched = client.get("/api/transformation", params={"on": current})
        assert fetched.status_code == 200, fetched.text
        body = fetched.json()
    for group in body["today"]["groups"]:
        for commitment in group["commitments"]:
            if commitment["status"] == "open":
                toggled = client.post(
                    f"/api/transformation/today/commitments/{commitment['id']}/toggle",
                    params={"on": current},
                )
                assert toggled.status_code == 200, toggled.text
    clock["day"] += timedelta(days=1)
    opened = client.get("/api/transformation", params={"on": on(clock)})
    assert opened.status_code == 200, opened.text
    return opened.json()


def test_catalog_requires_auth_and_marks_the_extra(client):
    assert client.get("/api/catalog").status_code == 401
    register(client)
    response = client.get("/api/catalog")
    assert response.status_code == 200
    identities = {item["id"]: item for item in response.json()["identities"]}
    assert "disciplined" in identities
    assert "healthy" in identities
    direction = next(
        item
        for item in identities["disciplined"]["directions"]
        if item["id"] == "master-deep-work"
    )
    phase = direction["phases"][0]
    assert phase["headline"] == "Keep One Promise"
    kinds = {item["kind"] for item in phase["commitments"]}
    assert kinds == {"base", "extra"}
    first = phase["commitments"][0]
    assert first["recurrence"] == "daily"
    extra = next(item for item in phase["commitments"] if item["kind"] == "extra")
    assert extra["recurrence"] == "weekly"
    assert extra["weekdays"] == [0]


def test_start_rejects_a_third_identity_and_a_second_start(client, clock):
    register(client)
    assert client.get("/api/transformation", params={"on": on(clock)}).status_code == 404
    too_many = selections(
        ("disciplined", "master-deep-work"),
        ("healthy", "move-daily"),
        ("focused", "single-task"),
    )
    assert client.post("/api/transformation", params={"on": on(clock)}, json=too_many).status_code == 422
    unknown = selections(("disciplined", "not-a-direction"),)
    assert client.post("/api/transformation", params={"on": on(clock)}, json=unknown).status_code == 422
    body = start(client, clock)
    assert body["statement"] == "I'm becoming disciplined and healthy."
    assert titles(body, "disciplined") == ["15 minutes of uninterrupted work"]
    assert titles(body, "healthy") == ["Walk for 20 minutes"]
    assert titles(body, "disciplined") != titles(body, "healthy")
    assert body["promises_kept"] == 0
    assert body["year"][0]["date"] == "2026-01-01"
    assert body["year"][-1]["date"] == "2026-12-31"
    assert len(body["year"]) == 365
    assert next(item for item in body["year"] if item["today"])["date"] == "2026-09-26"
    again = client.post("/api/transformation", params={"on": on(clock)}, json=BOTH)
    assert again.status_code == 409


def mark_one_done(client, clock, identity_id=None):
    current = on(clock)
    body = client.get("/api/transformation", params={"on": current})
    assert body.status_code == 200, body.text
    payload = body.json()
    commitment = next(
        item
        for group in payload["today"]["groups"]
        if identity_id is None or group["identity_id"] == identity_id
        for item in group["commitments"]
        if item["status"] == "open"
    )
    toggled = client.post(
        f"/api/transformation/today/commitments/{commitment['id']}/toggle",
        params={"on": current},
    )
    assert toggled.status_code == 200, toggled.text
    clock["day"] += timedelta(days=1)
    return toggled.json()


def test_goals_grow_after_three_done_days_and_shrink_after_two_misses(client, clock):
    register(client)
    start(client, clock, selections(("disciplined", "master-deep-work"),))
    opened = client.get("/api/transformation", params={"on": on(clock)})
    assert titles(opened.json(), "disciplined") == ["15 minutes of uninterrupted work"]
    assert opened.json()["today"]["coming_up"] == []
    for _ in range(3):
        mark_one_done(client, clock)
    tuesday = client.get("/api/transformation", params={"on": on(clock)})
    assert tuesday.status_code == 200, tuesday.text
    assert on(clock) == "2026-09-29"
    assert titles(tuesday.json(), "disciplined") == ["15 minutes of uninterrupted work"]
    upcoming = [item["title"] for item in tuesday.json()["today"]["coming_up"]]
    assert upcoming == ["Open the work and stay with it for 15 minutes"]
    clock["day"] = date(2026, 9, 30)
    wednesday = client.get("/api/transformation", params={"on": on(clock)})
    assert wednesday.status_code == 200, wednesday.text
    assert titles(wednesday.json(), "disciplined") == [
        "15 minutes of uninterrupted work",
        "Open the work and stay with it for 15 minutes",
    ]
    clock["day"] = date(2026, 10, 1)
    dropped = client.get("/api/transformation", params={"on": on(clock)})
    assert dropped.status_code == 200, dropped.text
    assert titles(dropped.json(), "disciplined") == ["15 minutes of uninterrupted work"]
    assert dropped.json()["today"]["coming_up"] == []
    clock["day"] = date(2026, 10, 6)
    still_one = client.get("/api/transformation", params={"on": on(clock)})
    assert titles(still_one.json(), "disciplined") == ["15 minutes of uninterrupted work"]


def test_every_identity_grows_on_its_own(client, clock):
    register(client, email="healthy@example.com")
    start(
        client,
        clock,
        selections(("healthy", "move-daily"), ("focused", "single-task")),
    )
    opened = client.get("/api/transformation", params={"on": on(clock)})
    assert len(titles(opened.json(), "healthy")) == 1
    assert len(titles(opened.json(), "focused")) == 1
    for _ in range(3):
        mark_one_done(client, clock, "healthy")
    tuesday = client.get("/api/transformation", params={"on": on(clock)}).json()
    healthy_upcoming = [item["title"] for item in tuesday["today"]["coming_up"] if item["identity_name"] == "Healthy"]
    focused_upcoming = [item["title"] for item in tuesday["today"]["coming_up"] if item["identity_name"] == "Focused"]
    assert healthy_upcoming == ["Take a 15-minute walk outside"]
    assert focused_upcoming == []
    assert len(titles(tuesday, "focused")) == 1


def test_an_earned_goal_can_move_to_another_day(client, clock):
    register(client, email="schedule@example.com")
    start(client, clock, selections(("disciplined", "master-deep-work"),))
    for _ in range(6):
        mark_one_done(client, clock)
    friday = client.get("/api/transformation", params={"on": on(clock)})
    assert friday.status_code == 200, friday.text
    assert on(clock) == "2026-10-02"
    upcoming = {item["title"]: item for item in friday.json()["today"]["coming_up"]}
    phone = upcoming["No phone during the first hour of work"]
    moved = client.post(
        f"/api/transformation/commitments/{phone['planned_commitment_id']}/schedule",
        params={"on": on(clock)},
        json={"weekdays": [4]},
    )
    assert moved.status_code == 200, moved.text
    assert "No phone during the first hour of work" in titles(moved.json(), "disciplined")
    focus = next(
        item
        for item in friday.json()["today"]["groups"][0]["commitments"]
        if item["implementation"]["title"] == "Open the work and stay with it for 15 minutes"
    )
    rejected = client.post(
        f"/api/transformation/commitments/{focus['planned_commitment_id']}/schedule",
        params={"on": on(clock)},
        json={"weekdays": [0, 2]},
    )
    assert rejected.status_code == 422


def test_replace_skip_and_a_finished_day_needs_one_done_goal(client, clock):
    register(client)
    body = start(client, clock, selections(("healthy", "move-daily"),))
    commitment = body["today"]["groups"][0]["commitments"][0]
    other = next(
        item for item in commitment["implementations"] if item["id"] != commitment["implementation"]["id"]
    )
    replaced = client.post(
        f"/api/transformation/today/commitments/{commitment['id']}/replace",
        params={"on": on(clock)},
        json={"implementation_id": other["id"]},
    )
    assert replaced.status_code == 200
    updated = replaced.json()["today"]["groups"][0]["commitments"][0]
    assert updated["objective"] == commitment["objective"]
    assert updated["implementation"]["title"] == other["title"]
    skipped = client.post(
        f"/api/transformation/today/commitments/{commitment['id']}/skip",
        params={"on": on(clock)},
    )
    assert skipped.status_code == 200
    assert skipped.json()["today"]["closed"] is False
    clock["day"] += timedelta(days=1)
    unfinished = client.get("/api/transformation", params={"on": on(clock)})
    assert unfinished.status_code == 200, unfinished.text
    assert unfinished.json()["promises_kept"] == 0
    assert unfinished.json()["prior_closed_on"] is None
    goal = unfinished.json()["today"]["groups"][0]["commitments"][0]
    done = client.post(
        f"/api/transformation/today/commitments/{goal['id']}/toggle",
        params={"on": on(clock)},
    )
    assert done.status_code == 200
    assert done.json()["today"]["closed"] is False
    finished_on = on(clock)
    clock["day"] += timedelta(days=1)
    finished = client.get("/api/transformation", params={"on": on(clock)})
    assert finished.status_code == 200, finished.text
    payload = finished.json()
    assert payload["today"]["closed"] is False
    assert payload["promises_kept"] == 1
    assert payload["prior_closed_on"] == finished_on
    kept = next(item for item in payload["year"] if item["date"] == finished_on)
    assert kept["closed"] is True
    assert kept["intensity"] >= 1


def test_a_day_is_light_until_every_goal_is_done(client, clock):
    register(client, email="goals@example.com")
    body = start(client, clock)
    first = body["today"]["groups"][0]["commitments"][0]
    one = client.post(
        f"/api/transformation/today/commitments/{first['id']}/toggle",
        params={"on": on(clock)},
    )
    assert one.status_code == 200
    today = next(item for item in one.json()["year"] if item["today"])
    assert today["closed"] is False
    assert today["intensity"] == 1
    by_identity = {item["identity_id"]: item["intensity"] for item in today["identities"]}
    assert by_identity["disciplined"] == 2
    assert by_identity["healthy"] == 0
    second = one.json()["today"]["groups"][1]["commitments"][0]
    both = client.post(
        f"/api/transformation/today/commitments/{second['id']}/toggle",
        params={"on": on(clock)},
    )
    assert both.status_code == 200
    today = next(item for item in both.json()["year"] if item["today"])
    assert today["intensity"] == 2


def test_change_direction_keeps_promises_kept_and_old_days(client, clock):
    register(client)
    body = start(client, clock)
    for _ in range(3):
        body = settle(client, clock, body)
    opened = client.get("/api/transformation", params={"on": on(clock)}).json()
    assert opened["promises_kept"] == 3
    assert len(titles(opened, "healthy")) == 1
    changed = client.put(
        "/api/transformation",
        params={"on": on(clock)},
        json=selections(
            ("disciplined", "master-deep-work"),
            ("healthy", "improve-my-sleep"),
        ),
    )
    assert changed.status_code == 200, changed.text
    payload = changed.json()
    assert payload["promises_kept"] == 3
    assert len(titles(payload, "healthy")) == 1
    assert len(titles(payload, "disciplined")) == 1
    closed_days = [item for item in payload["year"] if item["intensity"] == 2]
    assert len(closed_days) == 3


def test_phase_advances_after_fourteen_showed_up_days(client, clock):
    register(client)
    body = start(client, clock, selections(("disciplined", "master-deep-work"),))
    for _ in range(14):
        body = settle(client, clock, body)
    disciplined = body["selections"][0]
    assert disciplined["phase_name"] == "Consistency"
    assert disciplined["stage_name"] == "Consistency"
    assert disciplined["day_in_phase"] == 1
    assert disciplined["phases"][0]["status"] == "complete"
    assert disciplined["phases"][1]["status"] == "current"
    assert body["promises_kept"] == 14
    assert body["progress"]["next_phase_name"] == "Focus"
    tomorrow = [item["title"] for item in body["tomorrow"]]
    assert tomorrow == [
        "15 minutes of uninterrupted work",
        "Sit down at the same time and work for 25 minutes",
    ]


def test_tomorrow_is_the_next_day_and_a_gap_keeps_the_path(client, clock):
    register(client, email="return@example.com")
    body = start(client, clock, selections(("disciplined", "master-deep-work"),))
    assert body["prior_closed_on"] is None
    closed = settle(client, clock, body)
    assert closed["today"]["date"] == "2026-09-27"
    assert closed["today"]["closed"] is False
    assert closed["prior_closed_on"] == "2026-09-26"
    assert closed["promises_kept"] == 1
    assert [item["title"] for item in closed["tomorrow"]] == ["15 minutes of uninterrupted work"]
    clock["day"] = date(2026, 9, 29)
    opened = client.get("/api/transformation", params={"on": on(clock)})
    assert opened.status_code == 200, opened.text
    payload = opened.json()
    assert payload["prior_closed_on"] == "2026-09-26"
    assert payload["today"]["closed"] is False
    assert payload["promises_kept"] == 1
    assert payload["selections"][0]["day_in_phase"] == 2
    assert payload["selections"][0]["stage_name"] == "Foundation"


def test_reset_clears_the_transformation_and_leaves_the_account(client, clock, db):
    register(client)
    start(client, clock)
    user = db.scalar(select(User).where(User.email == "ada@example.com"))
    assert user is not None
    user.role = Role.admin
    db.commit()
    removed = client.delete("/api/transformation")
    assert removed.status_code == 204
    missing = client.get("/api/transformation", params={"on": on(clock)})
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Transformation has not started."
    assert client.get("/api/me").status_code == 200


def test_reset_is_admin_only(client, clock):
    register(client)
    start(client, clock)
    removed = client.delete("/api/transformation")
    assert removed.status_code == 404
    kept = client.get("/api/transformation", params={"on": on(clock)})
    assert kept.status_code == 200


def test_date_must_be_near_today(client, clock):
    register(client)
    start(client, clock)
    far = client.get("/api/transformation", params={"on": "2020-01-01"})
    assert far.status_code == 422
    client.cookies.clear()
    assert client.get("/api/catalog").status_code == 401
    assert client.get("/api/transformation", params={"on": on(clock)}).status_code == 401
