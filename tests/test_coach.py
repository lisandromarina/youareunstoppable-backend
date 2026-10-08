import json
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.core.config import get_settings
from src.models.subscription import Plan
from src.models.transformation import PlannedCommitment, PlannedImplementation, Transformation
from src.models.user import User
from tests.test_transformation import on, register, selections, start, titles


@pytest.fixture
def clock(monkeypatch):
    state = {"day": date(2026, 9, 26)}

    def fake_now() -> datetime:
        current = state["day"]
        return datetime(current.year, current.month, current.day, 15, tzinfo=timezone.utc)

    monkeypatch.setattr("src.services.transformation.utcnow", fake_now)
    return state


def _block_network(*_args, **_kwargs):
    raise AssertionError("network")


@pytest.fixture
def coach_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_api_key", "sk-test")
    monkeypatch.setattr(settings, "ai_model", "gpt-test")
    monkeypatch.setattr("src.services.ai.requests.post", _block_network)


def grant(db, email="ada@example.com", plan=Plan.pro, status="active"):
    db.expire_all()
    user = db.scalar(select(User).options(joinedload(User.subscription)).where(User.email == email))
    assert user is not None
    user.subscription.plan = plan
    user.subscription.subscription_status = status
    db.commit()


def mock_reply(monkeypatch, payload):
    monkeypatch.setattr("src.services.coach.complete", lambda *_args, **_kwargs: json.dumps(payload))


def say(client, clock, monkeypatch, payload, message="I want to start small."):
    mock_reply(monkeypatch, payload)
    response = client.post(
        "/api/coach/messages",
        params={"on": on(clock)},
        json={"message": message},
    )
    return response


def accept(client, clock):
    return client.post("/api/coach/apply", params={"on": on(clock)})


def daily(title, position, identity="disciplined", reason="Start with something you can finish."):
    return {
        "identity_id": identity,
        "objective": "Show up",
        "title": title,
        "recurrence": "daily",
        "position": position,
        "reason": reason,
    }


def once(title, position, due, identity="disciplined"):
    return {
        "identity_id": identity,
        "objective": "Take the step",
        "title": title,
        "recurrence": "once",
        "due_on": due,
        "position": position,
        "reason": "This only needs to happen once.",
    }


def plan(*goals, reply="Start with the smallest step."):
    return {
        "reply": reply,
        "context": {},
        "proposal": {
            "type": "plan",
            "rationale": "The work should be small enough to finish.",
            "goals": list(goals),
        },
    }


def context_of(db):
    db.expire_all()
    row = db.scalar(select(Transformation))
    assert row is not None
    return row


def settle(client, clock, how="all"):
    current = on(clock)
    body = client.get("/api/transformation", params={"on": current})
    assert body.status_code == 200, body.text
    kept = False
    for group in body.json()["today"]["groups"]:
        for commitment in group["commitments"]:
            if commitment["status"] != "open":
                continue
            if how == "none" or (how == "one" and kept):
                skipped = client.post(
                    f"/api/transformation/today/commitments/{commitment['id']}/skip",
                    params={"on": current},
                )
                assert skipped.status_code == 200, skipped.text
                continue
            toggled = client.post(
                f"/api/transformation/today/commitments/{commitment['id']}/toggle",
                params={"on": current},
            )
            assert toggled.status_code == 200, toggled.text
            kept = True
    closed = client.post("/api/transformation/today/showed-up", params={"on": current})
    assert closed.status_code == 200, closed.text
    clock["day"] += timedelta(days=1)
    return closed.json()


def open_titles(client, clock, identity="disciplined"):
    response = client.get("/api/transformation", params={"on": on(clock)})
    assert response.status_code == 200, response.text
    return titles(response.json(), identity)


def begin(client, clock, db, status="active"):
    register(client)
    grant(db, status=status)
    start(client, clock, selections(("disciplined", "master-deep-work"),))


@pytest.mark.parametrize("status", ["active", "trialing", "past_due"])
def test_entitled_statuses_can_call_the_coach(client, clock, db, coach_key, monkeypatch, status):
    begin(client, clock, db, status=status)
    response = say(client, clock, monkeypatch, {"reply": "Start with the bed.", "proposal": None})
    assert response.status_code == 200, response.text
    assert response.json()["reply"] == "Start with the bed."
    assert response.json()["proposal"] is None


@pytest.mark.parametrize("plan,status", [(Plan.free, "active"), (Plan.pro, "canceled"), (Plan.pro, "unpaid")])
def test_coach_rejects_anyone_who_is_not_pro(client, clock, db, coach_key, plan, status):
    register(client)
    grant(db, plan=plan, status=status)
    start(client, clock, selections(("disciplined", "master-deep-work"),))
    response = client.post(
        "/api/coach/messages",
        params={"on": on(clock)},
        json={"message": "I want a coach."},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Coach is part of Pro."
    denied = client.get("/api/coach", params={"on": on(clock)})
    assert denied.status_code == 403


def test_missing_key_is_unavailable_and_apply_does_not_need_it(client, clock, db, coach_key, monkeypatch):
    begin(client, clock, db)
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_api_key", "")
    missing = client.post(
        "/api/coach/messages",
        params={"on": on(clock)},
        json={"message": "Hello"},
    )
    assert missing.status_code == 503
    assert missing.json()["detail"] == "Coach is not configured."

    monkeypatch.setattr(settings, "ai_api_key", "sk-test")
    proposed = say(client, clock, monkeypatch, plan(daily("Make the bed", 1)))
    assert proposed.status_code == 200, proposed.text
    monkeypatch.setattr(settings, "ai_api_key", "")
    applied = accept(client, clock)
    assert applied.status_code == 200, applied.text
    assert titles(applied.json(), "disciplined") == ["Make the bed"]


def test_thread_reopens_the_same_conversation(client, clock, db, coach_key, monkeypatch):
    begin(client, clock, db)
    sent = say(
        client,
        clock,
        monkeypatch,
        plan(daily("Make the bed", 1)),
        message="I can make the bed.",
    )
    assert sent.status_code == 200, sent.text
    thread = client.get("/api/coach", params={"on": on(clock)})
    assert thread.status_code == 200, thread.text
    body = thread.json()
    assert body["transcript"] == [
        {"role": "user", "content": "I can make the bed."},
        {"role": "coach", "content": "Start with the smallest step."},
    ]
    assert body["proposal"]["goals"][0]["title"] == "Make the bed"


def test_mocked_reply_can_mix_once_and_daily_goals_on_two_identities(client, clock, db, coach_key, monkeypatch):
    register(client)
    grant(db)
    start(client, clock)
    response = say(
        client,
        clock,
        monkeypatch,
        plan(
            daily("Make the bed", 1, reason="Start with the bed."),
            once("Write the business name", 2, on(clock)),
            daily("Walk for 10 minutes", 1, identity="healthy"),
            reply="Start small. The name can wait until the bed is done.",
        ),
    )
    assert response.status_code == 200, response.text
    goals = response.json()["proposal"]["goals"]
    identities = {item["identity_id"] for item in goals}
    recurrences = {item["recurrence"] for item in goals}
    assert identities == {"disciplined", "healthy"}
    assert recurrences == {"daily", "once"}
    applied = accept(client, clock)
    assert applied.status_code == 200, applied.text
    assert "Make the bed" in titles(applied.json(), "disciplined")
    assert "Write the business name" in titles(applied.json(), "disciplined")
    assert titles(applied.json(), "healthy") == ["Walk for 10 minutes"]
    row = context_of(db)
    assert row.origin.value == "adaptive"
    assert row.rationale == "The work should be small enough to finish."


def test_invalid_model_output_writes_nothing(client, clock, db, coach_key, monkeypatch):
    begin(client, clock, db)
    for payload in ("not json", json.dumps({"reply": "No.", "proposal": {"type": "plan", "goals": [{"recurrence": "yearly"}]}})):
        mock_reply(monkeypatch, payload if payload.startswith("{") or payload == "not json" else payload)
        monkeypatch.setattr("src.services.coach.complete", lambda *_args, **_kwargs: payload)
        response = client.post(
            "/api/coach/messages",
            params={"on": on(clock)},
            json={"message": "Change the plan."},
        )
        assert response.status_code == 422
        row = context_of(db)
        assert row.origin.value == "catalog"
        assert row.context is None
        assert row.rationale is None


def test_a_sixth_goal_is_trimmed_and_the_quick_win_stays(client, clock, db, coach_key, monkeypatch):
    begin(client, clock, db)
    goals = [daily("Make the bed", 1)]
    goals.extend(once(f"Step {position}", position, on(clock)) for position in range(2, 7))
    response = say(client, clock, monkeypatch, plan(*goals))
    assert response.status_code == 200, response.text
    proposed = response.json()["proposal"]["goals"]
    assert len(proposed) == 5
    assert proposed[0]["title"] == "Make the bed"
    assert all(item["title"] != "Step 6" for item in proposed)


def test_once_goals_are_due_only_on_their_date_and_count_toward_the_streak(client, clock, db, coach_key, monkeypatch):
    begin(client, clock, db)
    tomorrow = (clock["day"] + timedelta(days=1)).isoformat()
    created = say(
        client,
        clock,
        monkeypatch,
        plan(
            once("Write the name", 1, on(clock)),
            daily("Make the bed", 2),
            daily("Read 10 pages", 3),
            once("Open the account", 4, tomorrow),
        ),
    )
    assert created.status_code == 200, created.text
    applied = accept(client, clock)
    assert applied.status_code == 200, applied.text
    assert titles(applied.json(), "disciplined") == ["Write the name", "Make the bed"]
    assert "Open the account" not in titles(applied.json(), "disciplined")
    settle(client, clock, how="one")
    assert open_titles(client, clock) == ["Make the bed", "Read 10 pages", "Open the account"]
    later = client.get("/api/transformation", params={"on": on(clock)})
    assert "Write the name" not in titles(later.json(), "disciplined")


def test_streak_prefix_grows_and_resets(client, clock, db, coach_key, monkeypatch):
    begin(client, clock, db)
    habits = [daily(title, position) for position, title in enumerate(
        ["Make the bed", "Read 10 pages", "Walk 20 minutes", "Prepare lunch", "Create a video"],
        start=1,
    )]
    assert accept(client, clock).status_code == 409
    created = say(client, clock, monkeypatch, plan(*habits))
    assert created.status_code == 200, created.text
    assert accept(client, clock).status_code == 200
    assert open_titles(client, clock) == ["Make the bed"]

    settle(client, clock, how="all")
    assert open_titles(client, clock) == ["Make the bed", "Read 10 pages"]
    settle(client, clock, how="all")
    assert open_titles(client, clock) == ["Make the bed", "Read 10 pages", "Walk 20 minutes"]
    settle(client, clock, how="none")
    assert open_titles(client, clock) == ["Make the bed"]

    settle(client, clock, how="all")
    clock["day"] += timedelta(days=1)
    assert open_titles(client, clock) == ["Make the bed"]


def test_several_completions_increment_the_streak_once(client, clock, db, coach_key, monkeypatch):
    begin(client, clock, db)
    say(
        client,
        clock,
        monkeypatch,
        plan(*[daily(title, position) for position, title in enumerate(["Make the bed", "Read 10 pages", "Walk"], start=1)]),
    )
    assert accept(client, clock).status_code == 200
    settle(client, clock, how="all")
    assert open_titles(client, clock) == ["Make the bed", "Read 10 pages"]
    settle(client, clock, how="all")
    assert open_titles(client, clock) == ["Make the bed", "Read 10 pages", "Walk"]
    row = context_of(db)
    path = next(item for item in row.paths if item.identity_id == "disciplined")
    assert path.commitment_streak == 2


def test_only_skips_reset_the_streak(client, clock, db, coach_key, monkeypatch):
    begin(client, clock, db)
    say(client, clock, monkeypatch, plan(daily("Make the bed", 1), daily("Read 10 pages", 2)))
    accept(client, clock)
    settle(client, clock, how="none")
    assert open_titles(client, clock) == ["Make the bed"]
    path = next(item for item in context_of(db).paths if item.identity_id == "disciplined")
    assert path.commitment_streak == 0


def test_today_adjustment_does_not_change_future_goals(client, clock, db, coach_key, monkeypatch):
    begin(client, clock, db)
    say(client, clock, monkeypatch, plan(daily("Read 10 pages", 1), daily("Walk 20 minutes", 2)))
    accept(client, clock)
    adjusted = say(
        client,
        clock,
        monkeypatch,
        {
            "reply": "Read five pages. Leave the walk for a day you have it.",
            "proposal": {
                "type": "today",
                "goals": [daily("Read 5 pages", 1)],
            },
        },
    )
    assert adjusted.status_code == 200, adjusted.text
    applied = accept(client, clock)
    assert applied.status_code == 200, applied.text
    assert titles(applied.json(), "disciplined") == ["Read 5 pages"]
    db.expire_all()
    stored = db.scalar(select(PlannedImplementation).where(PlannedImplementation.title == "Read 10 pages"))
    assert stored is not None
    assert db.scalar(select(PlannedImplementation).where(PlannedImplementation.title == "Read 5 pages")) is None
    clock["day"] += timedelta(days=1)
    assert open_titles(client, clock) == ["Read 10 pages"]


def test_full_list_can_show_five_goals_on_a_short_streak(client, clock, db, coach_key, monkeypatch):
    begin(client, clock, db)
    habits = [daily(f"Goal {position}", position) for position in range(1, 6)]
    say(client, clock, monkeypatch, plan(*habits))
    accept(client, clock)
    assert open_titles(client, clock) == ["Goal 1"]
    say(
        client,
        clock,
        monkeypatch,
        {
            "reply": "All five are yours today.",
            "proposal": {"type": "today", "goals": habits},
        },
        message="Give me the full list.",
    )
    applied = accept(client, clock)
    assert applied.status_code == 200, applied.text
    assert titles(applied.json(), "disciplined") == [f"Goal {position}" for position in range(1, 6)]
    clock["day"] += timedelta(days=1)
    assert open_titles(client, clock) == ["Goal 1"]


def test_context_keeps_stated_facts_and_drops_the_rest(client, clock, db, coach_key, monkeypatch):
    begin(client, clock, db)
    first = say(
        client,
        clock,
        monkeypatch,
        {
            "reply": "Twenty minutes is enough.",
            "context": {
                "idea": "I want to start a business that gives me financial freedom.",
                "statement": "I build this in small steps.",
                "skills": ["writing"],
                "constraints": ["Only 20 minutes on weekdays"],
                "preferences": ["Prefer working in the morning"],
                "availability": {"weekday_minutes": 20, "weekend_minutes": 60, "secret": 1},
                "invented": "runs marathons",
            },
            "proposal": None,
        },
        message="I want to start a business. I can write. I only have 20 minutes on weekdays and I prefer mornings.",
    )
    assert first.status_code == 200, first.text
    stored = context_of(db).context
    assert stored["idea"].startswith("I want to start a business")
    assert stored["statement"] == "I build this in small steps."
    assert stored["skills"] == ["writing"]
    assert stored["constraints"] == ["Only 20 minutes on weekdays"]
    assert stored["preferences"] == ["Prefer working in the morning"]
    assert stored["availability"] == {"weekday_minutes": 20, "weekend_minutes": 60}
    assert "invented" not in stored
    assert "obligations" not in stored

    second = say(client, clock, monkeypatch, {"reply": "Use the morning.", "context": {}, "proposal": None})
    assert second.status_code == 200, second.text
    again = context_of(db).context
    assert again["skills"] == ["writing"]
    assert again["constraints"] == ["Only 20 minutes on weekdays"]
    assert again["preferences"] == ["Prefer working in the morning"]
    assert again["availability"]["weekday_minutes"] == 20
    assert again["idea"] == stored["idea"]
    assert again["statement"] == stored["statement"]
    shown = client.get("/api/transformation", params={"on": on(clock)})
    assert shown.json()["statement"] == "I build this in small steps."


def test_a_one_time_goal_that_does_not_fit_moves_forward(client, clock, db, coach_key, monkeypatch):
    begin(client, clock, db)
    goals = [daily("Make the bed", 1)]
    goals.extend(once(f"Step {position}", position, on(clock)) for position in range(2, 6))
    say(client, clock, monkeypatch, plan(*goals))
    assert accept(client, clock).status_code == 200
    db.expire_all()
    phase_id = db.scalar(
        select(PlannedCommitment.phase_id).where(PlannedCommitment.recurrence == "once")
    )
    db.add(
        PlannedCommitment(
            phase_id=phase_id,
            position=6,
            unlock_streak=0,
            objective="Take the step",
            recurrence="once",
            weekdays=[],
            due_on=clock["day"],
            reason="One more step.",
        )
    )
    db.flush()
    extra = db.scalar(select(PlannedCommitment).where(PlannedCommitment.position == 6))
    extra.implementations.append(PlannedImplementation(position=0, title="Step 6", is_default=True))
    db.commit()
    opened = client.get("/api/transformation", params={"on": on(clock)})
    assert opened.status_code == 200, opened.text
    shown = titles(opened.json(), "disciplined")
    assert shown[0] == "Make the bed"
    assert "Step 6" not in shown
    assert len(shown) == 5
    db.expire_all()
    slid = db.scalar(select(PlannedCommitment).where(PlannedCommitment.position == 6))
    assert slid.due_on.isoformat() == (clock["day"] + timedelta(days=1)).isoformat()


def test_changing_direction_copies_the_catalog_again(client, clock, db, coach_key, monkeypatch):
    begin(client, clock, db)
    say(client, clock, monkeypatch, plan(daily("Make the bed", 1)))
    accept(client, clock)
    changed = client.put(
        "/api/transformation",
        params={"on": on(clock)},
        json=selections(("disciplined", "build-a-morning-routine"),),
    )
    assert changed.status_code == 200, changed.text
    assert "Make the bed" not in titles(changed.json(), "disciplined")
    row = context_of(db)
    assert row.origin.value == "catalog"
    assert all(item.catalog_commitment_id is not None for path in row.paths for phase in path.phases for item in phase.commitments)
