from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.models.user import User
from src.services.auth import GoogleProfile


def register(client, email="ada@example.com", password="password123"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )


def cookie_headers(response) -> list[str]:
    return response.headers.get_list("set-cookie")


def use_refresh_cookie(client, token: str) -> None:
    client.cookies.delete("refresh_token")
    client.cookies.set("refresh_token", token, domain="testserver", path="/api/auth")


def test_hello(client):
    response = client.get("/api/hello")
    assert response.status_code == 200
    assert response.json()["message"] == "Hello from YouAreUnstoppable!"


def test_register_creates_free_subscription(client, db):
    response = register(client)
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "ada@example.com"
    assert "access_token" not in body
    assert "refresh_token" not in body
    issued = cookie_headers(response)
    assert any(item.startswith("access_token=") and "HttpOnly" in item for item in issued)
    assert any(
        item.startswith("refresh_token=") and "HttpOnly" in item and "Path=/api/auth" in item
        for item in issued
    )

    me = client.get("/api/me")
    assert me.status_code == 200
    payload = me.json()
    assert payload["email"] == "ada@example.com"
    assert payload["role"] == "user"
    assert payload["has_password"] is True
    assert payload["subscription"]["plan"] == "free"
    assert payload["subscription"]["subscription_status"] is None
    assert payload["last_connection"] is not None

    user = db.scalar(
        select(User).options(joinedload(User.subscription)).where(User.email == "ada@example.com")
    )
    assert user is not None
    assert user.deleted_at is None
    assert user.subscription.plan.value == "free"
    assert user.subscription.stripe_customer_id is None
    assert user.subscription.stripe_subscription_id is None
    assert user.subscription.deleted_at is None
    assert user.subscription.deleted_reason is None


def test_duplicate_email_is_rejected(client):
    assert register(client).status_code == 200
    again = register(client)
    assert again.status_code == 409


def test_login_and_logout(client):
    register(client)
    logged_in = client.post(
        "/api/auth/login",
        json={"email": "ada@example.com", "password": "password123"},
    )
    assert logged_in.status_code == 200
    refresh_token = logged_in.cookies["refresh_token"]

    logged_out = client.post("/api/auth/logout")
    assert logged_out.status_code == 204
    assert client.get("/api/me").status_code == 401

    use_refresh_cookie(client, refresh_token)
    reused = client.post("/api/auth/refresh")
    assert reused.status_code == 401


def test_refresh_rotates_token_without_moving_last_connection(client):
    registered = register(client)
    old_refresh = registered.cookies["refresh_token"]
    before = client.get("/api/me").json()

    refreshed = client.post("/api/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.cookies["refresh_token"] != old_refresh
    assert "refresh_token" not in refreshed.json()

    after = client.get("/api/me").json()
    assert after["last_connection"] == before["last_connection"]

    use_refresh_cookie(client, old_refresh)
    old = client.post("/api/auth/refresh")
    assert old.status_code == 401


def test_closed_account_cannot_log_in(client, db):
    register(client)
    user = db.scalar(select(User).where(User.email == "ada@example.com"))
    user.deleted_at = datetime.now(timezone.utc)
    db.commit()

    response = client.post(
        "/api/auth/login",
        json={"email": "ada@example.com", "password": "password123"},
    )
    assert response.status_code == 403


def test_google_links_verified_email_and_rejects_a_different_subject(client, monkeypatch):
    register(client)
    profiles = iter(
        [
            GoogleProfile(sub="google-1", email="ada@example.com"),
            GoogleProfile(sub="google-2", email="ada@example.com"),
        ]
    )
    monkeypatch.setattr("src.services.auth.verify_google_id_token", lambda token: next(profiles))

    linked = client.post("/api/auth/google", json={"id_token": "first"})
    assert linked.status_code == 200

    conflict = client.post("/api/auth/google", json={"id_token": "second"})
    assert conflict.status_code == 409


def test_google_creates_a_free_account_that_can_set_a_password(client, monkeypatch, db):
    monkeypatch.setattr(
        "src.services.auth.verify_google_id_token",
        lambda token: GoogleProfile(sub="google-9", email="grace@example.com"),
    )
    created = client.post("/api/auth/google", json={"id_token": "token"})
    assert created.status_code == 200

    me = client.get("/api/me")
    assert me.json()["subscription"]["plan"] == "free"
    assert me.json()["has_password"] is False

    user = db.scalar(
        select(User).options(joinedload(User.subscription)).where(User.email == "grace@example.com")
    )
    assert user.password_hash is None
    assert user.google_sub == "google-9"
    assert user.subscription.user_id == user.id

    missing = client.post(
        "/api/auth/login",
        json={"email": "grace@example.com", "password": "password123"},
    )
    assert missing.status_code == 401

    set_password = client.post("/api/auth/password", json={"password": "password123"})
    assert set_password.status_code == 204
    assert client.get("/api/me").json()["has_password"] is True

    logged_in = client.post(
        "/api/auth/login",
        json={"email": "grace@example.com", "password": "password123"},
    )
    assert logged_in.status_code == 200

    again = client.post("/api/auth/password", json={"password": "anotherpass1"})
    assert again.status_code == 409
