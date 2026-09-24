# YouAreUnstoppable — Backend implementation

How to build the API, and what exists now. Domain rules live in [domain.md](domain.md). Follow that file for what a day, a streak, and a subscription mean.

## Current state

The product is specified and not built.

Installed today, from `requirements.txt`:

- Python 3.12+
- FastAPI
- Uvicorn

`src/main.py` exposes one route:

```text
GET /api/hello
```

```json
{
  "message": "Hello from YouAreUnstoppable!"
}
```

Interactive docs:

```text
http://localhost:8000/docs
http://localhost:8000/redoc
```

Not present yet: PostgreSQL, SQLAlchemy, Google authentication, an AI client, Stripe.

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

Secrets stay in an uncommitted env file. Expected names, once those services exist:

```text
DATABASE_URL=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
STRIPE_SECRET_KEY=
AI_API_KEY=
```

Do not commit `.env` files or credentials.

## Phases

### Phase 0 — now

`GET /api/hello` only. Keep this route while the app is a starter.

### Phase 1 — frontend prototype

The mobile prototype runs on mock data. It does not need new endpoints. Do not add Phase 2 modules while that prototype is being built.

### Phase 2 — the record

Add users, transformations, days, and journal entries. Modules this phase introduces:

```text
src/
├── main.py
├── api/
│   ├── today.py
│   ├── journey.py
│   └── journal.py
├── models/
├── schemas/
├── services/
└── core/
```

`services/` owns streak length, day status, and the rates in [domain.md](domain.md). Routes stay thin and call those services.

### Phase 3 — accounts, coach, and billing

Add Google authentication, the coach, and Stripe. Modules this phase introduces:

```text
src/api/auth.py
src/api/coach.py
```

Plus the Stripe and AI clients behind services. Entitlements follow the Free and Pro list in [domain.md](domain.md).

## Conventions

- Functional style. Prefer plain functions over classes for route handlers and services.
- Type hints on every function. Pydantic models for request and response bodies.
- Early returns for error cases. Happy path last.
- `HTTPException` for expected errors.
- Lowercase underscored module names.
- Document a route here only after the handler exists. Clients should not call a path this file does not list under Current state.

## Production

The intended production path is FastAPI on Vercel and PostgreSQL on a managed provider. Local development does not use Docker.
