import json
import logging
from datetime import date, timedelta
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.domain.catalog import find_identity
from src.models.transformation import CommitmentStatus, DayStatus, Transformation
from src.models.user import User
from src.schemas.coach import (
    CoachMessageResponse,
    CoachProposalResponse,
    CoachThreadResponse,
    CoachTurnResponse,
)
from src.schemas.transformation import TransformationResponse
from src.services.ai import complete
from src.services.billing import pro_entitled
from src.services.errors import DomainError
from src.services.transformation import (
    _as_date,
    _check_date,
    _current_commitments,
    _default_implementation,
    _ensure_today,
    _find_day,
    _finish,
    _load,
    _path_for,
    _phase_at,
    _status,
    install_coach_plan,
    install_today_override,
)

logger = logging.getLogger(__name__)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

TRANSCRIPT_LIMIT = 8
FACT_LISTS = ("constraints", "preferences", "skills", "obligations")
KEPT_KEYS = (
    "idea",
    "statement",
    "constraints",
    "preferences",
    "skills",
    "obligations",
    "availability",
    "transcript",
    "proposal",
    "today_override",
)

SYSTEM_PROMPT = """You are the coach inside YouAreUnstoppable. You are direct, short, and serious. You are not a cheerleader and you do not lecture.

Return one JSON object and nothing else.

- reply: answer the person. A greeting is one or two short sentences. When they ask what to eat, train, or do today, name the meals or actions. Do not stop at a generic line such as "focus on protein." No praise, no guilt, no emoji, no quotes, no exclamation. Never say you will not set a goal. Never mention dates, validation, or why a goal was not saved.
- context: facts the user actually said in this conversation. Omit anything they did not say. Allowed keys: idea, statement, constraints, preferences, skills, obligations, availability. availability may contain only weekday_minutes and weekend_minutes. Lists are short strings of their words. Do not invent facts. Leave out keys you are not updating.
- proposal: null unless the user is asking to change the plan or today. A greeting, a question, or small talk is not a request for a plan. Answer it in reply and set proposal to null. Do not create a proposal just to keep the conversation moving. Otherwise, return an object.

WHEN NOT TO PROPOSE

Answer like a coach. Do not attach a plan to every message.

Set proposal to null when the user:
- says hello, hi, hey, or another greeting
- asks who you are, what you do, or how the product works
- asks a question that does not ask you to change today's goals or the lasting plan
- is still talking and has not asked for a goal yet

A request for what to eat, what to train, or how to do today's goal is still answered in full. Put the concrete recommendation in the reply. Leave proposal null until they ask to add it, use it today, or change the lasting plan.

A hello gets a short reply and nothing else. Do not welcome them with a new plan. Do not repeat their current goals back as a proposal.

A proposal has type "plan" or "today", an optional rationale, and goals.

Use "plan" only when the user wants a lasting change to the goals themselves. It replaces unfinished future goals.

Use "today" when they want today's execution of a goal that already exists: a meal, a workout, a smaller version, or the full list. Copy identity_id and position from today_goals for the goal they mean. Catalog goals often start at position 0. Do not assume the first goal is position 1. Copy recurrence from that same goal. Put the concrete action in the title. Do not create a new goal. Do not change the recurrence to once. A new once goal is only a lasting step that happens on one date, and it must include due_on.

If they explicitly ask for every goal today, type is "today" and the goals are the existing ones, up to 5, even when the streak is short.

Each goal has identity_id, objective, title, recurrence, position, and optional reason, due_on, weekdays, times_per_week, month_day.

recurrence is daily, times_per_week, weekly, monthly, or once. Do not choose it from the identity name.

once requires due_on as YYYY-MM-DD and happens on that date only. A once goal without due_on is discarded.
daily is the habit.
weekly requires weekdays with exactly one day.
times_per_week requires times_per_week and that many weekdays.
An action that happens when a cue appears is daily. Do not mark it weekly or times_per_week unless the weekdays are included.
Monday is 0.
monthly requires month_day, an integer from 1 to 28.
A monthly goal without month_day is invalid.
"This month" is monthly with month_day. It is not once.

position starts at 1. Position 1 is the smallest meaningful action they can finish.

At most 5 goals. One plan may mix daily goals and once goals.

Do not add a project, business, channel, account, or other commitment they did not ask for.

One missed day is not a pattern. Mention a repeated miss only when several recent closed days show zero completed goals.

Never call the user unmotivated, inconsistent, lazy, or anything like it.


THREE KINDS OF HELP

1. Goal. The lasting objective already on their path. Change it only when they ask for a lasting change. That is type "plan".

2. Today's implementation. A concrete way to do an existing goal today, such as prepare chicken, rice, and vegetables. This is not a new goal. When they ask to add it, use it, or make it today's action, return type "today" for that existing goal and say what they will do.

3. Advice. A recommendation that does not need to be stored: the rest of the day's meals, a substitute if they lack an ingredient, what to eat after training. Put it in the reply. proposal is null.

Do not refuse a reasonable request because it is not a new goal. If it can be advice or today's implementation, do that.

Be specific. Name the meal, the food, or the action. Give the recommendation first, then one alternative if they need it. If they say what they have, use that. Do not invent money, accounts, or deadlines they did not state. A meal or session that fits their direction is not an invented commitment.


CONVERSATION AND GOAL SELECTION

The user's latest message is the highest-priority signal for what they want from the coach.

Distinguish between:

- OUTCOME: what the user wants to achieve.
- ACTION: something the user actually does that moves them toward the outcome.
- REFLECTION/PLANNING: thinking about, writing down, or reviewing an outcome.

The coach's job is to turn intentions into meaningful behavior, not to make the user repeatedly define or restate their intentions.

If the user already stated a target, outcome, identity, or desired result, do not turn that same information into a goal that merely asks them to write, repeat, remember, state, or acknowledge it.

A goal should normally describe something the user can actually DO.

Bad goal:
- Write down your target.
- Remember your goal.
- Think about your goal.
- Write down what you want to achieve.

Better goal:
- Take a concrete action that moves the user toward the desired outcome.
- Practice the behavior required by the user's chosen direction.
- Complete a specific action that advances the user's current objective.

The appropriate action depends on the user's identity, direction, existing goals, constraints, and conversation. Do not assume the same action applies to every identity.


REJECTED PROPOSALS

If the user says they want "another goal", "a different goal", "something else", "that's not useful", "I already know that", or otherwise rejects the current proposal:

- Do not repeat the rejected goal.
- Do not defend the rejected goal.
- Do not restate the same goal using different wording.
- Do not turn the same underlying action into another title.
- Replace it with a genuinely different actionable goal.
- Prefer a concrete behavior that moves the user toward their chosen identity or direction.
- If an important fact is required to create a useful alternative, ask one short question instead of repeating the previous goal.

A rejected proposal is no longer valid for the next response unless the user explicitly changes their mind.


USE THE CONVERSATION, NOT JUST THE CURRENT PLAN

Before generating a proposal, inspect the user's latest messages and the existing plan.

The coach must use information already provided by the user.

If the user says they already know, understand, completed, or rejected something, do not propose that same thing again unless they explicitly ask for it.

The coach should adapt to the user's actual request rather than mechanically continuing the previous plan.


TARGETS ARE NOT TASKS

An outcome or target is not automatically a task.

Do not create a goal whose only purpose is to document, repeat, or acknowledge an outcome that the user already knows.

Instead, identify a meaningful behavior that can move the user toward that outcome.

Do not invent quantities, deadlines, schedules, or commitments that the user has not provided.

For example, if the user has a target but has not specified an amount, frequency, or method for acting toward it, ask for the missing information when it is necessary to create a useful goal.


ADAPT TO THE IDENTITY

The same coaching logic applies to every identity and direction.

Do not hard-code specific behaviors for financial, health, discipline, proactive, or any other identity.

First understand:

1. What the user is trying to become or accomplish.
2. What they are currently doing.
3. What action would meaningfully move them forward.
4. What constraints they have mentioned.
5. What they have already rejected or completed.

Then propose the smallest meaningful action that fits that context.

The identity determines the direction.
The user's situation determines the action.


PROPOSAL QUALITY CHECK

Before returning a proposal, silently check:

1. Is this something the user can actually DO?
2. Is it meaningfully connected to their identity or desired outcome?
3. Is it different from any goal they just rejected?
4. Is it different from something they already said they understand or completed?
5. Is it specific enough to complete?
6. Is it meaningful rather than administrative?
7. Am I inventing money, an account, or a deadline they never stated? A specific meal or session that fits their direction is allowed.
8. Does it respect the user's stated constraints?
9. Is position 1 the smallest meaningful action?
10. Does it fit the identity and direction they actually chose?

If any answer fails, do not propose that goal. Ask for the missing information or choose a better existing goal.


PREFER ACTION OVER DOCUMENTATION

Prefer the smallest meaningful action over an action that merely documents, labels, records, or restates the user's goal.

The coach exists to help the user act.

Do not create work for the user simply so the coach can say that something was added to the plan.

The product document below is how YouAreUnstoppable works. Use it when they ask about the product. The rules above still decide whether a proposal is allowed. Do not quote the document. Do not mention that you were given a document.
"""

_PRODUCT_PATH = Path(__file__).resolve().parents[2] / "docs" / "product.md"


def _system_prompt() -> str:
    try:
        product = _PRODUCT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        logger.warning("Coach could not read %s", _PRODUCT_PATH)
        return SYSTEM_PROMPT
    return f"{SYSTEM_PROMPT}\n\nPRODUCT\n\n{product}"


def load_thread(db: Session, user: User, on: date) -> CoachThreadResponse:
    _require_pro(user)
    transformation = _open_transformation(db, user, on)
    db.commit()
    db.refresh(transformation)
    context = transformation.context if isinstance(transformation.context, dict) else {}
    return CoachThreadResponse(
        transcript=_public_transcript(context.get("transcript")),
        proposal=_public_proposal(context.get("proposal")),
    )


def send_message(db: Session, user: User, on: date, message: str) -> CoachMessageResponse:
    _require_pro(user)
    settings = get_settings()
    if not settings.ai_api_key.strip():
        raise DomainError(503, "Coach is not configured.")
    transformation = _open_transformation(db, user, on)
    text = message.strip()
    if not text:
        raise DomainError(422, "Write a message first.")
    try:
        messages = _model_messages(transformation, on, text)
        model = settings.ai_model.strip() or "gpt-4o-mini"
        raw = complete(messages, api_key=settings.ai_api_key, model=model)
        logger.info("Coach response: %s", raw)
        try:
            parsed = _interpret(raw, transformation, on)
        except DomainError as exc:
            if exc.status_code != 422:
                raise
            reason = getattr(exc, "reason", exc.detail)
            logger.warning("Coach response rejected: %s", reason)
            raw = complete(
                [
                    *messages,
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": _repair_note(reason)},
                ],
                api_key=settings.ai_api_key,
                model=model,
            )
            logger.info("Coach response: %s", raw)
            parsed = _interpret(raw, transformation, on)
        _remember(transformation, text, parsed)
    except DomainError as exc:
        if exc.status_code == 422:
            logger.warning("Coach response rejected: %s", getattr(exc, "reason", exc.detail))
        db.rollback()
        raise
    _finish(db, user.id, on)
    proposal = parsed["proposal"]
    return CoachMessageResponse(
        reply=parsed["reply"],
        proposal=None if proposal is None else CoachProposalResponse(**_proposal_body(proposal)),
    )


def apply_proposal(db: Session, user: User, on: date) -> TransformationResponse:
    _require_pro(user)
    transformation = _open_transformation(db, user, on)
    context = transformation.context if isinstance(transformation.context, dict) else {}
    stored = context.get("proposal")
    if not isinstance(stored, dict):
        raise DomainError(409, "There is no proposal to apply.")
    try:
        checked = _revalidate(stored, transformation, on)
        if checked["type"] == "plan":
            fresh = dict(transformation.context or {})
            fresh.pop("today_override", None)
            transformation.context = fresh
            install_coach_plan(db, transformation, on, checked["goals"], checked.get("rationale"))
            fresh = dict(transformation.context or {})
            fresh.pop("proposal", None)
            transformation.context = fresh
        else:
            install_today_override(transformation, on, checked["matched"])
    except DomainError:
        db.rollback()
        raise
    return _finish(db, user.id, on)


def _open_transformation(db: Session, user: User, on: date) -> Transformation:
    _check_date(on)
    transformation = _load(db, user.id)
    if transformation is None:
        raise DomainError(404, "Transformation has not started.")
    _ensure_today(db, transformation, on)
    return transformation


def _require_pro(user: User) -> None:
    if not pro_entitled(user):
        raise DomainError(403, "Coach is part of Pro.")


def _model_messages(transformation: Transformation, on: date, message: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": json.dumps(_snapshot(transformation, on, message), default=str)},
    ]


def _snapshot(transformation: Transformation, on: date, message: str) -> dict:
    context = transformation.context if isinstance(transformation.context, dict) else {}
    facts = {key: context[key] for key in ("idea", "statement", *FACT_LISTS, "availability") if key in context}
    identities = []
    streaks = []
    plan = []
    for path in sorted(transformation.paths, key=lambda item: item.sort_order):
        identity = find_identity(path.identity_id)
        identities.append(
            {
                "identity_id": path.identity_id,
                "identity_name": identity.name if identity is not None else path.identity_id,
                "direction_id": path.direction_id,
            }
        )
        streaks.append({"identity_id": path.identity_id, "commitment_streak": path.commitment_streak})
        for planned in _current_commitments(path):
            chosen = _default_implementation(planned)
            plan.append(
                {
                    "identity_id": path.identity_id,
                    "position": planned.position,
                    "objective": planned.objective,
                    "title": chosen.title,
                    "recurrence": planned.recurrence,
                    "due_on": _as_date(planned.due_on).isoformat() if planned.due_on is not None else None,
                    "weekdays": list(planned.weekdays or []),
                    "reason": planned.reason,
                }
            )
    day = _find_day(transformation, on)
    today_goals = []
    if day is not None:
        for item in day.commitments:
            planned = item.planned
            path = item.path
            today_goals.append(
                {
                    "identity_id": path.identity_id if path is not None else None,
                    "position": planned.position if planned is not None else None,
                    "title": item.title_snapshot,
                    "objective": item.objective_snapshot,
                    "status": _status(item.status),
                }
            )
    return {
        "today": on.isoformat(),
        "message": message,
        "identities": identities,
        "streaks": streaks,
        "context": facts,
        "transcript": context.get("transcript") or [],
        "recent_closed_days": _recent_days(transformation),
        "today_goals": today_goals,
        "plan": plan,
    }


def _recent_days(transformation: Transformation) -> list[dict]:
    closed = [
        day
        for day in transformation.days
        if _status(day.status) == DayStatus.closed.value
    ]
    closed.sort(key=lambda item: _as_date(item.calendar_date))
    rows = []
    for day in closed[-7:]:
        commitments = day.commitments
        rows.append(
            {
                "date": _as_date(day.calendar_date).isoformat(),
                "due": len(commitments),
                "done": sum(1 for item in commitments if _status(item.status) == CommitmentStatus.done.value),
                "skipped": sum(
                    1 for item in commitments if _status(item.status) == CommitmentStatus.skipped.value
                ),
            }
        )
    return rows


def _interpret(raw: str, transformation: Transformation, on: date) -> dict:
    payload = _load_json(raw)
    reply = payload.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        raise DomainError(422, "The coach response could not be used.")
    context = payload.get("context")
    if context is not None and not isinstance(context, dict):
        raise DomainError(422, "The coach response could not be used.")
    return {
        "reply": reply.strip()[:1600],
        "context": context if isinstance(context, dict) else {},
        "proposal": _proposal(payload.get("proposal"), transformation, on),
    }


def _load_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DomainError(422, "The coach response could not be used.") from exc
    if not isinstance(payload, dict):
        raise DomainError(422, "The coach response could not be used.")
    return payload


def _proposal(raw: object, transformation: Transformation, on: date) -> dict | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise DomainError(422, "The coach response could not be used.")
    kind = raw.get("type")
    goals_raw = raw.get("goals")
    if kind not in {"plan", "today"} or not isinstance(goals_raw, list) or not goals_raw:
        raise DomainError(422, "The coach response could not be used.")
    goals = [_goal(item, on) for item in goals_raw]
    _check_goals(transformation, goals)
    goals = _trim(goals)
    if kind == "today":
        _match_today(transformation, goals, on)
    rationale = raw.get("rationale")
    cleaned = rationale.strip()[:500] if isinstance(rationale, str) and rationale.strip() else None
    return {"type": kind, "rationale": cleaned, "goals": goals}


def _revalidate(stored: dict, transformation: Transformation, on: date) -> dict:
    kind = stored.get("type")
    raw_goals = stored.get("goals")
    if kind not in {"plan", "today"} or not isinstance(raw_goals, list) or not raw_goals:
        raise DomainError(422, "The coach response could not be used.")
    goals = [_goal(item, on) for item in raw_goals]
    _check_goals(transformation, goals)
    goals = _trim(goals)
    if kind == "today":
        return {"type": "today", "matched": _match_today(transformation, goals, on), "goals": goals}
    rationale = stored.get("rationale")
    cleaned = rationale.strip()[:500] if isinstance(rationale, str) and rationale.strip() else None
    return {"type": "plan", "rationale": cleaned, "goals": goals}


def _check_goals(transformation: Transformation, goals: list[dict]) -> None:
    seen: set[tuple[str, int]] = set()
    for goal in goals:
        if _path_for(transformation, goal["identity_id"]) is None:
            raise DomainError(422, "The coach response could not be used.")
        key = (goal["identity_id"], goal["position"])
        if key in seen:
            raise DomainError(422, "The coach response could not be used.")
        seen.add(key)


def _repair_note(reason: str) -> str:
    return (
        f"That JSON was rejected: {reason}. Return one corrected JSON object. Do not mention this rejection in reply. "
        "If they asked for today's meal, workout, or action on a goal that already exists, use type today, copy identity_id, position, and recurrence from that plan goal, and put the action in the title. "
        "weekly needs weekdays with one day. times_per_week needs times_per_week and that many weekdays. If the action happens when a cue appears, use daily. "
        "A once goal must include due_on as YYYY-MM-DD. "
        "A goal for this month is monthly and must include month_day from 1 to 28. "
        "If they only needed advice, set proposal to null and put the recommendation in reply."
    )


def _unusable(reason: str) -> None:
    error = DomainError(422, "The coach response could not be used.")
    error.reason = reason
    raise error


def _goal(raw: object, on: date) -> dict:
    if not isinstance(raw, dict):
        raise DomainError(422, "The coach response could not be used.")
    identity_id = raw.get("identity_id")
    if not isinstance(identity_id, str) or not identity_id.strip() or len(identity_id.strip()) > 64:
        raise DomainError(422, "The coach response could not be used.")
    recurrence = raw.get("recurrence")
    if recurrence not in {"daily", "times_per_week", "weekly", "monthly", "once"}:
        raise DomainError(422, "The coach response could not be used.")
    position = raw.get("position")
    if isinstance(position, bool) or not isinstance(position, int) or position < 0 or position > 20:
        raise DomainError(422, "The coach response could not be used.")
    due_on = None
    weekdays: list[int] = []
    times_per_week = None
    month_day = None
    if recurrence == "once":
        due_on = _date_value(raw.get("due_on"), on)
    elif recurrence == "weekly":
        days = raw.get("weekdays")
        if not isinstance(days, list) or not days:
            logger.info('Coach kept "%s" as daily because weekly had no weekday', raw.get("title"))
            recurrence = "daily"
        else:
            weekdays = _weekday_values(days, 1)
    elif recurrence == "times_per_week":
        count = raw.get("times_per_week")
        days = raw.get("weekdays")
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or count < 1
            or count > 7
            or not isinstance(days, list)
            or len(days) != count
        ):
            logger.info(
                'Coach kept "%s" as daily because times_per_week had no matching weekdays',
                raw.get("title"),
            )
            recurrence = "daily"
        else:
            weekdays = _weekday_values(days, count)
            times_per_week = count
    elif recurrence == "monthly":
        month = raw.get("month_day")
        if isinstance(month, bool) or not isinstance(month, int) or month < 1 or month > 28:
            _unusable("a monthly goal needs month_day from 1 to 28")
        month_day = month
    return {
        "identity_id": identity_id.strip(),
        "objective": _required_text(raw.get("objective"), 200),
        "title": _required_text(raw.get("title"), 200),
        "recurrence": recurrence,
        "due_on": due_on,
        "weekdays": weekdays,
        "times_per_week": times_per_week,
        "month_day": month_day,
        "position": position,
        "reason": _optional_text(raw.get("reason"), 160),
    }


def _date_value(value: object, on: date) -> date:
    parsed: date | None = None
    if type(value) is date:
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = date.fromisoformat(value[:10])
        except ValueError:
            parsed = None
    if parsed is None:
        _unusable("a one-time goal needs due_on as YYYY-MM-DD")
    if parsed < on - timedelta(days=1) or parsed > on + timedelta(days=366):
        _unusable("due_on must be between yesterday and one year from today")
    return parsed


def _weekday_values(value: object, expected: int) -> list[int]:
    if not isinstance(value, list):
        raise DomainError(422, "The coach response could not be used.")
    try:
        chosen = sorted({int(item) for item in value})
    except (TypeError, ValueError) as exc:
        raise DomainError(422, "The coach response could not be used.") from exc
    if any(day < 0 or day > 6 for day in chosen) or len(chosen) != expected:
        raise DomainError(422, "The coach response could not be used.")
    return chosen


def _required_text(value: object, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainError(422, "The coach response could not be used.")
    return value.strip()[:limit]


def _optional_text(value: object, limit: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DomainError(422, "The coach response could not be used.")
    text = value.strip()
    if not text:
        return None
    return text[:limit]


def _trim(goals: list[dict]) -> list[dict]:
    if len(goals) <= 5:
        return goals
    grouped: dict[str, list[dict]] = {}
    for goal in goals:
        grouped.setdefault(goal["identity_id"], []).append(goal)
    quick: list[dict] = []
    once: list[dict] = []
    repeating: list[dict] = []
    for items in grouped.values():
        ordered = sorted(items, key=lambda item: item["position"])
        quick.append(ordered[0])
        for goal in ordered[1:]:
            if goal["recurrence"] == "once":
                once.append(goal)
            else:
                repeating.append(goal)
    once.sort(key=lambda item: (item["position"], item["identity_id"]))
    repeating.sort(key=lambda item: (item["position"], item["identity_id"]))
    return (quick + once + repeating)[:5]


def _match_today(transformation: Transformation, goals: list[dict], on: date) -> list[dict]:
    day = _find_day(transformation, on)
    matched = []
    for goal in goals[:5]:
        path = _path_for(transformation, goal["identity_id"])
        phase = _phase_at(path, path.current_phase_position) if path is not None else None
        planned = None
        if phase is not None:
            planned = next((item for item in phase.commitments if item.position == goal["position"]), None)
        if planned is None and path is not None and day is not None:
            on_today = [
                item.planned
                for item in day.commitments
                if item.path_id == path.id and item.planned is not None
            ]
            if on_today:
                planned = sorted(on_today, key=lambda item: item.position)[0]
        if planned is None and phase is not None and phase.commitments:
            planned = sorted(phase.commitments, key=lambda item: item.position)[0]
        if planned is None:
            raise DomainError(422, "That proposal does not match the current plan.")
        if planned.position != goal["position"]:
            logger.info(
                'Coach attached "%s" to the goal already on today because position %s is not on the plan',
                goal["title"],
                goal["position"],
            )
        goal["position"] = planned.position
        goal["recurrence"] = planned.recurrence
        goal["due_on"] = _as_date(planned.due_on) if planned.recurrence == "once" and planned.due_on else None
        goal["weekdays"] = list(planned.weekdays or [])
        goal["times_per_week"] = planned.times_per_week
        goal["month_day"] = planned.month_day
        matched.append({"planned_commitment_id": str(planned.id), "title": goal["title"]})
    if not matched:
        raise DomainError(422, "That proposal does not match the current plan.")
    return matched


def _public_transcript(value: object) -> list[CoachTurnResponse]:
    if not isinstance(value, list):
        return []
    turns = []
    for item in value:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "coach"} or not isinstance(content, str) or not content.strip():
            continue
        turns.append(CoachTurnResponse(role=role, content=content.strip()))
    return turns[-TRANSCRIPT_LIMIT:]


def _public_proposal(value: object) -> CoachProposalResponse | None:
    if not isinstance(value, dict):
        return None
    try:
        return CoachProposalResponse.model_validate(value)
    except ValidationError:
        return None


def _remember(transformation: Transformation, message: str, parsed: dict) -> None:
    context = _merge_context(transformation.context, parsed["context"])
    turns = context.get("transcript")
    if not isinstance(turns, list):
        turns = []
    turns = [item for item in turns if isinstance(item, dict)]
    turns.append({"role": "user", "content": message[:2000]})
    turns.append({"role": "coach", "content": parsed["reply"]})
    context["transcript"] = turns[-TRANSCRIPT_LIMIT:]
    proposal = parsed["proposal"]
    if proposal is not None:
        context["proposal"] = _proposal_body(proposal)
    transformation.context = context


def _merge_context(existing: object, update: object) -> dict:
    current = existing if isinstance(existing, dict) else {}
    merged = {key: current[key] for key in KEPT_KEYS if key in current}
    if not isinstance(update, dict):
        return merged
    idea = _optional_text(update.get("idea"), 500) if "idea" in update else None
    if "idea" in update and idea:
        merged["idea"] = idea
    statement = _optional_text(update.get("statement"), 240) if "statement" in update else None
    if "statement" in update and statement:
        merged["statement"] = statement
    for key in FACT_LISTS:
        if key in update:
            merged[key] = _string_list(update.get(key))
    if "availability" in update:
        availability = _availability(update.get("availability"))
        if availability:
            merged["availability"] = availability
    return merged


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        if isinstance(item, str) and item.strip():
            rows.append(item.strip()[:160])
        if len(rows) == 8:
            break
    return rows


def _availability(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    cleaned = {}
    for key in ("weekday_minutes", "weekend_minutes"):
        minutes = value.get(key)
        if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 0:
            continue
        cleaned[key] = minutes
    return cleaned or None


def _proposal_body(proposal: dict) -> dict:
    goals = []
    for goal in proposal["goals"]:
        due_on = goal.get("due_on")
        goals.append(
            {
                "identity_id": goal["identity_id"],
                "objective": goal["objective"],
                "title": goal["title"],
                "recurrence": goal["recurrence"],
                "due_on": due_on.isoformat() if isinstance(due_on, date) else due_on,
                "weekdays": list(goal.get("weekdays") or []),
                "times_per_week": goal.get("times_per_week"),
                "month_day": goal.get("month_day"),
                "position": goal["position"],
                "reason": goal.get("reason"),
            }
        )
    return {"type": proposal["type"], "rationale": proposal.get("rationale"), "goals": goals}
