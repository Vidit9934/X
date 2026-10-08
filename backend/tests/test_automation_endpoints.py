import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_supabase
from app.main import app
from app.repositories.check_ins_repo import CheckInsRepo
from app.repositories.style_repo import StyleRepo
from app.routers import automation as automation_router
from app.routers import checkin as checkin_router
from app.routers import drafts as drafts_router
from tests.fakes import FakeSupabaseClient


class FakeLLMClient:
    def __init__(self, response_text: str):
        self._response_text = response_text
        self.calls = []

    def chat(self, system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self._response_text


class FakeReaderPool:
    def __init__(self, posts_by_handle: dict[str, list[dict]]):
        self._posts_by_handle = posts_by_handle
        self.fetch_calls: list[tuple[list[str], int]] = []

    def fetch_recent_posts(self, handles, limit):
        self.fetch_calls.append((list(handles), limit))
        posts = []
        for handle in handles:
            posts.extend(self._posts_by_handle.get(handle, []))
        return posts


@pytest.fixture
def fake_supabase(monkeypatch):
    client = FakeSupabaseClient()
    monkeypatch.setattr("app.main.get_supabase", lambda: client)
    monkeypatch.setattr("app.routers.automation.get_supabase", lambda: client)
    monkeypatch.setattr("app.routers.checkin.get_supabase", lambda: client)
    yield client


@pytest.fixture
def api_client(fake_supabase):
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_automated_trend_scan_scrapes_study_handles_and_summarizes(monkeypatch, api_client):
    monkeypatch.setattr(settings, "study_creator_handles", "alice,bob")
    reader_pool = FakeReaderPool(
        {
            "alice": [{"author_handle": "alice", "text": "alice tweet", "id": "1", "engagement_score": 0}],
            "bob": [{"author_handle": "bob", "text": "bob tweet", "id": "2", "engagement_score": 0}],
        }
    )
    app.dependency_overrides[automation_router.get_reader_pool] = lambda: reader_pool
    app.dependency_overrides[automation_router.get_llm_client] = (
        lambda: FakeLLMClient("today's trend: agentic tools")
    )

    response = api_client.post("/automation/trend-scan")

    assert response.status_code == 200
    assert response.json() == {"summary": "today's trend: agentic tools"}
    assert reader_pool.fetch_calls == [(["alice", "bob"], settings.scrape_posts_per_handle)]


def test_style_profile_refresh_upserts_per_handle(monkeypatch, api_client, fake_supabase):
    monkeypatch.setattr(settings, "study_creator_handles", "alice,bob")
    reader_pool = FakeReaderPool(
        {
            "alice": [{"author_handle": "alice", "text": "alice tweet", "id": "1", "engagement_score": 0}],
            "bob": [{"author_handle": "bob", "text": "bob tweet", "id": "2", "engagement_score": 0}],
        }
    )
    style_json = json.dumps(
        {
            "hook_patterns": ["question hook"],
            "structure_notes": "short paragraphs",
            "tone_notes": "direct",
            "formatting_notes": "occasional emoji",
        }
    )
    app.dependency_overrides[automation_router.get_reader_pool] = lambda: reader_pool
    app.dependency_overrides[automation_router.get_llm_client] = lambda: FakeLLMClient(style_json)

    response = api_client.post("/automation/style-profile-refresh")

    assert response.status_code == 200
    profiles = response.json()
    assert {p["creator_handle"] for p in profiles} == {"alice", "bob"}
    # one scrape call per handle (not batched), each respecting the per-handle limit
    assert reader_pool.fetch_calls == [
        (["alice"], settings.scrape_posts_per_handle),
        (["bob"], settings.scrape_posts_per_handle),
    ]

    stored = StyleRepo(fake_supabase).get_all()
    assert {row["creator_handle"] for row in stored} == {"alice", "bob"}


def test_style_profile_refresh_returns_502_on_malformed_llm_output(monkeypatch, api_client):
    monkeypatch.setattr(settings, "study_creator_handles", "alice")
    reader_pool = FakeReaderPool(
        {"alice": [{"author_handle": "alice", "text": "alice tweet", "id": "1", "engagement_score": 0}]}
    )
    app.dependency_overrides[automation_router.get_reader_pool] = lambda: reader_pool
    app.dependency_overrides[automation_router.get_llm_client] = lambda: FakeLLMClient("not json")

    response = api_client.post("/automation/style-profile-refresh")

    assert response.status_code == 502


def test_reply_target_scan_returns_raw_posts_unscored(monkeypatch, api_client):
    monkeypatch.setattr(settings, "watchlist_creator_handles", "bigcreator")
    reader_pool = FakeReaderPool(
        {
            "bigcreator": [
                {"author_handle": "bigcreator", "text": "someone has a real problem", "id": "9", "engagement_score": 42}
            ]
        }
    )
    app.dependency_overrides[automation_router.get_reader_pool] = lambda: reader_pool

    response = api_client.post("/automation/reply-target-scan")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["text"] == "someone has a real problem"


def test_checkin_intake_and_today_round_trip(api_client):
    response = api_client.post("/checkin", json={"text": "shipped the scraper adapter"})
    assert response.status_code == 200

    today = api_client.get("/checkin/today")
    assert today.status_code == 200
    assert today.json() == {"text": "shipped the scraper adapter"}


def test_checkin_no_answer_falls_back_to_null(api_client):
    response = api_client.post("/checkin", json={"text": None})
    assert response.status_code == 200
    assert response.json() == {"text": None}

    today = api_client.get("/checkin/today")
    assert today.json() == {"text": None}
