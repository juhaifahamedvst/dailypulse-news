# syntax=docker/dockerfile:1
# DailyPulse news API 1.1.0: two stages (lesson 39.5). One image runs the API, the worker and migrate.

# Stage 1, build: uv installs the packages into /app/.venv. Nothing else from here ships.
FROM python:3.14.10-slim-trixie AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.10 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# Stage 2, runtime: the same Python image, the .venv and the code. No uv.
FROM python:3.14.10-slim-trixie AS runtime
ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
RUN groupadd --system --gid 10001 dailypulse \
 && useradd --system --uid 10001 --gid dailypulse --no-log-init dailypulse
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY settings.py news_api.py tasks.py migrate.py healthcheck.py ./
USER dailypulse

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "healthcheck.py"]
CMD ["fastapi", "run", "news_api.py", "--port", "8000"]
