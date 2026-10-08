from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class CoachMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class CoachGoalResponse(BaseModel):
    identity_id: str
    objective: str
    title: str
    recurrence: Literal["daily", "times_per_week", "weekly", "monthly", "once"]
    due_on: date | None = None
    weekdays: list[int] = Field(default_factory=list)
    times_per_week: int | None = None
    month_day: int | None = None
    position: int
    reason: str | None = None


class CoachProposalResponse(BaseModel):
    type: Literal["plan", "today"]
    rationale: str | None = None
    goals: list[CoachGoalResponse]


class CoachTurnResponse(BaseModel):
    role: Literal["user", "coach"]
    content: str


class CoachThreadResponse(BaseModel):
    transcript: list[CoachTurnResponse]
    proposal: CoachProposalResponse | None = None


class CoachMessageResponse(BaseModel):
    reply: str
    proposal: CoachProposalResponse | None = None
