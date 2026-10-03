from typing import Any
from uuid import uuid4

import httpx

from app.core.config import get_settings


settings = get_settings()


class PayPalError(RuntimeError):
    """Raised when a PayPal API operation fails."""

    pass


class PayPalClient:
    """
    Client for interacting with the PayPal REST API.
    """

    def __init__(self):
        if (
            not settings.paypal_client_id
            or not settings.paypal_client_secret
        ):
            raise PayPalError(
                "PayPal credentials are not configured. "
                "Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in .env."
            )

        self.base_url = settings.paypal_base_url.rstrip("/")

    async def access_token(self) -> str:
        """
        Get an OAuth access token from PayPal.
        """

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/v1/oauth2/token",
                auth=(
                    settings.paypal_client_id,
                    settings.paypal_client_secret,
                ),
                data={
                    "grant_type": "client_credentials",
                },
                headers={
                    "Accept": "application/json",
                    "Accept-Language": "en_US",
                },
            )

        if response.is_error:
            raise PayPalError(
                f"PayPal OAuth failed: {response.text}"
            )

        data = response.json()

        access_token = data.get("access_token")

        if not access_token:
            raise PayPalError(
                "PayPal OAuth succeeded but no access token was returned."
            )

        return access_token

    async def create_order(
        self,
        amount: float,
        currency: str,
        description: str,
    ) -> dict[str, Any]:
        """
        Create a PayPal checkout order.
        """

        if amount <= 0:
            raise PayPalError(
                "PayPal order amount must be greater than zero."
            )

        currency = currency.upper().strip()

        if len(currency) != 3:
            raise PayPalError(
                "PayPal currency must be a valid 3-letter currency code."
            )

        token = await self.access_token()

        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "description": description[:127],
                    "amount": {
                        "currency_code": currency,
                        "value": f"{amount:.2f}",
                    },
                }
            ],
            "application_context": {
                "brand_name": "PathGuard",
                "user_action": "PAY_NOW",
                "return_url": settings.paypal_return_url,
                "cancel_url": settings.paypal_cancel_url,
            },
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/v2/checkout/orders",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Prefer": "return=representation",
                    "PayPal-Request-Id": f"pathguard-{uuid4()}",
                },
            )

        if response.is_error:
            raise PayPalError(
                f"PayPal create order failed: {response.text}"
            )

        return response.json()

    async def get_order(
        self,
        order_id: str,
    ) -> dict[str, Any]:
        """
        Retrieve a PayPal order by ID.

        This is useful for verifying the order before
        granting the user access to a paid PathGuard feature.
        """

        if not order_id:
            raise PayPalError(
                "PayPal order ID is required."
            )

        token = await self.access_token()

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{self.base_url}/v2/checkout/orders/{order_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
            )

        if response.is_error:
            raise PayPalError(
                f"PayPal get order failed: {response.text}"
            )

        return response.json()

    async def capture_order(
        self,
        order_id: str,
    ) -> dict[str, Any]:
        """
        Capture an approved PayPal order.
        """

        if not order_id:
            raise PayPalError(
                "PayPal order ID is required."
            )

        token = await self.access_token()

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/v2/checkout/orders/{order_id}/capture",
                json={},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Prefer": "return=representation",
                    "PayPal-Request-Id": (
                        f"pathguard-capture-{order_id}"
                    ),
                },
            )

        if response.is_error:
            raise PayPalError(
                f"PayPal capture failed: {response.text}"
            )

        return response.json()