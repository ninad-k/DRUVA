"""Centralized runtime configuration loaded from environment variables.

Every component reads settings from this module — do not read ``os.environ``
anywhere else in the codebase.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_WEAK_JWT_SECRETS = frozenset({"", "change-me", "changeme", "secret"})


class Settings(BaseSettings):
    """Application settings, populated from environment variables prefixed ``DHRUVA_``."""

    model_config = SettingsConfigDict(
        env_prefix="DHRUVA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ----------------------------------------------------------------
    env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    service_name: str = "dhruva-backend"
    service_version: str = "0.1.0"

    # --- Networking ---------------------------------------------------------
    http_host: str = "0.0.0.0"
    http_port: int = 8000
    grpc_host: str = "0.0.0.0"
    grpc_port: int = 50051
    ws_host: str = "0.0.0.0"
    ws_port: int = 8001

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:4173"]
    )

    @model_validator(mode="after")
    def _reject_insecure_defaults_outside_dev(self) -> "Settings":
        """Fail fast instead of booting staging/production with dev secrets."""
        if self.env == "development":
            return self
        problems: list[str] = []
        if self.jwt_secret in _WEAK_JWT_SECRETS or len(self.jwt_secret) < 32:
            problems.append("DHRUVA_JWT_SECRET must be a random string of at least 32 characters")
        if not self.master_key:
            problems.append("DHRUVA_MASTER_KEY must be set (base64-encoded 32 bytes)")
        if self.debug:
            problems.append("DHRUVA_DEBUG must be false")
        if problems:
            raise ValueError(
                f"Insecure configuration for DHRUVA_ENV={self.env}: " + "; ".join(problems)
            )
        return self

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: object) -> object:
        if isinstance(v, str) and not v.startswith("["):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    # --- Database -----------------------------------------------------------
    db_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/dhruva"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # --- Redis --------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"

    # --- JWT ----------------------------------------------------------------
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "dhruva.local"
    jwt_audience: str = "dhruva-users"
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 7 * 24 * 3600

    # --- Encryption for broker credentials ---------------------------------
    master_key: str = ""  # base64-encoded 32 bytes

    # --- Observability ------------------------------------------------------
    otlp_endpoint: str = "http://localhost:4317"
    enable_tracing: bool = True
    enable_metrics: bool = True

    # --- Email --------------------------------------------------------------
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@dhruva.local"

    # --- Telegram -----------------------------------------------------------
    telegram_bot_token: str = ""

    # --- Execution / approvals ---------------------------------------------
    approval_ttl_minutes: int = 15

    # --- Twilio WhatsApp (optional approval channel) -------------------------
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""  # e.g. "whatsapp:+14155238886"

    # --- AI Advisor --------------------------------------------------------
    # Pluggable LLM backend. Default uses a local Ollama server so users can
    # run gemma/llama/qwen without any cloud key. Switch via env vars:
    #   DHRUVA_ADVISOR_LLM_PROVIDER=anthropic | openai | ollama | openai_compatible | none
    advisor_enabled: bool = True
    advisor_llm_provider: Literal[
        "none", "anthropic", "openai", "ollama", "openai_compatible"
    ] = "ollama"
    advisor_llm_model: str = "gemma3:4b"
    advisor_llm_base_url: str = "http://localhost:11434"
    advisor_llm_api_key: str = ""
    advisor_llm_timeout_s: int = 120
    advisor_llm_max_tokens: int = 1024
    advisor_llm_temperature: float = 0.2
    # Daily refresh time (IST 18:30 = 13:00 UTC — after NSE close).
    advisor_refresh_cron_utc_hour: int = 13
    advisor_refresh_cron_utc_minute: int = 0
    # Risk caps used by the allocator.
    advisor_max_positions: int = 8
    advisor_per_position_stop_loss_pct: float = 10.0

    # --- Multibagger scanners / portfolio ----------------------------------
    scanner_enabled: bool = True
    scanner_run_cron_utc_hour: int = 13   # 18:30 IST — post NSE close
    scanner_run_cron_utc_minute: int = 30
    fundamentals_refresh_cron_utc_hour: int = 20  # Sun 01:30 IST ~= Sat 20:00 UTC
    fundamentals_refresh_cron_utc_minute: int = 0
    fundamentals_refresh_day_of_week: str = "sat"
    fundamentals_max_concurrency: int = 4
    fundamentals_stale_days: int = 7
    screener_base_url: str = "https://www.screener.in"

    # --- Pluggable fundamentals provider (Council + DCF) -------------------
    # ``repository`` reads the local FundamentalSnapshot cache. ``http`` calls
    # a user-supplied JSON API; ``static`` is for tests; ``null`` disables
    # fundamentals (Council still works on ratios-only / pure reasoning).
    fundamentals_provider: Literal[
        "repository", "http", "static", "null"
    ] = "repository"
    fundamentals_http_base_url: str = ""
    fundamentals_http_api_key: str = ""
    fundamentals_http_timeout_s: float = 15.0

    # --- Pluggable calendar provider (Phase H) --------------------------------
    # ``null`` disables the calendar (default). ``http`` calls a user-supplied
    # REST API; ``static`` returns an empty list (seed via code for demos).
    calendar_provider: Literal["null", "static", "http"] = "null"
    calendar_http_base_url: str = ""
    calendar_http_api_key: str = ""
    calendar_http_timeout_s: float = 15.0

    # --- Pluggable news provider (Phase I) ------------------------------------
    news_provider: Literal["null", "static", "http"] = "null"
    news_http_base_url: str = ""
    news_http_api_key: str = ""
    news_http_timeout_s: float = 15.0
    news_sentiment_llm_enabled: bool = False

    # --- FreqAI adaptive ML pipeline (Phase L) --------------------------------
    # When enabled, FreqAIStrategy trains and predicts alongside (or instead of)
    # the HMM regime detector.  Set freqai_model_kind to switch the learner.
    freqai_enabled: bool = False
    freqai_model_kind: Literal[
        "random_forest", "gradient_boost", "logistic"
    ] = "random_forest"
    freqai_retrain_every: int = 100
    freqai_label_threshold: float = 0.001
    freqai_model_dir: str = ""   # absolute path; empty = no persistence

    # Risk caps — extends existing RiskEngine
    max_positions: int = 20
    sector_concentration_cap_pct: float = 25.0
    vcp_hard_stop_pct: float = 4.5

    # Market cycle allocation (% of capital to deploy per regime)
    market_cycle_bull_pct: float = 90.0
    market_cycle_neutral_pct: float = 60.0
    market_cycle_bear_pct: float = 30.0

    # Default per-position allocation cap
    max_per_position_pct: float = 5.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings. Override via environment variables."""
    return Settings()
