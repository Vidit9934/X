from fastapi import FastAPI

from app.db import get_supabase
from app.routers import automation, checkin, drafts, trend

app = FastAPI(title="AI Twitter Growth Copilot — Backend")

app.include_router(trend.router)
app.include_router(drafts.router)
app.include_router(automation.router)
app.include_router(checkin.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/health/db")
def health_db() -> dict:
    """Hit by the Supabase-keepalive GitHub Actions workflow — a trivial query
    is enough to reset the free tier's 7-day idle-pause clock."""
    get_supabase().table("reader_accounts").select("id").limit(1).execute()
    return {"status": "ok"}
