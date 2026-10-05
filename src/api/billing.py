from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.api.deps import current_user
from src.core.database import get_db
from src.models.user import User
from src.schemas.billing import BillingUrlResponse
from src.services.billing import handle_webhook, start_checkout, start_portal

router = APIRouter()


@router.post("/api/billing/checkout", response_model=BillingUrlResponse)
def checkout(db: Session = Depends(get_db), user: User = Depends(current_user)) -> BillingUrlResponse:
    return BillingUrlResponse(url=start_checkout(db, user))


@router.post("/api/billing/portal", response_model=BillingUrlResponse)
def portal(user: User = Depends(current_user)) -> BillingUrlResponse:
    return BillingUrlResponse(url=start_portal(user))


@router.post("/api/billing/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, bool]:
    payload = await request.body()
    handle_webhook(db, payload, request.headers.get("stripe-signature"))
    return {"received": True}
