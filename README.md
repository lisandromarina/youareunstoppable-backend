# YouAreUnstoppable — Backend

FastAPI backend for the **YouAreUnstoppable** application.

The backend provides the API used by the React frontend. Sign-in is live. Transformations, daily commitments, the journey, the journal, the AI coach, and Stripe subscriptions come later.

---

## Current state

Email/password and Google sign-in are implemented. Every new account is Free and has a subscription row. Stripe is not connected.

Days, the journal, the coach, and billing routes are not built. The frontend prototype does not need them yet.

---

## Documentation

| Doc | What it covers |
| --- | --- |
| [docs/domain.md](docs/domain.md) | Days, streaks, journal, coach, and Free vs Pro |
| [docs/auth-decisions.md](docs/auth-decisions.md) | Why the auth and subscription tables are shaped this way |
| [docs/api.md](docs/api.md) | Live routes, request bodies, cookies, and status codes |
| [docs/implementation.md](docs/implementation.md) | How to build the API, phases, and what exists today |

Read those before adding routes.

---

## Tech Stack

* Python 3.12+
* FastAPI
* Uvicorn
* PostgreSQL
* SQLAlchemy
* Alembic
* Google sign-in (ID token verification)

Future technologies will be added as the application grows:

* AI Coach
* Stripe

---

## Requirements

Before starting the backend, make sure you have installed:

* Python 3.12 or newer
* pip
* Git

Check your Python installation:

```bash
python --version
```

Check pip:

```bash
pip --version
```

---

## Project Structure

```text
backend/
├── alembic/
├── src/
│   ├── api/
│   ├── core/
│   ├── models/
│   ├── schemas/
│   ├── services/
│   └── main.py
├── tests/
├── requirements.txt
└── README.md
```

---

## Installation

### 1. Navigate to the backend

```bash
cd backend
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

### 3. Activate the virtual environment

#### Windows — Command Prompt

```cmd
.venv\Scripts\activate.bat
```

#### Windows — PowerShell

```powershell
.venv\Scripts\Activate.ps1
```

After activation, you should see:

```text
(.venv)
```

at the beginning of your terminal prompt.

---

## Install Dependencies

With the virtual environment activated:

```bash
pip install -r requirements.txt
```

Create a `.env` file in `backend/` before migrating or starting the API. Required names:

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/youareunstoppable
JWT_SECRET=
GOOGLE_CLIENT_ID=
```

`GOOGLE_CLIENT_ID` is required for Google sign-in. Do not commit `.env`.

Apply the database migration:

```bash
alembic upgrade head
```

---

## Run the API

From the `backend` directory:

```bash
uvicorn src.main:app --reload
```

The API will start at:

```text
http://localhost:8000
```

---

## API Documentation

FastAPI automatically provides interactive API documentation.

Open:

```text
http://localhost:8000/docs
```

Alternative documentation:

```text
http://localhost:8000/redoc
```

---

## Hello World Endpoint

The current API includes:

```text
GET /api/hello
```

Open:

```text
http://localhost:8000/api/hello
```

Expected response:

```json
{
  "message": "Hello from YouAreUnstoppable!"
}
```

---

## Development

The `--reload` option automatically restarts the server when Python files change.

```bash
uvicorn src.main:app --reload
```

Stop the server with:

```text
CTRL + C
```

---

## Deactivate the Virtual Environment

When finished:

```bash
deactivate
```

---

## Environment Variables

Required for sign-in:

```text
DATABASE_URL=
JWT_SECRET=
GOOGLE_CLIENT_ID=
```

Leave `COOKIE_SECURE` unset for local HTTP. Set it to true when the API is served over HTTPS.

Stripe and the coach will add their own secrets later:

```text
STRIPE_SECRET_KEY=
AI_API_KEY=
```

Never commit secrets or `.env` files containing credentials to Git.

---

## Future Backend Architecture

As the application grows, the backend is expected to evolve toward:

```text
src/
├── main.py
├── api/
│   ├── auth.py
│   ├── today.py
│   ├── journey.py
│   ├── journal.py
│   └── coach.py
├── models/
├── schemas/
├── services/
└── core/
```

The core API concept will be:

```text
User
  │
  ├── Subscription
  │
  └── Transformation
        │
        ├── Identity
        ├── Commitments
        ├── Days
        └── Journal Entries
```

The most important domain entity is the **Day**.

Every completed day becomes another block in the user's transformation journey.
