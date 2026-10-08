from datetime import datetime, timezone

from supabase import Client

from app.models import Draft


class DraftsRepo:
    def __init__(self, client: Client):
        self._client = client

    def insert_many(self, drafts: list[Draft]) -> list[dict]:
        payload = [d.model_dump(exclude={"id", "created_at"}) for d in drafts]
        result = self._client.table("drafts").insert(payload).execute()
        return result.data

    def list_today(self) -> list[dict]:
        start_of_day = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        result = (
            self._client.table("drafts")
            .select("*")
            .gte("created_at", start_of_day.isoformat())
            .order("slot")
            .execute()
        )
        return result.data
