import logging

from app.repositories.reader_accounts_repo import ReaderAccountsRepo
from app.services.twscrape_scraper import TwscrapeScraper

logger = logging.getLogger("reader_pool")


class ReaderPoolManager:
    """Glues twscrape's built-in account rotation to our own reader_accounts
    bookkeeping table.

    twscrape's AccountsPool already rotates across logged-in accounts for us;
    this class is only responsible for health monitoring — syncing a failed
    login/session/challenge on the twscrape side into our Supabase table so
    a flagged account stops being routed traffic (retire on first failure,
    never "retry harder" — see requirements.txt section 2).
    """

    def __init__(self, scraper: TwscrapeScraper, reader_accounts_repo: ReaderAccountsRepo):
        self._scraper = scraper
        self._reader_accounts_repo = reader_accounts_repo

    def fetch_recent_posts(self, handles: list[str], limit: int) -> list[dict]:
        return self._scraper.fetch_recent_posts(handles, limit)

    def sync_health(self) -> None:
        """Mark any account twscrape reports as failed/locked as retired."""
        accounts_info = self._scraper.get_accounts_info()
        unhealthy_handles = {
            info["username"] for info in accounts_info if not info.get("active", True)
        }
        if not unhealthy_handles:
            return

        for account in self._reader_accounts_repo.list_all():
            if account["handle"] in unhealthy_handles and account["status"] != "retired":
                logger.warning(
                    "retiring reader account %s: twscrape reports login/session failure",
                    account["handle"],
                )
                self._reader_accounts_repo.mark_retired(account["id"])
