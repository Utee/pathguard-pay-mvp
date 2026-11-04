from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ---------------------------------------------------------
    # Application
    # ---------------------------------------------------------

    app_name: str = "PathGuard Pay"
    public_api_url: str | None = None

    # ---------------------------------------------------------
    # Database
    # ---------------------------------------------------------

    database_url: str = "sqlite:///./pathguard_pay.db"
    jwt_secret_key: str | None = None
    access_token_expire_minutes: int = 60
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---------------------------------------------------------
    # OpenRouter AI
    # ---------------------------------------------------------

    openrouter_api_key: str | None = None
    openrouter_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # ---------------------------------------------------------
    # PayPal
    # ---------------------------------------------------------

    paypal_client_id: str | None = None

    paypal_client_secret: str | None = None
    paypal_vault_encryption_key: str | None = None

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
    paypal_connection_return_url: str = (
        "http://127.0.0.1:8000/api/paypal/connection/return"
    )
    paypal_connection_cancel_url: str = (
        "http://127.0.0.1:8000/api/paypal/connection/cancel"
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

    @model_validator(mode="after")
    def hosted_callback_urls(self):
        if self.public_api_url:
            base = self.public_api_url.rstrip("/")
            callbacks = {
                "paypal_return_url": "/api/payments/paypal/return",
                "paypal_cancel_url": "/api/payments/paypal/cancel",
                "paypal_connection_return_url": "/api/paypal/connection/return",
                "paypal_connection_cancel_url": "/api/paypal/connection/cancel",
            }
            for field, path in callbacks.items():
                if field not in self.model_fields_set:
                    setattr(self, field, base + path)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

