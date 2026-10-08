from app.models import Draft
from app.repositories.drafts_repo import DraftsRepo
from app.repositories.leads_repo import LeadsRepo
from app.repositories.reader_accounts_repo import ReaderAccountsRepo
from app.repositories.style_repo import StyleRepo
from tests.fakes import FakeSupabaseClient


def test_drafts_repo_insert_and_list_today():
    client = FakeSupabaseClient()
    repo = DraftsRepo(client)

    drafts = [
        Draft(slot=1, post_type="build_in_public", body="body 1"),
        Draft(slot=2, post_type="blocker_or_lesson", body="body 2"),
    ]
    repo.insert_many(drafts)

    result = repo.list_today()
    assert len(result) == 2
    assert {r["body"] for r in result} == {"body 1", "body 2"}


def test_style_repo_upsert_updates_existing_by_handle():
    client = FakeSupabaseClient()
    repo = StyleRepo(client)

    repo.upsert({"creator_handle": "acme", "tone_notes": "v1"})
    repo.upsert({"creator_handle": "acme", "tone_notes": "v2"})

    all_rows = repo.get_all()
    assert len(all_rows) == 1
    assert all_rows[0]["tone_notes"] == "v2"


def test_leads_repo_insert_and_list():
    client = FakeSupabaseClient()
    repo = LeadsRepo(client)

    repo.insert({"source": "dm", "detail": "asked for a quote"})

    leads = repo.list_all()
    assert len(leads) == 1
    assert leads[0]["source"] == "dm"


def test_reader_accounts_repo_mark_retired():
    client = FakeSupabaseClient()
    repo = ReaderAccountsRepo(client)
    client.table("reader_accounts").insert(
        {"id": "1", "handle": "reader1", "status": "active"}
    ).execute()

    repo.mark_retired("1")

    accounts = repo.list_all()
    assert accounts[0]["status"] == "retired"
