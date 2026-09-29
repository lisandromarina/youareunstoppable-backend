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

## Transformation

These routes require the `access_token` cookie. A missing or invalid cookie is `401` with `Not authenticated.`

The client sends `on` as `YYYY-MM-DD` on every route that talks about today. The date must be UTC today, or one day on either side. Anything else is `422` with `That date is outside the allowed range.`

The catalog is the free template. Starting or replacing a transformation copies it onto the user. The rules are in [domain.md](domain.md).

### GET /api/catalog

`200` returns every identity, its directions, and each direction's phases. Each commitment has a `recurrence` of `daily`, `times_per_week`, `weekly`, or `monthly`, plus `weekdays`, `times_per_week`, and `month_day`. `kind` still marks the catalog's base and extra rows. Scheduling uses the recurrence, not `unlock_streak`.

```json
{
  "identities": [
    {
      "id": "disciplined",
      "name": "Disciplined",
      "directions": [
        {
          "id": "master-deep-work",
          "name": "Master deep work",
          "phases": [
            {
              "id": "master-deep-work-foundation",
              "name": "Foundation",
              "headline": "Keep One Promise",
              "length_days": 14,
              "commitments": []
            }
          ]
        }
      ]
    }
  ]
}
```

### The transformation document

`GET`, `POST`, `PUT`, and the today commands return the same document.

`statement` is built from the selected identity names, in order. Two identities read `I'm becoming disciplined and healthy.`

`selections` has one entry per identity, at most two. `phase_name` is the current headline. `stage_name` is the journey label. `phases` marks each phase `complete`, `current`, or `upcoming`. `active_commitments` is how many commitments that identity has today.

`today.groups` lists the commitments that are due that day, under each identity. `objective` is the goal. `cadence` is the frequency label. `implementation` is the chosen way. `implementations` are the other ways to meet the same goal. `status` is `open`, `done`, or `skipped`. `coming_up` lists current-phase commitments that are not due that day, with `when` for the chosen schedule.

`promises_kept` is how many days have been closed. A missed day does not reduce it. The product does not show a streak.

`progress` uses the first identity. `commitments_done` and `commitments_total` count closed days only, and only occurrences that were due.

`year` is 1 January through 31 December of the year in `on`. `intensity` is `0` to `2` for the commitments that were due that day, as in [domain.md](domain.md). A commitment that was not due is not counted. `identities` is the same scale for each identity alone. `closed` is true when that day was closed. `today` is true for `on`.

### GET /api/transformation

Query: `on`.

`200` returns the document. If that date has no day yet, the API opens it and schedules today's commitments.

`404` when nothing has started: `Transformation has not started.`

### POST /api/transformation

Query: `on`. Body:

```json
{
  "selections": [
    { "identity_id": "disciplined", "direction_id": "master-deep-work" }
  ]
}
```

One or two selections. `201` copies the catalog, starts at day 1 of the first phase, and schedules the commitments that are due on `on`.

`409` when a transformation already exists: `A transformation has already started.`

`422` when an identity is unknown (`Unknown identity.`), a direction is not under that identity (`That direction is not part of this identity.`), the same identity appears twice (`Each identity can be chosen once.`), or there are not one or two selections.

### PUT /api/transformation

Same query and body as `POST`.

`200` replaces the selections. An unchanged identity and direction keep their phase day and unlock streak. Anything new or changed is copied again at day 1 with unlock streak 0. If `on` is still open, today's commitments are rebuilt. Closed days stay.

`404` when nothing has started.

`422` uses the same selection errors as `POST`.

### DELETE /api/transformation

No body. `204` deletes the transformation, its paths, and its days. A second delete is also `204`. The account stays signed in. The next `GET` is `404`.

### POST /api/transformation/today/commitments/{commitment_id}/toggle

Query: `on`. No body.

`200` turns `open` into `done`, `done` into `open`, and `skipped` into `done`.

`404` when the commitment is not on that day: `Commitment was not found.`

`409` when the day is already closed: `This day is already closed.`

### POST /api/transformation/today/commitments/{commitment_id}/replace

Query: `on`. Body:

```json
{ "implementation_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6" }
```

`implementation_id` must be one of that commitment's planned implementations. `200` changes the chosen title. The objective snapshot stays.

`422` when it is not one of those ways: `That is not a way to complete this commitment.`

`404` and `409` match toggle.

### POST /api/transformation/today/commitments/{commitment_id}/skip

Query: `on`. No body.

`200` marks the commitment `skipped`.

`404` and `409` match toggle.

### POST /api/transformation/commitments/{planned_id}/schedule

Query: `on`. Body is either weekdays or a month day:

```json
{ "weekdays": [0, 2, 4] }
```

```json
{ "month_day": 1 }
```

`200` updates that planned commitment's schedule. Weekdays use Monday as `0`. A weekly commitment needs one weekday. A several-times-a-week commitment needs exactly `times_per_week` weekdays. A monthly commitment needs a day from 1 to 28. If `on` is still open, a commitment that becomes due is added, and an open commitment that is no longer due is removed. A closed day stays as it was. Later occurrences keep the new schedule.

`422` when the day count does not match: `Select exactly 3 days.` A daily commitment returns `This commitment is due every day.` A bad month day returns `Choose a day from 1 to 28.`

`404` when the planned commitment is not on this transformation: `Commitment was not found.`

### POST /api/transformation/today/showed-up

Query: `on`. No body.

`200` closes the day when every due commitment is done or skipped, advances each path's phase day and streak, and returns the document. Commitments that are not due do not block the day. The last day of a phase rolls into the next phase at day 1 and keeps the streak. After the last phase, the path stays there and `completed` is true.

`409` when any due commitment is still `open`: `Finish or skip every commitment first.`

`409` when the day is already closed: `This day is already closed.`

