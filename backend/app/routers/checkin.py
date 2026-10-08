from fastapi import APIRouter, Depends

from app.db import get_supabase
from app.models import CheckInRequest, CheckInResponse
from app.repositories.check_ins_repo import CheckInsRepo

router = APIRouter(prefix="/checkin", tags=["checkin"])


def get_check_ins_repo() -> CheckInsRepo:
    return CheckInsRepo(get_supabase())


@router.post("", response_model=CheckInResponse)
def submit_check_in(
    request: CheckInRequest,
    repo: CheckInsRepo = Depends(get_check_ins_repo),
) -> CheckInResponse:
    # A blank/missing text is a valid "no answer" signal, not an error — the
    # draft-generation step treats a null check-in as "no personal context
    # today, fall back to trend-based ideas" (requirements.txt section 4B).
    repo.insert(request.text or None)
    return CheckInResponse(text=request.text or None)


@router.get("/today", response_model=CheckInResponse)
def get_today_check_in(repo: CheckInsRepo = Depends(get_check_ins_repo)) -> CheckInResponse:
    latest = repo.get_latest_today()
    return CheckInResponse(text=latest["text"] if latest else None)
