# YouAreUnstoppable — Backend implementation

How to build the API, and what exists now. Domain rules live in [domain.md](domain.md). Follow that file for what a day, a streak, and a subscription mean.

## Current state

Sign-in is live. The transformation record is live: catalog, start, today, showed up, and reset. Monthly billing is live: Checkout, the Customer Portal, and webhooks write the existing subscription row. Journal, coach, and an AI client are not. Pro does not unlock a separate product yet.

Installed today, from `requirements.txt`:

- Python 3.12+
- FastAPI
- Uvicorn
- SQLAlchemy 2
- Alembic
- PostgreSQL driver (`psycopg`)
- Argon2 password hashes
- PyJWT
- Google auth, used to verify ID tokens
- Stripe, used for Checkout, the Customer Portal, and webhooks

Live routes:

```text
GET  /api/hello
POST /api/auth/register
POST /api/auth/login
POST /api/auth/google
POST /api/auth/password
POST /api/auth/refresh
POST /api/auth/logout
GET  /api/me
GET  /api/billing
POST /api/billing/checkout
POST /api/billing/portal
POST /api/billing/webhook
GET  /api/catalog
GET  /api/transformation
POST /api/transformation
PUT  /api/transformation
DELETE /api/transformation
POST /api/transformation/today/commitments/{commitment_id}/toggle
POST /api/transformation/today/commitments/{commitment_id}/replace
POST /api/transformation/today/commitments/{commitment_id}/skip
POST /api/transformation/today/showed-up
```

`GET /api/hello` still returns:

```json
{
  "message": "Hello from YouAreUnstoppable!"
}
```

Request bodies, cookies, and status codes are in [api.md](api.md). Register, login, Google sign-in, and refresh set HttpOnly cookies and return the user. New subscriptions have `plan` `free`. Checkout does not run at signup. A webhook is what sets `plan` to `pro`.

Not present yet: an AI client. Premium will write the same transformation tables. It does not get its own goal or message tables. This billing slice does not gate Today, Journey, or Progress.

The choices behind sign-in are in [auth-decisions.md](auth-decisions.md). Domain rules for the path, the two streaks, and the year are in [domain.md](domain.md).

## Run

```bash
cd backend
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Windows Command Prompt:

```cmd
.venv\Scripts\activate.bat
```

```bash
pip install -r requirements.txt
uvicorn src.main:app --reload
```

The API listens at `http://localhost:8000`. `--reload` restarts on file changes. Stop it with CTRL+C. Leave the virtual environment with `deactivate`.

Interactive docs:

```text
http://localhost:8000/docs
http://localhost:8000/redoc
```

Secrets stay in an uncommitted env file. Required for this slice:

```text
DATABASE_URL=
JWT_SECRET=
GOOGLE_CLIENT_ID=
```

`GOOGLE_CLIENT_ID` is required for Google sign-in. Email and password sign-in works without it. Leave `COOKIE_SECURE` unset for local HTTP. Set it to true when the API is served over HTTPS.

Billing reads these when Checkout, the portal, or a webhook runs. The API still boots if they are empty. Checkout and the portal then return `503`.

```text
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_ID=
FRONTEND_ORIGIN=
```

Monthly Pro and Manage billing appear only when all four are set. If any one is empty, Profile hides them and Checkout returns `503`.

`STRIPE_PRICE_ID` is the monthly Price id from the Stripe Dashboard. `FRONTEND_ORIGIN` is the web app origin, `http://localhost:5173` locally. Point the Stripe webhook at `POST /api/billing/webhook` on the API host. Locally, forward with the Stripe CLI to `http://localhost:8000/api/billing/webhook`.

Later services will add:

```text
AI_API_KEY=
```

Do not commit `.env` files or credentials.

Apply the schema before the first run against PostgreSQL:

```bash
alembic upgrade head
```

## Phases

### Phase 0 — hello

`GET /api/hello` remains.

### Accounts — now

Email/password sign-in, Google sign-in, refresh tokens, and the user plus subscription tables. Signup still inserts `plan=free` and does not call Stripe.

### The record — now

Curated identities and directions live in `src/domain/catalog.py`. Starting a transformation copies that path onto the user. Routes stay thin. `src/services/transformation.py` owns which commitments are due, schedule changes, promises kept, phase advance, and the year.

```text
src/
├── main.py
├── api/
│   ├── auth.py
│   ├── billing.py
│   ├── deps.py
│   └── transformation.py
├── domain/
│   └── catalog.py
├── models/
├── schemas/
│   ├── auth.py
│   ├── billing.py
│   └── transformation.py
├── services/
│   ├── auth.py
│   ├── billing.py
│   └── transformation.py
└── core/
```

### Billing — now

`POST /api/billing/checkout` and `POST /api/billing/portal` are signed in. `POST /api/billing/webhook` is not. The webhook verifies `Stripe-Signature` on the raw body. `apply_subscription` sets `plan=pro` only when Stripe's status is `active`, `trialing`, or `past_due`. A scheduled cancel is still `active` with `cancel_at_period_end` true, so Pro lasts through `current_period_end`. `customer.subscription.deleted` sets `plan=free`, clears `cancel_at_period_end` and `stripe_subscription_id`, and keeps `stripe_customer_id`. A valid event that matches no row returns 200. Stripe customer and subscription ids stay off `GET /api/me`.

### Later — coach

A later AI writes `origin`, `rationale`, phases, and planned commitments on the transformation that already exists. Do not add a separate Premium record. Do not add an `is_premium` column. When that path exists, Pro access is `plan=pro` and `subscription_status` in `active`, `trialing`, or `past_due`.

## Conventions

- Functional style. Prefer plain functions over classes for route handlers and services.
- Type hints on every function. Pydantic models for request and response bodies.
- Early returns for error cases. Happy path last.
- Expected auth failures raise `AuthError`. Expected transformation failures raise `DomainError`. The app returns the same `detail` JSON as `HTTPException`.
- Lowercase underscored module names.
- Add a live route to the list under Current state, and describe the request and response in [api.md](api.md). Clients should not call a path that list does not include.

## Production

The intended production path is FastAPI on Vercel and PostgreSQL on a managed provider. Local development does not use Docker.
