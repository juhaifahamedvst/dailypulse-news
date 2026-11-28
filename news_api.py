"""DailyPulse's news API, version 1.3.0: ready for the cloud (Chapter 41).

The headlines come from the news archive (PostgreSQL). The breaking-news banner lives in Redis, so
every copy of the API shows the same one. Each new banner queues a push alert for the Celery
worker (tasks.py). Start everything with `docker compose up`; the settings are in settings.py.

New in 1.3.0: GET /v1/health, because Cloud Run keeps paths that end in z (like /healthz) for
itself, and DAILYPULSE_STORE=memory, a preview with no archive and no Redis: five built-in
headlines, and a banner that lives in one copy's memory. It is for a first deploy only.
"""

import logging
import os
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

VERSION = "1.3.0"

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
    """Where the headlines come from: a port (Chapter 37). PostgreSQL, or a list."""

    async def headlines(self, section: str | None) -> list[Headline]: ...


class Banner(Protocol):
    """Where the breaking-news banner is kept: Redis, shared by every copy, or one copy's memory."""

    async def get(self) -> str | None: ...

    async def put(self, text: str) -> None: ...


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


PREVIEW_HEADLINES = [
    Headline(id=9001, section="city", title="Council approves the new tram line"),
    Headline(id=9002, section="traffic", title="Riverside bridge closed this weekend"),
    Headline(id=9003, section="weather", title="Snow expected on Thursday night"),
    Headline(id=9004, section="election", title="Election 2027: find your polling station"),
    Headline(id=9005, section="election", title="Results night: live from 22:00 on Sunday"),
]


class MemoryArchive:
    """The preview's archive: the same five headlines in every copy, and nothing to connect to."""

    async def headlines(self, section: str | None) -> list[Headline]:
        return [item for item in PREVIEW_HEADLINES if section in (None, item.section)]


class RedisBanner:
    def __init__(self, cache: aioredis.Redis) -> None:
        self.cache = cache

    async def get(self) -> str | None:
        text = await self.cache.get("breaking")
        return text.decode() if isinstance(text, bytes) else text

    async def put(self, text: str) -> None:
        await self.cache.set("breaking", text)


class MemoryBanner:
    """One copy's memory: another copy of the API never sees it, and a restart forgets it."""

    def __init__(self) -> None:
        self.text: str | None = None

    async def get(self) -> str | None:
        return self.text

    async def put(self, text: str) -> None:
        self.text = text


def queue_push_alert(text: str) -> None:
    """Hand the alert to the worker through Redis. If the broker is down, only the alert is lost."""
    try:
        send_push_alert.apply_async((text,), ignore_result=True)
    except OperationalError as error:
        logger.warning("push alert not queued (%s): %s", error, text)


def no_push_alert(text: str) -> None:
    logger.info("preview: no push alert for: %s", text)


@dataclass
class Newsroom:
    """Everything the endpoints need, made once at start-up. The tests make one from fakes."""

    edition: str
    editor_key: str
    archive: Archive
    banner: Banner
    alert: Callable[[str], None]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    edition = setting("DAILYPULSE_EDITION", "city")
    editor_key = setting("DAILYPULSE_EDITOR_KEY")
    store = setting("DAILYPULSE_STORE", "servers")
    cache: aioredis.Redis | None = None
    if store == "memory":
        archive: Archive = MemoryArchive()
        banner: Banner = MemoryBanner()
        alert = no_push_alert
    else:
        archive = PostgresArchive(archive_conninfo())
        cache = aioredis.Redis.from_url(
            setting("DAILYPULSE_REDIS_URL"),
            decode_responses=True,
            socket_timeout=1,
            socket_connect_timeout=1,
            retry=Retry(ExponentialWithJitterBackoff(cap=0.1, base=0.01), retries=1),
        )
        banner = RedisBanner(cache)
        alert = queue_push_alert
    found = await archive.headlines(None)  # fails at once if the archive isn't ready
    app.state.newsroom = Newsroom(edition, editor_key, archive, banner, alert)
    logger.info(
        "news API %s, edition %s, store %s: %d headlines", VERSION, edition, store, len(found)
    )
    yield
    if cache is not None:
        await cache.aclose()
    logger.info("news API stopping cleanly")


app = FastAPI(title="DailyPulse news API", version=VERSION, lifespan=lifespan)


def newsroom(request: Request) -> Newsroom:
    room: Newsroom = request.app.state.newsroom  # app.state holds anything: say what this is
    return room


Room = Annotated[Newsroom, Depends(newsroom)]


def health_report() -> dict[str, str]:
    """The version, which copy answered, and (on Cloud Run) which revision it runs."""
    return {
        "status": "ok",
        "version": VERSION,
        "host": socket.gethostname(),
        "revision": os.environ.get("K_REVISION", "none"),
    }


@app.get("/healthz")
async def health() -> dict[str, str]:
    """For Docker's health check and Compose. Cloud Run keeps this path for itself."""
    return health_report()


@app.get("/v1/health")
async def health_v1() -> dict[str, str]:
    """The same answer on a path every platform passes on: no z at the end."""
    return health_report()


@app.get("/v1/headlines")
async def headlines(room: Room, section: str | None = None) -> dict[str, object]:
    return {
        "edition": room.edition,
        "host": socket.gethostname(),
        "breaking": await room.banner.get(),
        "headlines": await room.archive.headlines(section),
    }


@app.get("/v1/breaking")
async def breaking(room: Room) -> dict[str, object]:
    """Only the banner: on election night the phone app asks for it every 10 seconds."""
    return {"breaking": await room.banner.get()}


@app.post("/v1/breaking", status_code=201)
async def set_breaking(
    item: Breaking, room: Room, x_editor_key: Annotated[str, Header()] = ""
) -> Breaking:
    """Editors put a banner over the headlines, and the worker pushes it to the app."""
    if not room.editor_key or not secrets.compare_digest(x_editor_key, room.editor_key):
        raise HTTPException(status_code=401, detail="a valid X-Editor-Key header is needed")
    await room.banner.put(item.text)
    room.alert(item.text)
    logger.info("breaking news: %s", item.text)
    return item


@app.get("/v1/sections")
async def sections() -> dict[str, list[str]]:
    """The sections the phone app shows as tabs."""
    return {"sections": ["city", "election", "traffic", "weather"]}
