import asyncio
import time

from app.config import settings


class TwscrapeScraper:
    """Scraper Protocol implementation backed by twscrape (see services/scraper.py).

    twscrape is async-only; this class runs it via asyncio.run so the rest of
    the (synchronous) codebase — routers, ReaderPoolManager — never has to
    become async. Reader-account credentials come from settings.reader_accounts_json
    (JSON array of {handle, username, password, email, email_password}) and are
    loaded into twscrape's own local sqlite account pool, never into Supabase.
    """

    def __init__(self):
        self._pool = None

    async def _get_pool(self):
        if self._pool is None:
            from twscrape import AccountsPool

            self._pool = AccountsPool(settings.twscrape_db_path)
            await self._ensure_accounts_loaded(self._pool)
        return self._pool

    @staticmethod
    async def _ensure_accounts_loaded(pool) -> None:
        import json

        accounts = json.loads(settings.reader_accounts_json or "[]")
        for account in accounts:
            try:
                await pool.add_account(
                    account["username"],
                    account["password"],
                    account["email"],
                    account["email_password"],
                )
            except Exception:
                pass  # already registered — twscrape has no idempotent add

    def fetch_recent_posts(self, handles: list[str], limit: int) -> list[dict]:
        return asyncio.run(self._fetch_recent_posts_async(handles, limit))

    def get_accounts_info(self) -> list[dict]:
        """Per-account login/session status from twscrape's pool, for health sync."""
        return asyncio.run(self._get_accounts_info_async())

    async def _get_accounts_info_async(self) -> list[dict]:
        pool = await self._get_pool()
        accounts = await pool.accounts_info()
        return [
            {"username": a["username"], "active": a["active"]}
            for a in accounts
        ]

    async def _fetch_recent_posts_async(self, handles: list[str], limit: int) -> list[dict]:
        from twscrape import API

        pool = await self._get_pool()
        api = API(pool)

        posts: list[dict] = []
        for i, handle in enumerate(handles):
            if i > 0:
                time.sleep(settings.scrape_pacing_seconds)

            user = await api.user_by_login(handle)
            if user is None:
                continue

            async for tweet in api.user_tweets(user.id, limit=limit):
                posts.append(
                    {
                        "id": str(tweet.id),
                        "author_handle": handle,
                        "text": tweet.rawContent,
                        "engagement_score": _engagement_score(tweet),
                    }
                )

        return posts


def _engagement_score(tweet) -> float:
    # No formula is specified in requirements.txt — likes weighted 1x, retweets
    # 2x (a retweet is a stronger a signal than a like), replies 1x.
    likes = getattr(tweet, "likeCount", 0) or 0
    retweets = getattr(tweet, "retweetCount", 0) or 0
    replies = getattr(tweet, "replyCount", 0) or 0
    return float(likes + 2 * retweets + replies)
