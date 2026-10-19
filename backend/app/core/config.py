from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ---------------------------------------------------------
    # Application
    # ---------------------------------------------------------

    app_name: str = "PathGuard Pay"

    # ---------------------------------------------------------
    # Database
    # ---------------------------------------------------------

    database_url: str = "sqlite:///./pathguard_pay.db"
    jwt_secret_key: str | None = None
    access_token_expire_minutes: int = 60
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---------------------------------------------------------
    # OpenAI
    # ---------------------------------------------------------

    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"
    openrouter_api_key: str | None = None
    openrouter_model: str = "openai/gpt-chat-latest"

    # ---------------------------------------------------------
    # PayPal
    # ---------------------------------------------------------

    paypal_client_id: str | None = None

    paypal_client_secret: str | None = None

    # Sandbox:
    # https://api-m.sandbox.paypal.com
    #
    # Live:
    # https://api-m.paypal.com
    paypal_base_url: str = (
        "https://api-m.sandbox.paypal.com"
    )

    # PayPal redirects the user here after approval.
    paypal_return_url: str = (
        "http://127.0.0.1:8000"
        "/api/payments/paypal/return"
    )

    # PayPal redirects the user here when checkout is cancelled.
    paypal_cancel_url: str = (
        "http://127.0.0.1:8000"
        "/api/payments/paypal/cancel"
    )

    # Frontend URL to which our backend redirects the user
    # after PayPal approval/cancellation.
    paypal_frontend_url: str = (
        "http://localhost:5173"
    )

    # ---------------------------------------------------------
    # Pydantic Settings
    # ---------------------------------------------------------

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()