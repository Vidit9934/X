from supabase import Client


class StyleRepo:
    def __init__(self, client: Client):
        self._client = client

    def get_all(self) -> list[dict]:
        result = self._client.table("style_profiles").select("*").execute()
        return result.data

    def upsert(self, profile: dict) -> list[dict]:
        result = (
            self._client.table("style_profiles")
            .upsert(profile, on_conflict="creator_handle")
            .execute()
        )
        return result.data
