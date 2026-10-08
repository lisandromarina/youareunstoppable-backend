# API

The routes that exist today. Why the session works this way is in [auth-decisions.md](auth-decisions.md). The journal is not in this file. Coach routes are below.

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

Register, login, Google sign-in, refresh, and `GET /api/me` return this object. `plan` is `free` or `pro`. `role` is `user` or `admin`. `has_password` is true when the account has a password. A Google-only account returns false until `POST /api/auth/password` succeeds. The password hash is not in this response. New accounts are `user` and `free`. `plan` is `pro` when Stripe's status is `active`, `trialing`, or `past_due`. `cancel_at_period_end` is true when a cancel is scheduled and access still lasts through `current_period_end`. Stripe customer and subscription ids stay in the database and are not in this response. Whether Monthly Pro is offered is `GET /api/billing`, not a field on the user.

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
    "cancel_at_period_end": false,
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

`statement` is built from the selected identity names, in order. Two identities read `I'm becoming disciplined and healthy.` When `context.statement` is set, that line is used instead.

`selections` has one entry per identity, at most two. `phase_name` is the current headline. `stage_name` is the journey label. `phases` marks each phase `complete`, `current`, or `upcoming`. `active_commitments` is how many commitments that identity has today.

`today.groups` lists the active goals that are due that day, under each identity. A catalog path starts with one goal. Three days in a row with at least one goal done add the next one on the following day. Two days in a row with none done remove the latest one, and the count stays at least one. An adaptive path uses the streak prefix instead of that count. `objective` is the goal. `cadence` is the frequency label. `due_on` is set for a one-time goal. `reason` is the optional line under the action. `implementation` is the chosen way. `implementations` are the other ways to meet the same goal. `status` is `open`, `done`, or `skipped`. `coming_up` lists active goals that are not due that day, with `when` for the chosen schedule. On an adaptive path it lists what tomorrow would add at the streak this close would produce.

`promises_kept` is how many days have been closed. A missed day does not reduce it. The product does not show a streak. `started_on` is the date the transformation began.

`tomorrow` lists the active goals due the day after `on`, including a goal earned by marking one done today. Each item has `identity_name`, `title`, and `cadence`. `prior_closed_on` is the latest closed date before `on`, or null when no earlier day has been closed. A gap before today does not remove those days.

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

`422` when the day count does not match: `Select exactly 3 days.` A daily commitment returns `This commitment is due every day.` A one-time commitment returns `This commitment happens once.` A bad month day returns `Choose a day from 1 to 28.`

`404` when the planned commitment is not on this transformation: `Commitment was not found.`

### POST /api/transformation/today/showed-up

Query: `on`. No body.

`200` closes the day when every due commitment is done or skipped, advances each path's phase day, and returns the document. The streak increments once when that path completed at least one due goal. It resets to 0 when that path completed none. Skip does not count. Completing several goals still adds one. Commitments that are not due do not block the day and are not misses. The last day of a phase rolls into the next phase at day 1. After the last phase, the path stays there and `completed` is true.

`409` when any due commitment is still `open`: `Finish or skip every commitment first.`

`409` when the day is already closed: `This day is already closed.`

## Coach

The coach routes require the `access_token` cookie and query `on`, the same date window as the transformation routes. Pro is `plan=pro` and `subscription_status` in `active`, `trialing`, or `past_due`. Anyone else gets `403` with `Coach is part of Pro.` A missing transformation is `404` with `Transformation has not started.`

The model suggests. The server validates and applies. The client cannot send goal text to apply.

### GET /api/coach

`200` returns the stored transcript and the current proposal, so the same conversation opens again. The transcript is the last eight turns. `proposal` is null when none is stored. This route does not call the model.

### POST /api/coach/messages

```json
{ "message": "I want to start working on my business" }
```

`200` returns the reply and, when the model has one, the stored proposal. A reply with no proposal is valid and clears any previous proposal. More than five goals is trimmed to five. The first kept goal is the quick win.

```json
{
  "reply": "Start with the smallest step.",
  "proposal": {
    "type": "plan",
    "rationale": "The work should be small enough to finish.",
    "goals": [
      {
        "identity_id": "disciplined",
        "objective": "Show up",
        "title": "Make the bed",
        "recurrence": "daily",
        "due_on": null,
        "weekdays": [],
        "times_per_week": null,
        "month_day": null,
        "position": 1,
        "reason": "Start with something you can finish."
      }
    ]
  }
}
```

`proposal.type` is `plan` or `today`. `plan` is a lasting change. `today` matches existing goals by identity and position and can shorten a title for the open day.

`503` when `AI_API_KEY` is empty: `Coach is not configured.`

`422` when the model output cannot be used: `The coach response could not be used.` Nothing is written.

`502` when the model call fails: `The coach could not reply.`

### POST /api/coach/apply

No body. The server loads the proposal stored by the last message, validates it again, and commits in one transaction.

`200` returns the transformation document. A `plan` sets `origin` to `adaptive`, appends `rationale`, replaces the current phase's coach commitments for the identities in the proposal, and rebuilds the open day. Closed days stay. A `today` proposal changes only the open day. Future planned titles stay. Tomorrow follows the streak again.

`409` when nothing is stored: `There is no proposal to apply.`

`422` when the stored proposal no longer matches the plan. Apply does not call the model, so a missing `AI_API_KEY` does not block it.

## GET /api/billing

Requires the `access_token` cookie. No body.

`200` says whether the four Stripe settings are set. Profile uses this to show or hide Monthly Pro and Manage billing. It is not stored on the user.

```json
{ "enabled": false }
```

`enabled` is true only when the Stripe secret, webhook secret, monthly price, and frontend origin are all set.

## POST /api/billing/checkout

Requires the `access_token` cookie. No body.

`200` returns a Stripe Checkout URL for the monthly price.

```json
{ "url": "https://checkout.stripe.com/c/pay/cs_test_..." }
```

Signup does not call Stripe. The first checkout creates a Stripe Customer and stores `stripe_customer_id`. The browser goes to `url`. Returning to `/profile` does not by itself set `plan` to `pro`. The webhook does that.

`409` when the status is already `active`, `trialing`, or `past_due`: `This account already has Pro.` A scheduled cancel is still `active`, so that person uses the portal.

`503` when any billing setting is missing: `Billing is not configured.`

## POST /api/billing/portal

Requires the `access_token` cookie. No body.

`200` returns a Stripe Customer Portal URL.

```json
{ "url": "https://billing.stripe.com/p/session/..." }
```

`409` when this account has no Stripe customer yet: `Billing is not set up for this account.`

`503` when any billing setting is missing: `Billing is not configured.`

## POST /api/billing/webhook

No session cookie. Stripe sends the raw body and a `Stripe-Signature` header. The API checks that signature before it reads the event.

`200` acknowledges the event.

```json
{ "received": true }
```

Handled events are `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, and `customer.subscription.deleted`. The row is found by `metadata.user_id`, then by `stripe_customer_id`. Applying the same subscription twice writes the same fields.

`plan` becomes `pro` when the Stripe status is `active`, `trialing`, or `past_due`. Every other status sets `plan` to `free`. `cancel_at_period_end` is stored on its own and does not change `plan`. A scheduled cancel stays `pro` until `customer.subscription.deleted`. That event sets `plan` to `free`, sets `cancel_at_period_end` to false, clears `stripe_subscription_id`, and keeps `stripe_customer_id`. The subscription row is not soft-deleted.

A valid event that matches no row is logged and still returns `200`.

`400` when the signature is missing or wrong: `Webhook signature is not valid.`

`503` when the webhook secret is missing: `Billing is not configured.`

