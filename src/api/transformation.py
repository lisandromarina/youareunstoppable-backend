from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from src.api.deps import current_admin, current_user
from src.core.database import get_db
from src.models.user import User
from src.schemas.transformation import (
    CatalogResponse,
    ReplaceRequest,
    ScheduleRequest,
    SelectionsRequest,
    TransformationResponse,
    catalog_response,
)
from src.services.transformation import (
    read_transformation,
    replace_commitment,
    reset_transformation,
    set_schedule,
    showed_up,
    skip_commitment,
    start_transformation,
    toggle_commitment,
    update_transformation,
)

router = APIRouter()


@router.get("/api/catalog", response_model=CatalogResponse)
def catalog(user: User = Depends(current_user)) -> CatalogResponse:
    del user
    return catalog_response()


@router.get("/api/transformation", response_model=TransformationResponse)
def transformation(
    on: date = Query(),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TransformationResponse:
    return read_transformation(db, user, on)


@router.post("/api/transformation", response_model=TransformationResponse, status_code=201)
def start(
    body: SelectionsRequest,
    on: date = Query(),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TransformationResponse:
    return start_transformation(db, user, on, body.selections)


@router.put("/api/transformation", response_model=TransformationResponse)
def update(
    body: SelectionsRequest,
    on: date = Query(),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TransformationResponse:
    return update_transformation(db, user, on, body.selections)


@router.delete("/api/transformation", status_code=204)
def reset(
    db: Session = Depends(get_db),
    user: User = Depends(current_admin),
) -> Response:
    reset_transformation(db, user)
    return Response(status_code=204)


@router.post(
    "/api/transformation/today/commitments/{commitment_id}/toggle",
    response_model=TransformationResponse,
)
def toggle(
    commitment_id: UUID,
    on: date = Query(),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TransformationResponse:
    return toggle_commitment(db, user, on, commitment_id)


@router.post(
    "/api/transformation/today/commitments/{commitment_id}/replace",
    response_model=TransformationResponse,
)
def replace(
    commitment_id: UUID,
    body: ReplaceRequest,
    on: date = Query(),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TransformationResponse:
    return replace_commitment(db, user, on, commitment_id, body.implementation_id)


@router.post(
    "/api/transformation/today/commitments/{commitment_id}/skip",
    response_model=TransformationResponse,
)
def skip(
    commitment_id: UUID,
    on: date = Query(),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TransformationResponse:
    return skip_commitment(db, user, on, commitment_id)


@router.post("/api/transformation/today/showed-up", response_model=TransformationResponse)
def close_day(
    on: date = Query(),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TransformationResponse:
    return showed_up(db, user, on)


@router.post(
    "/api/transformation/commitments/{planned_id}/schedule",
    response_model=TransformationResponse,
)
def schedule(
    planned_id: UUID,
    body: ScheduleRequest,
    on: date = Query(),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TransformationResponse:
    return set_schedule(db, user, on, planned_id, body.weekdays, body.month_day)
