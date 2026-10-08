import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import stripe
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import Settings, get_settings
from src.models.subscription import Plan, Subscription
from src.models.user import User
from src.services.errors import DomainError

logger = logging.getLogger(__name__)

PRO_STATUSES = frozenset({"active", "trialing", "past_due"})


def pro_entitled(user: User) -> bool:
    row = user.subscription
    if row is None:
        return False
    plan = row.plan.value if isinstance(row.plan, Plan) else row.plan
    return plan == Plan.pro.value and row.subscription_status in PRO_STATUSES


def create_stripe_client(secret_key: str) -> stripe.StripeClient:
    return stripe.StripeClient(secret_key)


def billing_configured(settings: Settings | None = None) -> bool:
    current = settings or get_settings()
    return bool(
        current.stripe_secret_key
        and current.stripe_webhook_secret
        and current.stripe_price_id
        and current.frontend_origin
    )


def start_checkout(db: Session, user: User) -> str:
    settings = get_settings()
    if not billing_configured(settings):
        raise DomainError(503, "Billing is not configured.")
    row = user.subscription
    if row.subscription_status in PRO_STATUSES:
        raise DomainError(409, "This account already has Pro.")

    client = create_stripe_client(settings.stripe_secret_key)
    if not row.stripe_customer_id:
        customer = client.v1.customers.create(
            params={"email": user.email, "metadata": {"user_id": str(user.id)}}
        )
        row.stripe_customer_id = customer.id
        db.commit()

    origin = settings.frontend_origin.rstrip("/")
    session = client.v1.checkout.sessions.create(
        params={
            "mode": "subscription",
            "customer": row.stripe_customer_id,
            "client_reference_id": str(user.id),
            "line_items": [{"price": settings.stripe_price_id, "quantity": 1}],
            "success_url": f"{origin}/profile?checkout=success",
            "cancel_url": f"{origin}/profile",
            "metadata": {"user_id": str(user.id)},
            "subscription_data": {"metadata": {"user_id": str(user.id)}},
        }
    )
    url = session.url
    if not url:
        raise DomainError(502, "Checkout could not be started.")
    return url


def start_portal(user: User) -> str:
    settings = get_settings()
    if not billing_configured(settings):
        raise DomainError(503, "Billing is not configured.")
    row = user.subscription
    if not row.stripe_customer_id:
        raise DomainError(409, "Billing is not set up for this account.")

    client = create_stripe_client(settings.stripe_secret_key)
    origin = settings.frontend_origin.rstrip("/")
    session = client.v1.billing_portal.sessions.create(
        params={"customer": row.stripe_customer_id, "return_url": f"{origin}/profile"}
    )
    url = session.url
    if not url:
        raise DomainError(502, "The billing portal could not be opened.")
    return url


def handle_webhook(db: Session, payload: bytes, signature: str | None) -> None:
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise DomainError(503, "Billing is not configured.")
    try:
        event = stripe.Webhook.construct_event(payload, signature or "", settings.stripe_webhook_secret)
    except (stripe.SignatureVerificationError, ValueError) as exc:
        raise DomainError(400, "Webhook signature is not valid.") from exc
    apply_event(db, event, settings)


def apply_event(db: Session, event: Any, settings: Settings) -> None:
    event_type = str(_get(event, "type") or "")
    data = _get(event, "data")
    obj = _get(data, "object")
    if obj is None:
        logger.info("Stripe event %s had no object", _get(event, "id"))
        return

    if event_type == "checkout.session.completed":
        _apply_checkout(db, event, obj, settings)
        return
    if event_type in {"customer.subscription.created", "customer.subscription.updated"}:
        _apply_known_subscription(db, event, obj, ended=False)
        return
    if event_type == "customer.subscription.deleted":
        _apply_known_subscription(db, event, obj, ended=True)


def apply_subscription(row: Subscription, stripe_subscription: Any) -> None:
    status = str(_get(stripe_subscription, "status") or "")
    row.subscription_status = status or None
    row.plan = Plan.pro if status in PRO_STATUSES else Plan.free
    row.cancel_at_period_end = bool(_get(stripe_subscription, "cancel_at_period_end"))
    row.current_period_end = _period_end(stripe_subscription)
    customer = _customer_id(stripe_subscription)
    subscription_id = _get(stripe_subscription, "id")
    if customer:
        row.stripe_customer_id = customer
    if subscription_id:
        row.stripe_subscription_id = str(subscription_id)


def end_subscription(row: Subscription, stripe_subscription: Any) -> None:
    status = _get(stripe_subscription, "status")
    row.subscription_status = str(status) if status else "canceled"
    row.plan = Plan.free
    row.cancel_at_period_end = False
    row.stripe_subscription_id = None
    ended = _period_end(stripe_subscription)
    if ended is not None:
        row.current_period_end = ended
    customer = _customer_id(stripe_subscription)
    if customer:
        row.stripe_customer_id = customer


def _apply_checkout(db: Session, event: Any, session: Any, settings: Settings) -> None:
    row = _find_subscription(db, _user_id(session), _customer_id(session))
    if row is None:
        _log_unmatched(event)
        return
    customer = _customer_id(session)
    if customer:
        row.stripe_customer_id = customer
    subscription_ref = _get(session, "subscription")
    if subscription_ref is None:
        db.commit()
        return
    if isinstance(subscription_ref, str):
        if not settings.stripe_secret_key:
            raise DomainError(503, "Billing is not configured.")
        client = create_stripe_client(settings.stripe_secret_key)
        apply_subscription(row, client.v1.subscriptions.retrieve(subscription_ref))
        db.commit()
        return
    apply_subscription(row, subscription_ref)
    db.commit()


def _apply_known_subscription(db: Session, event: Any, obj: Any, *, ended: bool) -> None:
    row = _find_subscription(db, _user_id(obj), _customer_id(obj))
    if row is None:
        _log_unmatched(event)
        return
    if ended:
        end_subscription(row, obj)
    else:
        apply_subscription(row, obj)
    db.commit()


def _find_subscription(db: Session, user_id: str | None, customer_id: str | None) -> Subscription | None:
    if user_id:
        try:
            parsed = UUID(user_id)
        except ValueError:
            parsed = None
        if parsed is not None:
            row = db.scalar(select(Subscription).where(Subscription.user_id == parsed))
            if row is not None:
                return row
    if customer_id:
        return db.scalar(select(Subscription).where(Subscription.stripe_customer_id == customer_id))
    return None


def _log_unmatched(event: Any) -> None:
    logger.info("Stripe event %s did not match a subscription", _get(event, "id"))


def _user_id(obj: Any) -> str | None:
    metadata = _get(obj, "metadata") or {}
    value = _get(metadata, "user_id")
    if value:
        return str(value)
    reference = _get(obj, "client_reference_id")
    if reference:
        return str(reference)
    return None


def _customer_id(obj: Any) -> str | None:
    customer = _get(obj, "customer")
    if customer is None:
        return None
    if isinstance(customer, str):
        return customer
    nested = _get(customer, "id")
    if nested:
        return str(nested)
    return None


def _period_end(subscription: Any) -> datetime | None:
    raw = _get(subscription, "current_period_end")
    if raw is None:
        items = _get(subscription, "items")
        data = _get(items, "data") if items is not None else None
        if isinstance(data, list) and data:
            raw = _get(data[0], "current_period_end")
    if raw is None:
        return None
    return datetime.fromtimestamp(int(raw), tz=timezone.utc)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    getter = getattr(obj, "get", None)
    if callable(getter):
        try:
            value = getter(key, default)
        except TypeError:
            value = getter(key)
        if value is None:
            return default
        return value
    return getattr(obj, key, default)
