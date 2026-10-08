from datetime import datetime, timezone

from supabase import Client


class CheckInsRepo:
    def __init__(self, client: Client):
        self._client = client

    def insert(self, text: str | None) -> list[dict]:
        result = self._client.table("check_ins").insert({"text": text}).execute()
        return result.data

    def get_latest_today(self) -> dict | None:
        start_of_day = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        result = (
            self._client.table("check_ins")
            .select("*")
            .gte("created_at", start_of_day.isoformat())
            .order("created_at", desc=True)
            .execute()
        )
        return result.data[0] if result.data else None
