from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class DraftStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    posted = "posted"
    skipped = "skipped"


class ReaderAccountStatus(str, Enum):
    warming = "warming"
    active = "active"
    reserve = "reserve"
    retired = "retired"


class StyleProfile(BaseModel):
    id: Optional[str] = None
    creator_handle: str
    hook_patterns: list[str] = []
    structure_notes: str = ""
    tone_notes: str = ""
    formatting_notes: str = ""
    updated_at: Optional[datetime] = None


class Draft(BaseModel):
    id: Optional[str] = None
    slot: int
    post_type: str
    body: str
    image_idea: Optional[str] = None
    source_link: Optional[str] = None
    status: DraftStatus = DraftStatus.pending
    created_at: Optional[datetime] = None


class Lead(BaseModel):
    id: Optional[str] = None
    draft_id: Optional[str] = None
    source: str
    detail: Optional[str] = None
    created_at: Optional[datetime] = None


class ReaderAccount(BaseModel):
    id: Optional[str] = None
    handle: str
    status: ReaderAccountStatus = ReaderAccountStatus.warming
    last_used_at: Optional[datetime] = None
    failure_count: int = 0


class TrendScanRequest(BaseModel):
    raw_tweets: list[str]


class TrendScanResponse(BaseModel):
    summary: str


class DraftGenerationRequest(BaseModel):
    check_in_text: Optional[str] = None
    trend_summary: str


class DraftGenerationResponse(BaseModel):
    drafts: list[Draft]


class CheckInRequest(BaseModel):
    text: Optional[str] = None


class CheckInResponse(BaseModel):
    text: Optional[str] = None
