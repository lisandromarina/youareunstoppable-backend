from datetime import date, datetime, timedelta, timezone

import pytest

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
    closed = client.post("/api/transformation/today/showed-up", params={"on": current})
    assert closed.status_code == 200, closed.text
    clock["day"] += timedelta(days=1)
    return closed.json()


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


def test_only_due_commitments_appear_and_the_schedule_can_move(client, clock):
    register(client)
    body = start(client, clock, selections(("disciplined", "master-deep-work"),))
    assert titles(body, "disciplined") == ["15 minutes of uninterrupted work"]
    upcoming = {item["title"]: item for item in body["today"]["coming_up"]}
    assert "No phone during the first hour of work" in upcoming
    assert "Open the work and stay with it for 15 minutes" in upcoming
    phone = upcoming["No phone during the first hour of work"]
    moved = client.post(
        f"/api/transformation/commitments/{phone['planned_commitment_id']}/schedule",
        params={"on": on(clock)},
        json={"weekdays": [5]},
    )
    assert moved.status_code == 200, moved.text
    assert "No phone during the first hour of work" in titles(moved.json(), "disciplined")
    focus = upcoming["Open the work and stay with it for 15 minutes"]
    rejected = client.post(
        f"/api/transformation/commitments/{focus['planned_commitment_id']}/schedule",
        params={"on": on(clock)},
        json={"weekdays": [0, 2]},
    )
    assert rejected.status_code == 422
    clock["day"] = date(2026, 9, 28)
    monday = client.get("/api/transformation", params={"on": on(clock)})
    assert monday.status_code == 200
    monday_titles = titles(monday.json(), "disciplined")
    assert "15 minutes of uninterrupted work" in monday_titles
    assert "Open the work and stay with it for 15 minutes" in monday_titles
    assert "No phone during the first hour of work" not in monday_titles
    body = settle(client, clock, monday.json())
    clock["day"] = date(2026, 10, 5)
    following = client.get("/api/transformation", params={"on": on(clock)})
    assert following.status_code == 200
    assert "No phone during the first hour of work" not in titles(following.json(), "disciplined")
    assert body["promises_kept"] == 1
    assert body["progress"]["commitments_done"] == 2
    assert body["progress"]["commitments_total"] == 2


def test_replace_skip_and_showed_up(client, clock):
    register(client)
    body = start(client, clock, selections(("healthy", "move-daily"),))
    commitment = body["today"]["groups"][0]["commitments"][0]
    early = client.post("/api/transformation/today/showed-up", params={"on": on(clock)})
    assert early.status_code == 409
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
    closed = skipped.json()
    assert closed["today"]["groups"][0]["commitments"][0]["status"] == "skipped"
    showed = client.post("/api/transformation/today/showed-up", params={"on": on(clock)})
    assert showed.status_code == 200
    assert showed.json()["today"]["closed"] is True
    assert showed.json()["promises_kept"] == 1
    today = next(item for item in showed.json()["year"] if item["today"])
    assert today["closed"] is True
    assert today["intensity"] == 0
    again = client.post("/api/transformation/today/showed-up", params={"on": on(clock)})
    assert again.status_code == 409


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


def test_reset_clears_the_transformation_and_leaves_the_account(client, clock):
    register(client)
    start(client, clock)
    removed = client.delete("/api/transformation")
    assert removed.status_code == 204
    missing = client.get("/api/transformation", params={"on": on(clock)})
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Transformation has not started."
    assert client.get("/api/me").status_code == 200


def test_date_must_be_near_today(client, clock):
    register(client)
    start(client, clock)
    far = client.get("/api/transformation", params={"on": "2020-01-01"})
    assert far.status_code == 422
    client.cookies.clear()
    assert client.get("/api/catalog").status_code == 401
    assert client.get("/api/transformation", params={"on": on(clock)}).status_code == 401
