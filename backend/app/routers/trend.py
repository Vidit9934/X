from fastapi import APIRouter, Depends

from app.models import TrendScanRequest, TrendScanResponse
from app.services.openrouter import OpenRouterClient

router = APIRouter(prefix="/trend-scan", tags=["trend-scan"])

SYSTEM_PROMPT = (
    "You summarize a batch of tweets from AI/dev creators into the day's "
    "notable trends and discussion points. Be concise and concrete."
)


def get_llm_client() -> OpenRouterClient:
    return OpenRouterClient()


def summarize_tweets(client: OpenRouterClient, raw_tweets: list[str]) -> str:
    user_prompt = "\n---\n".join(raw_tweets)
    return client.chat(SYSTEM_PROMPT, user_prompt)


@router.post("", response_model=TrendScanResponse)
def run_trend_scan(
    request: TrendScanRequest,
    client: OpenRouterClient = Depends(get_llm_client),
) -> TrendScanResponse:
    summary = summarize_tweets(client, request.raw_tweets)
    return TrendScanResponse(summary=summary)
