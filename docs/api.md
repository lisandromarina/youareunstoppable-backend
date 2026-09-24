# API

The routes that exist today. Why the session works this way is in [auth-decisions.md](auth-decisions.md). Days, the journal, the coach, and Stripe are not in this file.

The interactive page is `http://localhost:8000/docs` while the API is running. The OpenAPI document is `http://localhost:8000/openapi.json`.

## Calling the API

Send JSON as `Content-Type: application/json`. The browser must send and store cookies, so each request uses credentials. In `fetch`, that is `credentials: "include"`.

The client does not read the tokens. Register, login, Google sign-in, and refresh set two HttpOnly cookies and return the user in the body. Later requests send those cookies automatically.

| Cookie | Path | Lifetime | Sent |
| --- | --- | --- | --- |
| `access_token` | `/` | 15 minutes | With every API request |
| `refresh_token` | `/api/auth` | 30 days | Only to `/api/auth` |

Both cookies are `HttpOnly` and `SameSite=Lax`. They are `Secure` when `COOKIE_SECURE` is true. Page scripts cannot read them.

An auth failure returns:

```json
{ "detail": "Not authenticated." }
```

A body that fails validation returns `422` with FastAPI's `detail` list. That covers a bad email, a missing field, or a password outside the length limits below.

## User

Register, login, Google sign-in, refresh, and `GET /api/me` return this object. `plan` is `free` or `pro`. `role` is `user` or `admin`. `has_password` is true when the account has a password. A Google-only account returns false until `POST /api/auth/password` succeeds. The password hash is not in this response. New accounts are `user` and `free`. Stripe fields on the subscription stay null until billing exists, and they are not in this response.

```json
{
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "email": "ada@example.com",
  "role": "user",
  "has_password": true,
  "last_connection": "2026-09-24T14:00:00Z",
  "subscription": {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "plan": "free",
    "subscription_status": null,
    "current_period_end": null,
    "deleted_at": null,
    "deleted_reason": null
  }
}
```

## GET /api/hello

No auth. Returns `200`.

```json
{ "message": "Hello from YouAreUnstoppable!" }
```

## POST /api/auth/register

Creates an account and a free subscription, then signs the person in.

```json
{ "email": "ada@example.com", "password": "password123" }
```

`password` is 8 to 128 characters. Email is stored lowercase.

`200` returns the user and sets both cookies. `last_connection` is this request.

`409` when the email is already registered, including a closed account: `An account with this email already exists.`

## POST /api/auth/login

Signs in with email and password.

```json
{ "email": "ada@example.com", "password": "password123" }
```

`password` is 1 to 128 characters.

`200` returns the user and sets both cookies. `last_connection` moves to this request.

`401` when the email is unknown, the account has no password, or the password is wrong: `Email or password is incorrect.`

`403` when the account is closed: `This account is closed.`

## POST /api/auth/google

Signs in with a Google ID token. The API checks it against `GOOGLE_CLIENT_ID` and requires a verified email.

```json
{ "id_token": "<google id token>" }
```

`200` returns the user and sets both cookies.

- A known Google subject signs in.
- A verified email that matches an existing user stores `google_sub` on that user.
- An unknown email creates a free account with no password.

`last_connection` moves to this request for an existing user, and is set for a new one.

`401` when the token cannot be verified: `Google sign-in could not be verified.` The same status is returned when the email is missing or not verified: `Google account email is not verified.`

`403` when the matched account is closed.

`409` when that email is already linked to a different Google subject: `This email is already linked to another Google account.`

`500` when `GOOGLE_CLIENT_ID` is not set: `Google sign-in is not configured.`

## POST /api/auth/password

Sets a password on the signed-in account. Requires the `access_token` cookie. A Google-only user calls this once.

```json
{ "password": "password123" }
```

`password` is 8 to 128 characters.

`204` with an empty body. Cookies stay as they are.

`401` when the access cookie is missing or invalid: `Not authenticated.`

`403` when the account is closed.

`409` when a password is already set: `This account already has a password.`

## POST /api/auth/refresh

No body. Requires the `refresh_token` cookie.

`200` returns the user, revokes the old refresh token, and sets a new cookie pair. `last_connection` does not change.

`401` when the refresh cookie is missing, revoked, or expired: `Refresh token is not valid.`

`403` when the account is closed.

## POST /api/auth/logout

No body. Clears both cookies. When the refresh cookie is still valid, that token is revoked. A missing or already dead refresh cookie still ends in `204`.

## GET /api/me

Requires the `access_token` cookie. Returns `200` and the user, including the subscription.

`401` when the access cookie is missing or invalid.

`403` when the account is closed.
