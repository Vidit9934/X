import twscrape

from app.services.twscrape_scraper import TwscrapeScraper


class FakeUser:
    def __init__(self, uid: int):
        self.id = uid


class FakeTweet:
    def __init__(self, tid: int, text: str, likes=1, retweets=2, replies=3):
        self.id = tid
        self.rawContent = text
        self.likeCount = likes
        self.retweetCount = retweets
        self.replyCount = replies


class FakeAccountsPool:
    def __init__(self, db_path):
        self.db_path = db_path
        self.added_accounts = []

    async def add_account(self, username, password, email, email_password):
        self.added_accounts.append(username)

    async def accounts_info(self):
        return [
            {"username": "reader1", "active": True},
            {"username": "reader2", "active": False},
        ]


class FakeAPI:
    def __init__(self, pool):
        self.pool = pool

    async def user_by_login(self, login):
        return FakeUser(uid=1)

    async def user_tweets(self, uid, limit=-1, kv=None):
        for i in range(limit):
            yield FakeTweet(tid=i, text=f"tweet {i} from user {uid}")


def test_fetch_recent_posts_maps_fields_and_respects_limit(monkeypatch):
    monkeypatch.setattr(twscrape, "AccountsPool", FakeAccountsPool)
    monkeypatch.setattr(twscrape, "API", FakeAPI)

    scraper = TwscrapeScraper()
    posts = scraper.fetch_recent_posts(["alice"], limit=2)

    assert len(posts) == 2
    assert posts[0]["author_handle"] == "alice"
    assert posts[0]["text"] == "tweet 0 from user 1"
    assert posts[0]["engagement_score"] == 1 + 2 * 2 + 3  # likes + 2*retweets + replies


def test_fetch_recent_posts_paces_between_handles(monkeypatch):
    monkeypatch.setattr(twscrape, "AccountsPool", FakeAccountsPool)
    monkeypatch.setattr(twscrape, "API", FakeAPI)

    sleep_calls = []
    monkeypatch.setattr(
        "app.services.twscrape_scraper.time.sleep", lambda seconds: sleep_calls.append(seconds)
    )

    scraper = TwscrapeScraper()
    scraper.fetch_recent_posts(["alice", "bob", "carol"], limit=1)

    # paced between handles, not before the first or with a burst of N calls
    assert len(sleep_calls) == 2


def test_get_accounts_info_returns_username_and_active(monkeypatch):
    monkeypatch.setattr(twscrape, "AccountsPool", FakeAccountsPool)
    monkeypatch.setattr(twscrape, "API", FakeAPI)

    scraper = TwscrapeScraper()
    info = scraper.get_accounts_info()

    assert info == [
        {"username": "reader1", "active": True},
        {"username": "reader2", "active": False},
    ]
