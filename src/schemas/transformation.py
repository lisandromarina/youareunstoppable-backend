from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SelectionRequest(BaseModel):
    identity_id: str = Field(min_length=1, max_length=64)
    direction_id: str = Field(min_length=1, max_length=64)


class SelectionsRequest(BaseModel):
    selections: list[SelectionRequest] = Field(min_length=1, max_length=2)


class ReplaceRequest(BaseModel):
    implementation_id: UUID


class ScheduleRequest(BaseModel):
    weekdays: list[int] | None = None
    month_day: int | None = None


class CatalogImplementationResponse(BaseModel):
    id: str
    title: str


class CatalogCommitmentResponse(BaseModel):
    id: str
    objective: str
    unlock_streak: int
    kind: Literal["base", "extra"]
    recurrence: Literal["daily", "times_per_week", "weekly", "monthly"]
    times_per_week: int | None
    weekdays: list[int]
    month_day: int | None
    implementations: list[CatalogImplementationResponse]


class CatalogPhaseResponse(BaseModel):
    id: str
    name: str
    headline: str
    length_days: int
    commitments: list[CatalogCommitmentResponse]


class CatalogDirectionResponse(BaseModel):
    id: str
    name: str
    phases: list[CatalogPhaseResponse]


class CatalogIdentityResponse(BaseModel):
    id: str
    name: str
    directions: list[CatalogDirectionResponse]


class CatalogResponse(BaseModel):
    identities: list[CatalogIdentityResponse]


class ImplementationResponse(BaseModel):
    id: UUID
    title: str


class CommitmentResponse(BaseModel):
    id: UUID
    planned_commitment_id: UUID | None
    objective: str
    cadence: str
    recurrence: Literal["daily", "times_per_week", "weekly", "monthly"]
    times_per_week: int | None
    weekdays: list[int]
    month_day: int | None
    implementation: ImplementationResponse
    implementations: list[ImplementationResponse]
    status: Literal["open", "done", "skipped"]


class UpcomingResponse(BaseModel):
    planned_commitment_id: UUID
    identity_name: str
    objective: str
    title: str
    cadence: str
    recurrence: Literal["daily", "times_per_week", "weekly", "monthly"]
    times_per_week: int | None
    weekdays: list[int]
    month_day: int | None
    when: str


class TodayGroupResponse(BaseModel):
    identity_id: str
    identity_name: str
    commitments: list[CommitmentResponse]


class TodayResponse(BaseModel):
    date: date
    closed: bool
    groups: list[TodayGroupResponse]
    coming_up: list[UpcomingResponse]


class PhaseResponse(BaseModel):
    name: str
    headline: str
    status: Literal["complete", "current", "upcoming"]
    length_days: int


class SelectionResponse(BaseModel):
    identity_id: str
    identity_name: str
    direction_id: str
    direction_name: str
    phase_name: str
    stage_name: str
    day_in_phase: int
    length_days: int
    active_commitments: int
    completed: bool
    phases: list[PhaseResponse]


class ProgressResponse(BaseModel):
    phase_name: str
    day_in_phase: int
    length_days: int
    commitments_done: int
    commitments_total: int
    next_phase_name: str | None


class YearIdentityResponse(BaseModel):
    identity_id: str
    intensity: int


class YearDayResponse(BaseModel):
    date: date
    intensity: int
    closed: bool
    today: bool
    identities: list[YearIdentityResponse]


class TomorrowItemResponse(BaseModel):
    identity_name: str
    title: str
    cadence: str


class TransformationResponse(BaseModel):
    statement: str
    selections: list[SelectionResponse]
    today: TodayResponse
    progress: ProgressResponse
    year: list[YearDayResponse]
    promises_kept: int
    started_on: date
    tomorrow: list[TomorrowItemResponse]
    prior_closed_on: date | None


def catalog_response() -> CatalogResponse:
    from src.domain.catalog import list_identities

    identities = []
    for identity in list_identities():
        directions = []
        for direction in identity.directions:
            phases = []
            for phase in direction.phases:
                commitments = []
                for commitment in phase.commitments:
                    commitments.append(
                        CatalogCommitmentResponse(
                            id=commitment.id,
                            objective=commitment.objective,
                            unlock_streak=commitment.unlock_streak,
                            kind="base" if commitment.unlock_streak == 0 else "extra",
                            recurrence=commitment.recurrence,  # type: ignore[arg-type]
                            times_per_week=commitment.times_per_week,
                            weekdays=list(commitment.weekdays),
                            month_day=commitment.month_day,
                            implementations=[
                                CatalogImplementationResponse(id=item.id, title=item.title)
                                for item in commitment.implementations
                            ],
                        )
                    )
                phases.append(
                    CatalogPhaseResponse(
                        id=phase.id,
                        name=phase.name,
                        headline=phase.headline,
                        length_days=phase.length_days,
                        commitments=commitments,
                    )
                )
            directions.append(
                CatalogDirectionResponse(id=direction.id, name=direction.name, phases=phases)
            )
        identities.append(
            CatalogIdentityResponse(id=identity.id, name=identity.name, directions=directions)
        )
    return CatalogResponse(identities=identities)
