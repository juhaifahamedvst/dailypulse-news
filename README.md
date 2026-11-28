# DailyPulse news stack

The DailyPulse news API 1.3.1 with everything it needs, started with one command: nginx in front, two copies of the
API, a Celery worker for push alerts, PostgreSQL for the archive and Redis for the banner and the queue.

- Tests, with no database: `uv run pytest`
- The book keeps no `uv.lock` here. Run `uv lock` once (or any `uv run`) before you build: the Dockerfile copies it.
- Settings, once:
  - copy `.env.example` to `.env` (Compose's `${DAILYPULSE_TAG}`) and `news.env.example` to `news.env`;
  - make `secrets/db_password.txt` and `secrets/editor_key.txt`, one line each, your own passwords.
  - Never commit `.env`, `news.env` or `secrets/`.
- Start: `docker compose up -d --build --wait`, then open <http://127.0.0.1:8039/v1/headlines>
- A backup of the archive: `docker compose --profile tools run --rm backup` (into `backups/archive.sql`)
- Rebuild the API on every save: `docker compose watch`
- Stop: `docker compose down` (keeps the data) or `docker compose down -v` (deletes the archive and the cache too)
