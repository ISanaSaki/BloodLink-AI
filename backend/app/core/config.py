"""Typed application settings loaded from environment / .env (contract section 13)."""

from functools import lru_cache
from typing import Annotated, Any

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PLACEHOLDER_SECRET = "change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # App
    app_env: str = "development"
    app_name: str = "blood-donation-api"
    app_debug: bool = True
    api_v1_prefix: str = "/api/v1"
    secret_key: str = PLACEHOLDER_SECRET
    access_token_expire_minutes: int = 60
    timezone: str = "UTC"

    # Database
    database_url: str = "postgresql+psycopg://postgres:postgres@db:5432/blood_donation"
    db_echo: bool = False

    # Redis / Celery
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # OTP
    otp_ttl_seconds: int = 120
    otp_resend_seconds: int = 60
    otp_max_attempts: int = 5
    otp_rate_limit_window_seconds: int = 3600
    otp_max_requests_per_phone: int = 5
    otp_max_requests_per_ip: int = 15

    # SMS provider adapter
    sms_provider: str = "mock"
    sms_api_key: str = ""
    sms_sender: str = ""
    sms_timeout_seconds: int = 10
    sms_max_retries: int = 3
    # Demo mailbox: when set (development only), the mock provider appends the full
    # message here so the team can read OTP codes and response links. Never in production.
    sms_dev_outbox_file: str = ""

    # Maps provider adapter
    maps_provider: str = "mock"
    maps_api_key: str = ""
    maps_timeout_seconds: int = 8

    # Dispatch
    dispatch_batch_size: int = 5
    dispatch_response_window_minutes: int = 15
    dispatch_max_candidates: int = 100

    # Compatibility rules source (section 11.3 step 5).
    compatibility_policy: str = "demo"

    # Absolute base URL used when building the secure donor response link.
    public_app_base_url: str = "http://localhost:5500"

    # CORS - a comma separated list in the environment, so JSON decoding is disabled.
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _reject_placeholder_secret_in_production(self) -> "Settings":
        if self.app_env.lower() == "production" and self.secret_key == PLACEHOLDER_SECRET:
            raise ValueError("SECRET_KEY must be replaced before running in production")
        if self.app_env.lower() == "production" and self.sms_dev_outbox_file:
            raise ValueError("SMS_DEV_OUTBOX_FILE is a demo helper and must be empty in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
