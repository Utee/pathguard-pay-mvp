from typing import Any
from uuid import uuid4

import httpx

from app.core.config import get_settings


settings = get_settings()


class PayPalError(RuntimeError):
    """Base error for PayPal API failures."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        name: str | None = None,
        debug_id: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.name = name
        self.debug_id = debug_id


class PayPalResourceNotFound(PayPalError):
    """Raised when PayPal cannot find an order visible to the API caller."""

    pass


def _paypal_error(response: httpx.Response, operation: str) -> PayPalError:
    try:
        data = response.json()
    except ValueError:
        data = {}

    name = data.get("name")
    debug_id = data.get("debug_id")
    details = data.get("details") or []
    detail = details[0] if details else {}
    issue = detail.get("issue")
    description = detail.get("description")

    parts = [f"PayPal {operation} failed"]
    if name:
        parts.append(str(name))
    if issue:
        parts.append(str(issue))
    if description:
        parts.append(str(description))
    if debug_id:
        parts.append(f"debug_id={debug_id}")

    message = ": ".join(parts[:2])
    if len(parts) > 2:
        message += " — " + " — ".join(parts[2:])

    if response.status_code == 404 or issue == "INVALID_RESOURCE_ID" or name == "RESOURCE_NOT_FOUND":
        return PayPalResourceNotFound(
            message,
            status_code=response.status_code,
            name=name,
            debug_id=debug_id,
        )

    return PayPalError(
        message,
        status_code=response.status_code,
        name=name,
        debug_id=debug_id,
    )


class PayPalClient:
    """Small async client for the PayPal Orders v2 API."""

    def __init__(self):
        if not settings.paypal_client_id or not settings.paypal_client_secret:
            raise PayPalError(
                "PayPal credentials are not configured. "
                "Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in .env."
            )

        self.base_url = settings.paypal_base_url.rstrip("/")

    async def access_token(self) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/v1/oauth2/token",
                auth=(settings.paypal_client_id, settings.paypal_client_secret),
                data={"grant_type": "client_credentials"},
                headers={
                    "Accept": "application/json",
                    "Accept-Language": "en_US",
                },
            )

        if response.is_error:
            raise _paypal_error(response, "OAuth")

        data = response.json()
        access_token = data.get("access_token")
        if not access_token:
            raise PayPalError("PayPal OAuth succeeded but no access token was returned.")

        return access_token

    async def create_order(
        self,
        amount: float,
        currency: str,
        description: str,
        *,
        reference_id: str | None = None,
    ) -> dict[str, Any]:
        if amount <= 0:
            raise PayPalError("PayPal order amount must be greater than zero.")

        currency = currency.upper().strip()
        if len(currency) != 3:
            raise PayPalError("PayPal currency must be a valid 3-letter currency code.")

        token = await self.access_token()

        purchase_unit: dict[str, Any] = {
            "description": description[:127],
            "amount": {
                "currency_code": currency,
                "value": f"{amount:.2f}",
            },
        }
        if reference_id:
            purchase_unit["reference_id"] = reference_id[:256]

        payload = {
            "intent": "CAPTURE",
            "purchase_units": [purchase_unit],
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
            raise _paypal_error(response, "create order")

        return response.json()

    async def get_order(self, order_id: str) -> dict[str, Any]:
        if not order_id:
            raise PayPalError("PayPal order ID is required.")

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
            raise _paypal_error(response, "get order")

        return response.json()

    async def capture_order(self, order_id: str) -> dict[str, Any]:
        if not order_id:
            raise PayPalError("PayPal order ID is required.")

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
                    "PayPal-Request-Id": f"pathguard-capture-{order_id}",
                },
            )

        if response.is_error:
            raise _paypal_error(response, "capture order")

        return response.json()
