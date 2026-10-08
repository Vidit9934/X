from supabase import Client


class ReaderAccountsRepo:
    def __init__(self, client: Client):
        self._client = client

    def list_all(self) -> list[dict]:
        result = self._client.table("reader_accounts").select("*").execute()
        return result.data

    def mark_retired(self, account_id: str) -> list[dict]:
        result = (
            self._client.table("reader_accounts")
            .update({"status": "retired"})
            .eq("id", account_id)
            .execute()
        )
        return result.data
