from datetime import date
from typing import Literal

from pydantic import BaseModel


class OnboardingRequest(BaseModel):
    step: Literal["begin", "identity", "direction"]


class OverviewResponse(BaseModel):
    total_users: int
    new_users_today: int
    new_users_7d: int
    new_users_30d: int
    started_path: int
    days_completed: int
    active_users: int
    retention_1d: float | None
    retention_3d: float | None
    retention_7d: float | None


class FunnelStepResponse(BaseModel):
    key: str
    label: str
    count: int
    percent_of_signups: float | None
    percent_of_previous: float | None


class CohortResponse(BaseModel):
    date: date
    size: int
    day_1: float | None
    day_3: float | None
    day_7: float | None
    day_14: float | None


class AnalyticsResponse(BaseModel):
    overview: OverviewResponse
    funnel: list[FunnelStepResponse]
    cohorts: list[CohortResponse]
