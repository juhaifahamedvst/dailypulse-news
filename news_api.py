"""DailyPulse's news API, version 1.1.0: the whole stack (Chapter 39).

The headlines come from the news archive (PostgreSQL). The breaking-news banner lives in Redis, so
every copy of the API shows the same one. Each new banner queues a push alert for the Celery
worker (tasks.py). Start everything with `docker compose up`; the settings are in settings.py.
"""

import logging
import secrets
import socket
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Protocol

import psycopg
import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from kombu.exceptions import OperationalError
from pydantic import BaseModel
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialWithJitterBackoff

from settings import archive_conninfo, setting
from tasks import send_push_alert

VERSION = "1.1.0"

logging.basicConfig(
    level=setting("DAILYPULSE_LOG_LEVEL", "INFO"),
    format="%(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("dailypulse")


class Headline(BaseModel):
    id: int
    section: str
    title: str


class Breaking(BaseModel):
    text: str


class Archive(Protocol):
    """Where the headlines come from: a port (Chapter 37). PostgreSQL here, a list in the tests."""

    async def headlines(self, section: str | None) -> list[Headline]: ...


class PostgresArchive:
    def __init__(self, conninfo: str) -> None:
        self.conninfo = conninfo

    async def headlines(self, section: str | None) -> list[Headline]:
        async with await psycopg.AsyncConnection.connect(self.conninfo) as connection:
            cursor = await connection.execute(
                "SELECT id, section, title FROM headlines"
                " WHERE %(section)s::text IS NULL OR section = %(section)s ORDER BY id",
                {"section": section},
            )
            rows = await cursor.fetchall()
        return [Headline(id=id_, section=part, title=title) for id_, part, title in rows]


def queue_push_alert(text: str) -> None:
    """Hand the alert to the worker through Redis. If the broker is down, only the alert is lost."""
    try:
        send_push_alert.apply_async((text,), ignore_result=True)
    except OperationalError as error:
        logger.warning("push alert not queued (%s): %s", error, text)


@dataclass
class Newsroom:
    """Everything the endpoints need, made once at start-up. The tests make one from fakes."""

    edition: str
    editor_key: str
    archive: Archive
    cache: aioredis.Redis
    alert: Callable[[str], None]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    archive = PostgresArchive(archive_conninfo())
    found = await archive.headlines(None)  # fails at once if the archive isn't ready
    cache = aioredis.Redis.from_url(
        setting("DAILYPULSE_REDIS_URL"),
        decode_responses=True,
        socket_timeout=1,
        socket_connect_timeout=1,
        retry=Retry(ExponentialWithJitterBackoff(cap=0.1, base=0.01), retries=1),
    )
    edition = setting("DAILYPULSE_EDITION", "city")
    app.state.newsroom = Newsroom(
        edition, setting("DAILYPULSE_EDITOR_KEY"), archive, cache, queue_push_alert
    )
    logger.info(
        "news API %s, edition %s: %d headlines in the archive", VERSION, edition, len(found)
    )
    yield
    await cache.aclose()
    logger.info("news API stopping cleanly")


app = FastAPI(title="DailyPulse news API", version=VERSION, lifespan=lifespan)


def newsroom(request: Request) -> Newsroom:
    room: Newsroom = request.app.state.newsroom  # app.state holds anything: say what this is
    return room


Room = Annotated[Newsroom, Depends(newsroom)]


@app.get("/healthz")
async def health() -> dict[str, str]:
    """For Docker's health check: the version, and which container answered."""
    return {"status": "ok", "version": VERSION, "host": socket.gethostname()}


@app.get("/v1/headlines")
async def headlines(room: Room, section: str | None = None) -> dict[str, object]:
    return {
        "edition": room.edition,
        "host": socket.gethostname(),
        "breaking": await room.cache.get("breaking"),
        "headlines": await room.archive.headlines(section),
    }


@app.post("/v1/breaking", status_code=201)
async def set_breaking(
    item: Breaking, room: Room, x_editor_key: Annotated[str, Header()] = ""
) -> Breaking:
    """Editors put a banner over the headlines, and the worker pushes it to the app."""
    if not room.editor_key or not secrets.compare_digest(x_editor_key, room.editor_key):
        raise HTTPException(status_code=401, detail="a valid X-Editor-Key header is needed")
    await room.cache.set("breaking", item.text)
    room.alert(item.text)
    logger.info("breaking news: %s", item.text)
    return item
