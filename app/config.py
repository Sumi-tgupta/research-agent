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

    # --- Web search providers ---
    # Free-tier web search with automatic fallback (see app/agents/search_agent.py).
    # SEARCH_PROVIDER=auto tries the configured keyed providers in priority
    # order — Exa → Serper → Tavily — and always ends at keyless DuckDuckGo, so
    # search never hard-fails. Or force an exact order with a comma-separated
    # list, e.g. SEARCH_PROVIDER=serper,duckduckgo.
    search_provider: str = "auto"
    exa_api_key: str = ""            # https://exa.ai — recurring monthly free credit
    exa_search_type: str = "auto"    # auto | fast | neural | keyword
    serper_api_key: str = ""         # https://serper.dev — ~2,500 free lookups, no card
    tavily_api_key: str = ""         # https://tavily.com — OPTIONAL (free tier now needs a card)

    # --- Academic / retrieval keys ---
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

    # --- Persistence (Phase 11) ---
    # SQLite locally (zero setup); point DATABASE_URL at Supabase's Postgres
    # (Project Settings → Database → Connection string) in production. This is
    # the single source of truth for the saved library — app/db/session.py
    # reads it from here.
    database_url: str = "sqlite:///.cache/apex_research.db"

    # --- Optional Supabase Storage (Phase 11) ---
    # Only needed to offload rendered PDFs / chart PNGs to a bucket and hand
    # back signed URLs. Left blank, saved reports still fully reconstruct from
    # the database and PDFs re-render on demand — Storage is a pure add-on.
    # The service-role key is a SECRET: env only, never the frontend.
    supabase_service_key: str = ""
    supabase_storage_bucket: str = "reports"
    supabase_signed_url_ttl_seconds: int = 60 * 60 * 24 * 7  # 1 week

    # --- Multi-model routing (Phase 12) ---
    # When enabled and a Groq key is present, "light" stages (fact-check claim
    # extraction, chart detection) route to a fast small Groq model while the
    # "heavy" reasoning stages (planner, writer, reviewer) stay on Gemini. Each
    # call falls back to the other provider on failure — see app/model_router.py.
    llm_routing_enabled: bool = True
    groq_fast_model: str = "llama-3.1-8b-instant"

    # --- New free retrieval sources (Phase 12) ---
    # All keyless and free. Toggle any off without touching code.
    enable_openalex: bool = True
    enable_pubmed: bool = True       # via Europe PMC (JSON, keyless)
    enable_crossref: bool = True
    enable_wikipedia: bool = True
    # Crossref's "polite pool" is faster + more reliable when you identify
    # yourself with a contact email. Optional; blank uses the public pool.
    crossref_mailto: str = ""

    # --- Rate limiting / quotas (Phase 12) ---
    # Off by default so local dev and the test suite are unaffected. Turn on in
    # a shared/public deployment. Counts reset daily (UTC), tracked in the DB.
    rate_limit_enabled: bool = False
    rate_limit_per_day: int = 50          # signed-in users
    rate_limit_anon_per_day: int = 10     # anonymous callers (keyed by IP)

    # --- Retrieval cache backend (Phase 12) ---
    # "sqlite" (default, local file), "postgres" (reuse DATABASE_URL), or
    # "redis" (REDIS_URL). Host filesystems are ephemeral, so pick postgres or
    # redis in production to keep the cache across restarts.
    cache_backend: str = "sqlite"
    redis_url: str = ""

    # --- Error monitoring (Phase 13) ---
    # Blank DSN disables Sentry entirely (no-op). sentry-sdk is an OPTIONAL
    # import — the app runs fine without it installed (see app/main.py).
    sentry_dsn: str = ""
    app_env: str = "development"
    # 0.0 = errors only (no performance tracing). Raise toward 1.0 to sample
    # transactions; keep it low on the free tier to stay within event quotas.
    sentry_traces_sample_rate: float = 0.0

    # --- Frontend / CORS ---
    # Comma-separated list of origins allowed to call this API. The Next.js
    # dev server runs on :3000. Set to "*" to allow any origin (dev only).
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- Optional Supabase auth ---
    # When set, bearer tokens on requests are verified with this HS256 secret
    # (Supabase project → Settings → API → JWT Secret). Leaving it blank keeps
    # the API fully anonymous — auth is never required, only recognized.
    supabase_jwt_secret: str = ""
    supabase_url: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parsed CORS origins. '*' (any variant) means allow all."""
        raw = self.allowed_origins.strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def supabase_auth_enabled(self) -> bool:
        return bool(self.supabase_jwt_secret)

    @property
    def supabase_storage_enabled(self) -> bool:
        """True only when we have everything needed to upload to a bucket:
        the project URL and a service-role key. Missing either keeps Storage
        off and reports still reconstruct fully from the database."""
        return bool(self.supabase_url and self.supabase_service_key)



@lru_cache
def get_settings() -> Settings:
    """Settings are cheap to build but read the .env file once and reuse it."""
    return Settings()
