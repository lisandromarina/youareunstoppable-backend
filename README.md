# YouAreUnstoppable — Backend

FastAPI backend for the **YouAreUnstoppable** application.

The backend provides the API used by the React frontend and will eventually handle authentication, transformations, daily commitments, journey tracking, journal entries, AI coaching, and subscriptions.

---

## Tech Stack

* Python 3.12+
* FastAPI
* Uvicorn

Future technologies will be added as the application grows:

* PostgreSQL
* SQLAlchemy
* Google Authentication
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
├── .venv/
├── src/
│   ├── __init__.py
│   └── main.py
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

Environment variables will be added as external services are introduced.

For example:

```text
DATABASE_URL=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
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
  └── Transformation
        │
        ├── Identity
        ├── Commitments
        ├── Days
        └── Journal Entries
```

The most important domain entity is the **Day**.

Every completed day becomes another block in the user's transformation journey.
