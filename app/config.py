"""
Centralized configuration.

Every agent/client reads its keys and defaults from here instead of calling
os.getenv() directly, so there is exactly one place that knows how config
is loaded. Values come from environment variables / a local .env file (see
.env.example for the full list).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Search / retrieval keys ---
    tavily_api_key: str = ""
    semantic_scholar_api_key: str = ""  # optional: works without, faster with

    # --- LLM keys ---
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # --- Agent defaults ---
    default_web_results: int = 5
    default_paper_results: int = 5
    request_timeout_seconds: int = 20


@lru_cache
def get_settings() -> Settings:
    """Settings are cheap to build but read the .env file once and reuse it."""
    return Settings()
