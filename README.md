# Bookly Backend - FastAPI Beyond CRUD

A book review API with authentication, Celery background tasks, rate limiting, and a comprehensive test suite.

**Frontend:** [bookly-frontend](https://github.com/sanaullahaq/bookly-frontend) — the React SPA that consumes this API.

## Tech Stack

- **Framework**: FastAPI
- **Database**: PostgreSQL + SQLModel (SQLAlchemy 2.0 ORM)
- **Auth**: JWT (access + refresh tokens), email verification, password reset
- **Background Tasks**: Celery + Redis
- **Rate Limiting**: SlowAPI + Redis
- **Migrations**: Alembic
- **Testing**: pytest, pytest-asyncio, httpx

## Setup

```bash
python3.12 -m venv env && source env/bin/activate
pip install -r requirements.txt
```

Create a `.env` file with:

```env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/bookly
JWT_SECRET = 
JWT_ALGORITHM = 
ACCESS_TOKEN_EXPIRY_SECONDS = 3600
REFRESH_TOKEN_EXPIRY_DAYS = 2
REDIS_URL = redis://localhost:6379/0
JTI_EXPIRY_SECONDS = 3600
DB_ECHO = False

MAIL_USERNAME=example@mail.com
MAIL_PASSWORD=xxxxxxxxxxxxxxxx
# Gmail blocks plain password SMTP auth. You need an App Password:
# Go to your Google Account → Security
# Enable 2-Step Verification (mandatory prerequisite — App Passwords won't show up without it)
# Go to Security → 2-Step Verification → App passwords (or search "App passwords" in your Google Account search bar)
# Create one — name it something like fastapi-beyond-crud
# Google gives you a 16-character password like abcd efgh ijkl mnop — copy it without spaces: abcdefghijklmnop

MAIL_FROM=example@mail.com
MAIL_PORT=587
MAIL_SERVER=smtp.gmail.com
MAIL_FROM_NAME=Bookly
DOMAIN=localhost:8000
```

Run migrations:

```bash
alembic upgrade head
```

Start the server:

```bash
fastapi dev src/
```

Start a Celery worker in a separate terminal. Signup verification and password-reset emails are sent through Celery, so those flows will hang until a worker is running:

```bash
celery -A src.celery_tasks.c_app worker --loglevel=INFO
```

Flower (optional task monitor) runs on `:5555`:

```bash
celery -A src.celery_tasks.c_app flower
```

## Run Tests

```bash
pytest tests/ -v              # everything (124 tests)
pytest tests/test_tags/ -v    # one package
pytest tests/ -v -k "test_signup"
pytest tests/ -x              # stop on first failure
```

Tests need **PostgreSQL only**. `tests/conftest.py` overrides the app's DB session and disables SlowAPI rate limits, stubs `send_email.delay`, and bypasses the Redis JTI blocklist — no Redis, Celery, or SMTP needed.

The test database is **hardcoded** in `tests/conftest.py` (it deliberately does not read your `.env`):

```
postgresql+asyncpg://sanaullahaq:12345@localhost:5432/bookly_test
```

That database and role must exist, and every table is truncated before each run:

```sql
CREATE DATABASE bookly_test;
```

Async fixtures must use `@pytest_asyncio.fixture` rather than plain `@pytest.fixture`, even though `pyproject.toml` sets `asyncio_mode = "auto"`.

## Project Structure

```
src/
├── auth/       # User signup, login, verification, password reset
├── books/      # Book CRUD
├── reviews/    # Review CRUD with ownership checks
├── tags/       # Tag CRUD, many-to-many with books
├── db/         # Engine, session, models, Redis client
├── errors.py   # Custom exceptions + handlers
├── middleware.py   # CORS, logging, rate limiter
└── celery_tasks.py # Async email tasks

tests/
├── conftest.py     # Shared fixtures (engine, session, client, auth)
├── test_auth/      # 30 tests
├── test_books/     # 33 tests
├── test_reviews/   # 26 tests
└── test_tags/      # 35 tests
```

## API Endpoints

| Prefix | Description |
|--------|-------------|
| `/api/v1/auth` | Signup, login, logout, refresh, verify, password reset |
| `/api/v1/books` | Book CRUD |
| `/api/v1/reviews` | Review CRUD (admin list, user add/delete own) |
| `/api/v1/tags` | Tag CRUD, add tags to a book, remove a tag from a book |

Docs at `/api/v1/docs` (Swagger) and `/api/v1/redoc`.

### Tags

Tags are **global** rows joined to books by a `BookTag` link table. That gives three distinct operations, and the difference matters:

| Route | Effect |
|-------|--------|
| `POST /tags/book/{book_uid}/tags` | Find-or-create each name, then link it to the book. Returns the updated `BookOut`. Already-linked names and repeated names within one payload are skipped (`BookTag` has a composite PK, so a duplicate row would violate it). |
| `DELETE /tags/book/{book_uid}/tags/{tag_uid}` | Drops the `BookTag` link only. The `Tag` row survives and stays attached to any other book. Idempotent — removing a tag that was never attached is a no-op returning `200` with the unchanged book, and a malformed `tag_uid` is a no-op rather than a 500. |
| `DELETE /tags/{tag_uid}` | Deletes the tag **globally**, unlinking it from every book. Never use this for a per-book removal. |

`BookOut` and `BookDetailOut` nest `tags`, so the detail and list responses always reflect the current links.
