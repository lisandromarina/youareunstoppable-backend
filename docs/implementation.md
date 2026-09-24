# YouAreUnstoppable — Backend implementation

How to build the API, and what exists now. Domain rules live in [domain.md](domain.md). Follow that file for what a day, a streak, and a subscription mean.

## Current state

Sign-in is live. Days, the journal, the coach, and Stripe are not.

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
```

`GET /api/hello` still returns:

```json
{
  "message": "Hello from YouAreUnstoppable!"
}
```

Request bodies, cookies, and status codes are in [api.md](api.md). Register, login, Google sign-in, and refresh set HttpOnly cookies and return the user. New subscriptions have `plan` `free`.

Not present yet: an AI client, Stripe Checkout, the billing portal, and webhooks.

The choices behind this slice are in [auth-decisions.md](auth-decisions.md). Domain rules for days and plans are in [domain.md](domain.md).

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

Later services will add:

```text
STRIPE_SECRET_KEY=
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

Email/password sign-in, Google sign-in, refresh tokens, and the user plus subscription tables. Modules:

```text
src/
├── main.py
├── api/
│   └── auth.py
├── models/
├── schemas/
│   └── auth.py
├── services/
│   └── auth.py
└── core/
```

Stripe ids live on `subscriptions` and stay null. Do not add Checkout in this phase.

### Phase 1 — frontend prototype

The mobile prototype runs on mock data. It does not need new endpoints.

### Phase 2 — the record

Add transformations, days, and journal entries. Routes stay thin. `services/` will own streak length, day status, and the rates in [domain.md](domain.md).

### Phase 3 — coach and billing

Add the coach and Stripe. A later billing slice fills `stripe_customer_id`, `stripe_subscription_id`, `subscription_status`, `current_period_end`, and `plan` on the existing subscription row. Entitlements follow the Free and Pro list in [domain.md](domain.md).

## Conventions

- Functional style. Prefer plain functions over classes for route handlers and services.
- Type hints on every function. Pydantic models for request and response bodies.
- Early returns for error cases. Happy path last.
- Expected auth failures raise `AuthError`. The app returns the same `detail` JSON as `HTTPException`.
- Lowercase underscored module names.
- Add a live route to the list under Current state, and describe the request and response in [api.md](api.md). Clients should not call a path that list does not include.

## Production

The intended production path is FastAPI on Vercel and PostgreSQL on a managed provider. Local development does not use Docker.
