from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.core.config import get_settings
from src.models.user import User
from tests.test_auth import register

PERIOD_END = 1794000000


@pytest.fixture
def billing_env(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_billing")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_billing")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_monthly")
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:5173")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class RecordingClient:
    def __init__(self, subscription=None):
        self.customer_calls = 0
        self.customer_params = None
        self.checkout_params = None
        self.portal_params = None
        self.retrieved = None
        self.subscription = subscription
        self.v1 = SimpleNamespace(
            customers=SimpleNamespace(create=self.create_customer),
            checkout=SimpleNamespace(sessions=SimpleNamespace(create=self.create_checkout)),
            billing_portal=SimpleNamespace(sessions=SimpleNamespace(create=self.create_portal)),
            subscriptions=SimpleNamespace(retrieve=self.retrieve_subscription),
        )

    def create_customer(self, params):
        self.customer_calls += 1
        self.customer_params = params
        return SimpleNamespace(id="cus_test")

    def create_checkout(self, params):
        self.checkout_params = params
        return SimpleNamespace(url="https://checkout.stripe.test/session")

    def create_portal(self, params):
        self.portal_params = params
        return SimpleNamespace(url="https://billing.stripe.test/session")

    def retrieve_subscription(self, subscription_id):
        self.retrieved = subscription_id
        return self.subscription


def subscription_row(db, email="ada@example.com"):
    db.expire_all()
    user = db.scalar(select(User).options(joinedload(User.subscription)).where(User.email == email))
    assert user is not None
    return user.subscription


def stripe_subscription(user_id, **overrides):
    payload = {
        "id": "sub_123",
        "customer": "cus_test",
        "status": "active",
        "cancel_at_period_end": False,
        "current_period_end": PERIOD_END,
        "metadata": {"user_id": user_id},
    }
    payload.update(overrides)
    return payload


def post_event(client, monkeypatch, event):
    monkeypatch.setattr(
        "src.services.billing.stripe.Webhook.construct_event",
        lambda payload, signature, secret: event,
    )
    return client.post(
        "/api/billing/webhook",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=test"},
    )


def test_checkout_requires_configuration(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "")
    monkeypatch.setenv("STRIPE_PRICE_ID", "")
    monkeypatch.setenv("FRONTEND_ORIGIN", "")
    get_settings.cache_clear()
    register(client)
    response = client.post("/api/billing/checkout")
    assert response.status_code == 503
    assert response.json()["detail"] == "Billing is not configured."
    assert client.get("/api/billing").json() == {"enabled": False}
    get_settings.cache_clear()


def test_checkout_creates_one_customer(client, db, monkeypatch, billing_env):
    recorder = RecordingClient()
    monkeypatch.setattr("src.services.billing.create_stripe_client", lambda secret: recorder)
    registered = register(client)
    user_id = registered.json()["id"]

    first = client.post("/api/billing/checkout")
    second = client.post("/api/billing/checkout")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == {"url": "https://checkout.stripe.test/session"}
    assert recorder.customer_calls == 1
    assert recorder.customer_params["email"] == "ada@example.com"
    assert recorder.customer_params["metadata"] == {"user_id": user_id}
    assert recorder.checkout_params["mode"] == "subscription"
    assert recorder.checkout_params["customer"] == "cus_test"
    assert recorder.checkout_params["line_items"] == [{"price": "price_monthly", "quantity": 1}]
    assert recorder.checkout_params["success_url"] == "http://localhost:5173/profile?checkout=success"
    assert recorder.checkout_params["subscription_data"] == {"metadata": {"user_id": user_id}}
    assert subscription_row(db).stripe_customer_id == "cus_test"
    me = client.get("/api/me").json()
    assert "billing_enabled" not in me
    assert client.get("/api/billing").json() == {"enabled": True}
    assert me["subscription"]["plan"] == "free"
    assert me["subscription"]["cancel_at_period_end"] is False
    assert "stripe_customer_id" not in me["subscription"]
    assert "stripe_subscription_id" not in me["subscription"]


def test_portal_without_customer_is_rejected(client, billing_env):
    register(client)
    response = client.post("/api/billing/portal")
    assert response.status_code == 409
    assert response.json()["detail"] == "Billing is not set up for this account."


def test_portal_opens_for_an_existing_customer(client, monkeypatch, billing_env):
    recorder = RecordingClient()
    monkeypatch.setattr("src.services.billing.create_stripe_client", lambda secret: recorder)
    register(client)
    assert client.post("/api/billing/checkout").status_code == 200
    response = client.post("/api/billing/portal")
    assert response.status_code == 200
    assert response.json() == {"url": "https://billing.stripe.test/session"}
    assert recorder.portal_params == {
        "customer": "cus_test",
        "return_url": "http://localhost:5173/profile",
    }


def test_webhook_rejects_a_bad_signature(client, billing_env):
    register(client)
    response = client.post(
        "/api/billing/webhook",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=bad"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Webhook signature is not valid."


def test_active_subscription_sets_pro(client, db, monkeypatch, billing_env):
    registered = register(client)
    user_id = registered.json()["id"]
    event = {
        "id": "evt_active",
        "type": "customer.subscription.updated",
        "data": {"object": stripe_subscription(user_id)},
    }
    first = post_event(client, monkeypatch, event)
    second = post_event(client, monkeypatch, event)
    assert first.status_code == 200
    assert second.status_code == 200

    me = client.get("/api/me").json()["subscription"]
    assert me["plan"] == "pro"
    assert me["subscription_status"] == "active"
    assert me["cancel_at_period_end"] is False
    row = subscription_row(db)
    assert row.stripe_customer_id == "cus_test"
    assert row.stripe_subscription_id == "sub_123"
    assert row.plan.value == "pro"

    again = client.post("/api/billing/checkout")
    assert again.status_code == 409


def test_past_due_stays_pro(client, monkeypatch, billing_env):
    registered = register(client)
    event = {
        "id": "evt_past_due",
        "type": "customer.subscription.updated",
        "data": {"object": stripe_subscription(registered.json()["id"], status="past_due")},
    }
    assert post_event(client, monkeypatch, event).status_code == 200
    me = client.get("/api/me").json()["subscription"]
    assert me["plan"] == "pro"
    assert me["subscription_status"] == "past_due"


def test_scheduled_cancel_stays_pro_until_deleted(client, db, monkeypatch, billing_env):
    registered = register(client)
    user_id = registered.json()["id"]
    scheduled = {
        "id": "evt_cancel",
        "type": "customer.subscription.updated",
        "data": {"object": stripe_subscription(user_id, cancel_at_period_end=True)},
    }
    assert post_event(client, monkeypatch, scheduled).status_code == 200
    me = client.get("/api/me").json()["subscription"]
    assert me["plan"] == "pro"
    assert me["subscription_status"] == "active"
    assert me["cancel_at_period_end"] is True
    assert subscription_row(db).stripe_subscription_id == "sub_123"

    deleted = {
        "id": "evt_deleted",
        "type": "customer.subscription.deleted",
        "data": {
            "object": stripe_subscription(
                user_id,
                status="canceled",
                cancel_at_period_end=True,
            )
        },
    }
    assert post_event(client, monkeypatch, deleted).status_code == 200
    me = client.get("/api/me").json()["subscription"]
    assert me["plan"] == "free"
    assert me["subscription_status"] == "canceled"
    assert me["cancel_at_period_end"] is False
    row = subscription_row(db)
    assert row.stripe_subscription_id is None
    assert row.stripe_customer_id == "cus_test"


def test_unmatched_webhook_returns_200(client, db, monkeypatch, billing_env):
    register(client)
    event = {
        "id": "evt_missing",
        "type": "customer.subscription.updated",
        "data": {
            "object": stripe_subscription(
                "00000000-0000-0000-0000-000000000000",
                customer="cus_missing",
            )
        },
    }
    response = post_event(client, monkeypatch, event)
    assert response.status_code == 200
    assert response.json() == {"received": True}
    assert subscription_row(db).plan.value == "free"


def test_checkout_session_retrieves_the_subscription(client, db, monkeypatch, billing_env):
    registered = register(client)
    user_id = registered.json()["id"]
    recorder = RecordingClient(
        subscription=stripe_subscription(user_id, id="sub_from_checkout", customer="cus_from_checkout")
    )
    monkeypatch.setattr("src.services.billing.create_stripe_client", lambda secret: recorder)
    event = {
        "id": "evt_checkout",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_from_checkout",
                "subscription": "sub_from_checkout",
                "metadata": {"user_id": user_id},
            }
        },
    }
    assert post_event(client, monkeypatch, event).status_code == 200
    assert recorder.retrieved == "sub_from_checkout"
    row = subscription_row(db)
    assert row.plan.value == "pro"
    assert row.stripe_customer_id == "cus_from_checkout"
    assert row.stripe_subscription_id == "sub_from_checkout"


def test_webhook_matches_customer_when_metadata_is_missing(client, db, monkeypatch, billing_env):
    recorder = RecordingClient()
    monkeypatch.setattr("src.services.billing.create_stripe_client", lambda secret: recorder)
    register(client)
    assert client.post("/api/billing/checkout").status_code == 200
    event = {
        "id": "evt_customer",
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_by_customer",
                "customer": "cus_test",
                "status": "trialing",
                "cancel_at_period_end": False,
                "current_period_end": PERIOD_END,
                "metadata": {},
            }
        },
    }
    assert post_event(client, monkeypatch, event).status_code == 200
    row = subscription_row(db)
    assert row.plan.value == "pro"
    assert row.subscription_status == "trialing"
    assert row.stripe_subscription_id == "sub_by_customer"
