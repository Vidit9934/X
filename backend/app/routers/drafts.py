import json

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_supabase
from app.models import Draft, DraftGenerationRequest, DraftGenerationResponse
from app.repositories.drafts_repo import DraftsRepo
from app.services.openrouter import OpenRouterClient

router = APIRouter(prefix="/drafts", tags=["drafts"])

POST_TYPES = [
    "build_in_public",
    "blocker_or_lesson",
    "insight_case_study",
    "trend_commentary",
    "question_or_build_in_public",
]

SYSTEM_PROMPT = (
    "You write 5 X (Twitter) post drafts in the user's voice, tuned for "
    "landing international clients by sharing insight/knowledge. "
    "Slot 1: build-in-public update. Slot 2: blocker/lesson learned. "
    "Slot 3: insight/mini case-study framed for a non-technical decision-maker. "
    "Slot 4: trend commentary. Slot 5: question-to-audience or a second "
    "build-in-public angle. "
    "Respond with strict JSON: a list of 5 objects, each with keys "
    "'body', 'image_idea', 'source_link' (source_link may be null)."
)


def get_llm_client() -> OpenRouterClient:
    return OpenRouterClient()


def get_drafts_repo() -> DraftsRepo:
    return DraftsRepo(get_supabase())


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        if stripped.endswith("```"):
            stripped = stripped[: -len("```")]
    return stripped.strip()


def _unwrap_list(parsed: object) -> object:
    """LLMs sometimes wrap the drafts array in an object, e.g. {"posts": [...]}.

    If the top level is a dict with exactly one key holding a list, unwrap it;
    otherwise return parsed unchanged so the strict-array check still catches
    genuinely malformed output.
    """
    if isinstance(parsed, dict) and len(parsed) == 1:
        (value,) = parsed.values()
        if isinstance(value, list):
            return value
    return parsed


@router.post("/generate", response_model=DraftGenerationResponse)
def generate_drafts(
    request: DraftGenerationRequest,
    client: OpenRouterClient = Depends(get_llm_client),
    repo: DraftsRepo = Depends(get_drafts_repo),
) -> DraftGenerationResponse:
    user_prompt = (
        f"Today's check-in: {request.check_in_text or '(no check-in provided)'}\n"
        f"Today's trend summary: {request.trend_summary}"
    )
    raw = client.chat(SYSTEM_PROMPT, user_prompt)

    try:
        parsed = _unwrap_list(json.loads(_strip_code_fence(raw)))
        if not isinstance(parsed, list) or len(parsed) != len(POST_TYPES):
            raise ValueError(f"expected {len(POST_TYPES)} draft objects, got {parsed!r}")
        drafts = [
            Draft(
                slot=i + 1,
                post_type=POST_TYPES[i],
                body=item["body"],
                image_idea=item.get("image_idea"),
                source_link=item.get("source_link"),
            )
            for i, item in enumerate(parsed)
        ]
    except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"LLM returned an unusable draft response: {exc}",
        ) from exc

    repo.insert_many(drafts)
    return DraftGenerationResponse(drafts=drafts)


@router.get("/today", response_model=list[dict])
def list_today_drafts(repo: DraftsRepo = Depends(get_drafts_repo)) -> list[dict]:
    return repo.list_today()
