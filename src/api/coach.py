from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.api.deps import current_user
from src.core.database import get_db
from src.models.user import User
from src.schemas.coach import CoachMessageRequest, CoachMessageResponse, CoachThreadResponse
from src.schemas.transformation import TransformationResponse
from src.services.coach import apply_proposal, load_thread, send_message

router = APIRouter()


@router.get("/api/coach", response_model=CoachThreadResponse)
def thread(
    on: date = Query(),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> CoachThreadResponse:
    return load_thread(db, user, on)


@router.post("/api/coach/messages", response_model=CoachMessageResponse)
def messages(
    body: CoachMessageRequest,
    on: date = Query(),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> CoachMessageResponse:
    return send_message(db, user, on, body.message)


@router.post("/api/coach/apply", response_model=TransformationResponse)
def apply(
    on: date = Query(),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TransformationResponse:
    return apply_proposal(db, user, on)
