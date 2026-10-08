from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = ""
    supabase_key: str = ""
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "deepseek/deepseek-v4-flash"

    # Stage 2 (automation) — scraper + creator watchlists
    twscrape_db_path: str = "twscrape_accounts.db"
    # JSON array of {"handle", "username", "password", "email", "email_password"}
    # for the reader-account pool. Never store real X credentials in Supabase or
    # git — this is the only place they live (loaded straight into twscrape's own
    # local sqlite account pool at startup).
    reader_accounts_json: str = ""
    study_creator_handles: str = ""  # comma-separated, style-study list
    watchlist_creator_handles: str = ""  # comma-separated, reply-target list
    scrape_posts_per_handle: int = 5
    scrape_pacing_seconds: float = 2.0

    def study_creator_handle_list(self) -> list[str]:
        return _parse_handles(self.study_creator_handles)

    def watchlist_creator_handle_list(self) -> list[str]:
        return _parse_handles(self.watchlist_creator_handles)


def _parse_handles(raw: str) -> list[str]:
    return [h.strip() for h in raw.split(",") if h.strip()]


settings = Settings()
