from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from src.api.deps import current_admin, current_user
from src.core.database import get_db
from src.core.security import utcnow
from src.models.user import User
from src.schemas.admin import AnalyticsResponse, OnboardingRequest
from src.services.analytics import mark_onboarding, snapshot

router = APIRouter()


@router.post("/api/onboarding", status_code=204)
def onboarding(
    body: OnboardingRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    mark_onboarding(db, user, body.step)
    return Response(status_code=204)


@router.get("/api/admin/analytics", response_model=AnalyticsResponse)
def analytics(
    db: Session = Depends(get_db),
    admin: User = Depends(current_admin),
) -> AnalyticsResponse:
    del admin
    return snapshot(db, utcnow().date())
