# Jibon Sathu Backend

Zone A (cloud) FastAPI service: Postgres schema, health check, and `POST /sync/push`.

## Quick start

1. Start Postgres: `docker compose up -d` (published on host **`127.0.0.1:5433`** — see `docker-compose.yml`).
2. `python -m venv .venv` then activate and `pip install -e ".[dev]"`
3. Copy `.env.example` to `.env` and adjust if needed. If you already have a `.env`, set **`DATABASE_URL`** to use port **5433** and user/password **`jibon`/`jibon`** unless you changed them in Compose.
4. `alembic upgrade head`
5. `uvicorn app.main:app --reload`

### Still seeing `password authentication failed for user "jibon"`?

- **Wrong process on the port:** An older `.env` may still point at **`5432`**, which is often a **system PostgreSQL**, not this project’s container. Prefer **`127.0.0.1:5433`** as in `.env.example`.
- **Stale Docker volume:** If you ever changed `POSTGRES_*` in Compose, Postgres keeps the old data directory. Reset with:

  `docker compose down -v` then `docker compose up -d`

  (**`-v` deletes the DB volume** — only do this if you do not need that data.)

### `localhost` vs `127.0.0.1` (Windows)

`localhost` can resolve to IPv6 (`::1`) first; another Postgres may listen there. This repo defaults to **`127.0.0.1`** in connection examples.

## Tests

With Postgres running and `DATABASE_URL` set (see `.env.example`):

```bash
pytest
```
