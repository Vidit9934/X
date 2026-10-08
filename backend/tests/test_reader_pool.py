from app.repositories.reader_accounts_repo import ReaderAccountsRepo
from app.services.reader_pool import ReaderPoolManager
from tests.fakes import FakeSupabaseClient


class FakeScraper:
    def __init__(self, accounts_info):
        self._accounts_info = accounts_info
        self.fetch_calls = []

    def fetch_recent_posts(self, handles, limit):
        self.fetch_calls.append((handles, limit))
        return [{"author_handle": h, "text": "x", "id": "1", "engagement_score": 0} for h in handles]

    def get_accounts_info(self):
        return self._accounts_info


def _seed_reader_account(client: FakeSupabaseClient, handle: str, status: str = "active") -> str:
    row = client.table("reader_accounts").insert({"handle": handle, "status": status}).execute().data[0]
    return row["id"]


def test_sync_health_retires_account_twscrape_reports_inactive():
    fake_supabase = FakeSupabaseClient()
    healthy_id = _seed_reader_account(fake_supabase, "healthy_reader")
    flagged_id = _seed_reader_account(fake_supabase, "flagged_reader")

    scraper = FakeScraper(
        accounts_info=[
            {"username": "healthy_reader", "active": True},
            {"username": "flagged_reader", "active": False},
        ]
    )
    repo = ReaderAccountsRepo(fake_supabase)
    manager = ReaderPoolManager(scraper, repo)

    manager.sync_health()

    accounts_by_id = {a["id"]: a for a in repo.list_all()}
    assert accounts_by_id[healthy_id]["status"] == "active"
    assert accounts_by_id[flagged_id]["status"] == "retired"


def test_sync_health_leaves_already_retired_account_alone():
    fake_supabase = FakeSupabaseClient()
    _seed_reader_account(fake_supabase, "already_retired", status="retired")

    scraper = FakeScraper(accounts_info=[{"username": "already_retired", "active": False}])
    repo = ReaderAccountsRepo(fake_supabase)
    manager = ReaderPoolManager(scraper, repo)

    manager.sync_health()  # should not raise or double-process

    accounts = repo.list_all()
    assert accounts[0]["status"] == "retired"


def test_fetch_recent_posts_delegates_to_scraper():
    scraper = FakeScraper(accounts_info=[])
    repo = ReaderAccountsRepo(FakeSupabaseClient())
    manager = ReaderPoolManager(scraper, repo)

    posts = manager.fetch_recent_posts(["alice"], limit=3)

    assert scraper.fetch_calls == [(["alice"], 3)]
    assert posts[0]["author_handle"] == "alice"
