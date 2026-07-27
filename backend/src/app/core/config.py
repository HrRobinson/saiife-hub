from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every environment variable the backend reads, in one place.

    Defaults are DEV/TEST values only. This repo is public: no real project ids,
    endpoints, peppers or Stripe keys ever appear here.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "sqlite+aiosqlite:///./hub-dev.db"
    ENV: Literal["dev", "test", "prod"] = "dev"
    LOG_LEVEL: Literal["debug", "info", "warning", "error"] = "info"
    APP_VERSION: str = "dev"

    APP_URL: str = "https://app.saiife.localhost:3001"
    MARKETING_URL: str = "https://saiife.localhost:3000"

    APP_JWT_SECRET: str = "dev-only-change-me"
    APP_JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_TTL_SECONDS: int = 15 * 60
    REFRESH_TOKEN_TTL_SECONDS: int = 30 * 24 * 3600

    COOKIE_DOMAIN: str = ".saiife.localhost"
    COOKIE_SECURE: bool = True
    COOKIE_SAMESITE: str = "lax"

    MAILGUN_API_KEY: str = ""
    MAILGUN_DOMAIN: str = ""
    MAILGUN_FROM: str = "saiife <noreply@saiife.localhost>"
    MAILGUN_BASE_URL: str = "https://api.eu.mailgun.net"

    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    GOOGLE_OAUTH_REDIRECT_URI: str = "https://api.saiife.localhost:8000/api/v1/auth/google/callback"

    PASSKEY_RP_ID: str = "saiife.localhost"
    PASSKEY_RP_NAME: str = "saiife"
    PASSKEY_ORIGIN: str = "https://app.saiife.localhost:3001"

    # Account tokens. The pepper is a SECRET and must be identical to the pepper
    # saiife-cloud verifies with — see docs/2026-07-21-saiife-cloud-admin-api-contract.md.
    ACCOUNT_TOKEN_PEPPER: str = "dev-only-pepper-not-a-real-value"

    # saiife-cloud admin API. Empty URL => the in-memory mock is used.
    CLOUD_ADMIN_API_URL: str = ""
    CLOUD_ADMIN_API_KEY: str = ""

    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_ID: str = ""
    STRIPE_SIGNATURE_TOLERANCE_SECONDS: int = 300


settings = Settings()
