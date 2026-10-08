from typing import Protocol


class Tweet(Protocol):
    id: str
    author_handle: str
    text: str
    engagement_score: float


class Scraper(Protocol):
    """Interface for reading tweets from X.

    Stage 1 has no concrete implementation — callers pass raw tweet text
    directly to the trend-scan endpoint instead. Stage 2 implements this
    with a twscrape-backed adapter so callers never change.
    """

    def fetch_recent_posts(self, handles: list[str], limit: int) -> list[Tweet]:
        ...
