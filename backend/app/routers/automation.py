import json

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.db import get_supabase
from app.models import StyleProfile, TrendScanResponse
from app.repositories.reader_accounts_repo import ReaderAccountsRepo
from app.repositories.style_repo import StyleRepo
from app.routers.trend import summarize_tweets
from app.services.openrouter import OpenRouterClient
from app.services.reader_pool import ReaderPoolManager
from app.services.twscrape_scraper import TwscrapeScraper

router = APIRouter(prefix="/automation", tags=["automation"])

STYLE_SYSTEM_PROMPT = (
    "You study a creator's recent X (Twitter) posts and extract their writing "
    "style as structured data — hook patterns, structure, tone, and formatting "
    "habits — never copy their text verbatim. "
    "Respond with strict JSON: an object with keys 'hook_patterns' (a list of "
    "short strings), 'structure_notes', 'tone_notes', 'formatting_notes' "
    "(each a short string)."
)


def get_llm_client() -> OpenRouterClient:
    return OpenRouterClient()


def get_reader_pool() -> ReaderPoolManager:
    return ReaderPoolManager(TwscrapeScraper(), ReaderAccountsRepo(get_supabase()))


def get_style_repo() -> StyleRepo:
    return StyleRepo(get_supabase())


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        if stripped.endswith("```"):
            stripped = stripped[: -len("```")]
    return stripped.strip()


@router.post("/trend-scan", response_model=TrendScanResponse)
def run_automated_trend_scan(
    reader_pool: ReaderPoolManager = Depends(get_reader_pool),
    client: OpenRouterClient = Depends(get_llm_client),
) -> TrendScanResponse:
    handles = settings.study_creator_handle_list()
    posts = reader_pool.fetch_recent_posts(handles, settings.scrape_posts_per_handle)
    raw_tweets = [post["text"] for post in posts]
    summary = summarize_tweets(client, raw_tweets or ["(no posts scraped today)"])
    return TrendScanResponse(summary=summary)


@router.post("/style-profile-refresh", response_model=list[StyleProfile])
def run_style_profile_refresh(
    reader_pool: ReaderPoolManager = Depends(get_reader_pool),
    client: OpenRouterClient = Depends(get_llm_client),
    style_repo: StyleRepo = Depends(get_style_repo),
) -> list[StyleProfile]:
    profiles = []
    for handle in settings.study_creator_handle_list():
        posts = reader_pool.fetch_recent_posts([handle], settings.scrape_posts_per_handle)
        if not posts:
            continue

        user_prompt = "\n---\n".join(post["text"] for post in posts)
        raw = client.chat(STYLE_SYSTEM_PROMPT, user_prompt)

        try:
            parsed = json.loads(_strip_code_fence(raw))
            profile = StyleProfile(
                creator_handle=handle,
                hook_patterns=parsed["hook_patterns"],
                structure_notes=parsed["structure_notes"],
                tone_notes=parsed["tone_notes"],
                formatting_notes=parsed["formatting_notes"],
            )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise HTTPException(
                status_code=502,
                detail=f"LLM returned an unusable style-profile response for {handle}: {exc}",
            ) from exc

        style_repo.upsert(profile.model_dump(exclude={"id", "updated_at"}))
        profiles.append(profile)

    return profiles


@router.post("/reply-target-scan", response_model=list[dict])
def run_reply_target_scan(
    reader_pool: ReaderPoolManager = Depends(get_reader_pool),
) -> list[dict]:
    """Stage 2 stub: scrapes the watchlist and returns raw recent posts.

    No scoring/ranking yet — Stage 3 adds engagement-velocity scoring and
    "someone has a real problem" prioritization on top of this data.
    """
    handles = settings.watchlist_creator_handle_list()
    return reader_pool.fetch_recent_posts(handles, settings.scrape_posts_per_handle)
