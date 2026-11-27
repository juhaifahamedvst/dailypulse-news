# syntax=docker/dockerfile:1
# DailyPulse news API: two stages that ship (lesson 39.5), a test stage for CI (40.5), pinned by digest (40.6).

# Stage 1, build: uv installs the packages into /app/.venv. Nothing else from here ships.
FROM python:3.14.10-slim-trixie@sha256:22eafb370920ad8b429e0aec3fff433e0669968519f5d60469d83729c138b28b AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.10@sha256:a3ea1357342c1a4bf9a0c53a3deb1b55379aefa037338d8113d5771efa01774f /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# Stage 2, test: only with --target test. The dev packages and the tests, on the image's own Python.
FROM build AS test
ENV UV_NO_DEV=0
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked
COPY *.py ./
RUN uv run --no-sync pytest -q

# Stage 3, runtime: the same Python image, the .venv and the code. No uv, no tests.
FROM python:3.14.10-slim-trixie@sha256:22eafb370920ad8b429e0aec3fff433e0669968519f5d60469d83729c138b28b AS runtime
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
