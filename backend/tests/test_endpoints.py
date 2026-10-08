import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.drafts_repo import DraftsRepo
from app.routers import drafts as drafts_router
from app.routers import trend as trend_router
from tests.fakes import FakeSupabaseClient


class FakeLLMClient:
    def __init__(self, response_text: str):
        self._response_text = response_text

    def chat(self, system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        return self._response_text


@pytest.fixture
def client_with_fakes():
    fake_supabase = FakeSupabaseClient()
    repo = DraftsRepo(fake_supabase)

    app.dependency_overrides[drafts_router.get_drafts_repo] = lambda: repo
    yield TestClient(app), repo
    app.dependency_overrides.clear()


def test_trend_scan_returns_summary():
    app.dependency_overrides[trend_router.get_llm_client] = (
        lambda: FakeLLMClient("today's trend: agentic coding tools")
    )
    client = TestClient(app)

    response = client.post("/trend-scan", json={"raw_tweets": ["tweet 1", "tweet 2"]})

    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == {"summary": "today's trend: agentic coding tools"}


def test_generate_drafts_end_to_end(client_with_fakes):
    client, repo = client_with_fakes
    fake_drafts = [
        {"body": f"draft {i}", "image_idea": "idea", "source_link": None} for i in range(5)
    ]
    app.dependency_overrides[drafts_router.get_llm_client] = (
        lambda: FakeLLMClient(json.dumps(fake_drafts))
    )

    response = client.post(
        "/drafts/generate",
        json={"check_in_text": "shipped a feature", "trend_summary": "trend: X"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["drafts"]) == 5

    inbox = client.get("/drafts/today")
    assert len(inbox.json()) == 5


def test_generate_drafts_returns_502_on_malformed_llm_output(client_with_fakes):
    client, _repo = client_with_fakes
    app.dependency_overrides[drafts_router.get_llm_client] = (
        lambda: FakeLLMClient("not json at all")
    )

    response = client.post(
        "/drafts/generate",
        json={"check_in_text": None, "trend_summary": "trend: X"},
    )

    assert response.status_code == 502


def test_generate_drafts_unwraps_object_wrapped_array(client_with_fakes):
    client, repo = client_with_fakes
    fake_drafts = [
        {"body": f"draft {i}", "image_idea": "idea", "source_link": None} for i in range(5)
    ]
    app.dependency_overrides[drafts_router.get_llm_client] = (
        lambda: FakeLLMClient(json.dumps({"posts": fake_drafts}))
    )

    response = client.post(
        "/drafts/generate",
        json={"check_in_text": "shipped a feature", "trend_summary": "trend: X"},
    )

    assert response.status_code == 200
    assert len(response.json()["drafts"]) == 5
