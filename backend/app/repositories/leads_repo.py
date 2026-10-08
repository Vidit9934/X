from supabase import Client


class LeadsRepo:
    def __init__(self, client: Client):
        self._client = client

    def insert(self, lead: dict) -> list[dict]:
        result = self._client.table("leads").insert(lead).execute()
        return result.data

    def list_all(self) -> list[dict]:
        result = self._client.table("leads").select("*").execute()
        return result.data
