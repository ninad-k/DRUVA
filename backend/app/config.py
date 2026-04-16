"""Centralized runtime configuration loaded from environment variables.

Every component reads settings from this module — do not read ``os.environ``
anywhere else in the codebase.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings. Override via environment variables."""
    return Settings()
