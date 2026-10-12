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
    opened_today: int
    closed_today: int
    commitments_done: int
    commitments_skipped: int
    return_1d: float | None
    closed_1d: float | None
    return_3d: float | None
    closed_3d: float | None
    return_7d: float | None
    closed_7d: float | None
    day1_closure: float | None


class FunnelStepResponse(BaseModel):
    key: str
    label: str
    count: int
    percent_of_signups: float | None
    percent_of_previous: float | None


class CohortDayResponse(BaseModel):
    returned: float | None
    closed: float | None


class CohortResponse(BaseModel):
    date: date
    size: int
    day_1: CohortDayResponse | None
    day_3: CohortDayResponse | None
    day_7: CohortDayResponse | None
    day_14: CohortDayResponse | None


class AnalyticsResponse(BaseModel):
    overview: OverviewResponse
    funnel: list[FunnelStepResponse]
    cohorts: list[CohortResponse]
