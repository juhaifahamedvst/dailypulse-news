"""The news API's tests, with no PostgreSQL, Redis or worker: run them with `uv run pytest`.

The endpoints get their newsroom from one dependency, so each test gives them one made of
fakes: the headlines in a list, fakeredis for the banner, and a list that collects the alerts.
"""

import asyncio

import fakeredis
import pytest
from fastapi.testclient import TestClient

import news_api
from news_api import Headline, MemoryBanner, Newsroom, RedisBanner

HEADLINES = [
    Headline(id=9001, section="city", title="Council approves the new tram line"),
    Headline(id=9003, section="weather", title="Snow expected on Thursday night"),
]


class ListArchive:
    async def headlines(self, section: str | None) -> list[Headline]:
        return [item for item in HEADLINES if section in (None, item.section)]


def client_with(alerts: list[str]) -> TestClient:
    room = Newsroom(
        edition="city",
        editor_key="test-key",
        archive=ListArchive(),
        banner=RedisBanner(fakeredis.FakeAsyncRedis(decode_responses=True)),
        alert=alerts.append,
    )
    news_api.app.dependency_overrides[news_api.newsroom] = lambda: room
    return TestClient(news_api.app)


def test_health_says_which_version() -> None:
    answer = client_with([]).get("/healthz")
    assert answer.json()["version"] == "1.3.0"


def test_health_on_a_path_without_a_z() -> None:
    answer = client_with([]).get("/v1/health").json()
    assert (answer["status"], answer["version"], answer["revision"]) == ("ok", "1.3.0", "none")


def test_headlines_by_section() -> None:
    answer = client_with([]).get("/v1/headlines", params={"section": "weather"})
    assert [item["id"] for item in answer.json()["headlines"]] == [9003]


def test_breaking_news_needs_the_key_and_queues_one_alert() -> None:
    alerts: list[str] = []
    client = client_with(alerts)
    refused = client.post("/v1/breaking", json={"text": "Polls close at 22:00"})
    assert refused.status_code == 401
    sent = client.post(
        "/v1/breaking", json={"text": "Polls close at 22:00"}, headers={"X-Editor-Key": "test-key"}
    )
    assert sent.status_code == 201
    assert client.get("/v1/headlines").json()["breaking"] == "Polls close at 22:00"
    assert alerts == ["Polls close at 22:00"]


def test_the_banner_alone() -> None:
    client = client_with([])
    assert client.get("/v1/breaking").json() == {"breaking": None}
    client.post(
        "/v1/breaking",
        json={"text": "Turnout passes 60 percent"},
        headers={"X-Editor-Key": "test-key"},
    )
    assert client.get("/v1/breaking").json() == {"breaking": "Turnout passes 60 percent"}


def test_the_sections_for_the_app_tabs() -> None:
    client = client_with([])
    assert client.get("/v1/sections").json() == {
        "sections": ["city", "election", "traffic", "weather"]
    }


def test_a_memory_banner_lives_in_one_copy_only() -> None:
    first, second = MemoryBanner(), MemoryBanner()
    asyncio.run(first.put("Polls close at 22:00"))
    assert asyncio.run(first.get()) == "Polls close at 22:00"
    assert asyncio.run(second.get()) is None  # another copy of the API never sees it


def test_the_preview_store_starts_with_no_servers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAILYPULSE_STORE", "memory")
    monkeypatch.setenv("DAILYPULSE_EDITOR_KEY", "test-key")
    news_api.app.dependency_overrides.clear()
    with TestClient(news_api.app) as client:  # runs the lifespan: no archive, no Redis
        answer = client.get("/v1/headlines").json()
    assert [item["id"] for item in answer["headlines"]] == [9001, 9002, 9003, 9004, 9005]
    assert answer["breaking"] is None
