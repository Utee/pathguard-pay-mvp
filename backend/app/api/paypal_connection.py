import logging
from datetime import datetime, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import get_current_user
from app.db import get_db
from app.models import PayPalWalletConnection, UserAccount
from app.services.paypal import PayPalClient, PayPalError, PayPalResourceNotFound
from app.services.paypal_vault import (
    PayPalVaultConfigurationError,
    assert_vault_encryption_ready,
    decrypt_payment_token,
    encrypt_payment_token,
)

settings = get_settings()
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/paypal/connection", tags=["PayPal connection"])


def _frontend_redirect(**params) -> RedirectResponse:
    query = urlencode({key: value for key, value in params.items() if value is not None})
    url = f"{settings.paypal_frontend_url.rstrip('/')}/"
    if query:
        url = f"{url}?{query}"
    return RedirectResponse(url, status_code=303)


def _connection_response(connection: PayPalWalletConnection | None) -> dict:
    connected = bool(connection and connection.payment_token_ciphertext)
    return {
        "connected": connected,
        "status": "connected" if connected else "not_connected",
        "email_address": connection.email_address if connected else None,
        "connected_at": connection.connected_at if connected else None,
    }


@router.get("")
def get_paypal_connection(
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    connection = (
        db.query(PayPalWalletConnection)
        .filter(PayPalWalletConnection.user_id == current_user.id)
        .first()
    )
    return _connection_response(connection)


@router.post("/setup")
async def setup_paypal_connection(
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    try:
        assert_vault_encryption_ready()
    except PayPalVaultConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    connection = (
        db.query(PayPalWalletConnection)
        .filter(PayPalWalletConnection.user_id == current_user.id)
        .first()
    )
    if connection and connection.payment_token_ciphertext:
        raise HTTPException(
            status_code=409,
            detail="A PayPal wallet is already connected. Disconnect it before linking another account.",
        )

    try:
        data = await PayPalClient().create_setup_token(
            merchant_customer_id=f"pathguard-user-{current_user.id}",
            return_url=settings.paypal_connection_return_url,
            cancel_url=settings.paypal_connection_cancel_url,
        )
    except PayPalError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    setup_token_id = data.get("id")
    approval_url = next(
        (
            link.get("href")
            for link in data.get("links", [])
            if link.get("rel") == "approve" and link.get("href")
        ),
        None,
    )
    if not setup_token_id or not approval_url:
        raise HTTPException(
            status_code=502,
            detail="PayPal did not return a usable wallet approval URL.",
        )

    if connection is None:
        connection = PayPalWalletConnection(user_id=current_user.id)
        db.add(connection)

    connection.pending_setup_token_id = setup_token_id
    db.commit()

    return {
        "status": "PAYER_ACTION_REQUIRED",
        "setup_token_id": setup_token_id,
        "approval_url": approval_url,
    }


@router.get("/return")
async def paypal_connection_return(
    token: str | None = None,
    setup_token_id: str | None = None,
    ba_token: str | None = None,
    approval_session_id: str | None = None,
    db: Session = Depends(get_db),
):
    token_id = token or setup_token_id or ba_token or approval_session_id
    if not token_id:
        logger.warning("PayPal Vault callback did not include a recognized setup-token identifier")
        return _frontend_redirect(
            paypal_connect="error",
            reason="missing_return_token",
        )

    connection = (
        db.query(PayPalWalletConnection)
        .filter(PayPalWalletConnection.pending_setup_token_id == token_id)
        .first()
    )
    if not connection:
        logger.warning(
            "PayPal Vault callback did not match a pending connection; callback_parameter=%s",
            "token" if token else "setup_token_id" if setup_token_id else
            "ba_token" if ba_token else "approval_session_id",
        )
        return _frontend_redirect(
            paypal_connect="error",
            reason="pending_connection_not_found",
        )

    try:
        data = await PayPalClient().create_payment_token(token_id)
        payment_token_id = data.get("id")
        if not payment_token_id:
            raise PayPalError("PayPal did not return a reusable payment token.")

        payment_source = (data.get("payment_source") or {}).get("paypal") or {}
        customer = data.get("customer") or {}
        connection.payment_token_ciphertext = encrypt_payment_token(payment_token_id)
        connection.paypal_customer_id = customer.get("id") or connection.paypal_customer_id
        connection.payer_id = payment_source.get("payer_id") or payment_source.get("account_id")
        connection.email_address = payment_source.get("email_address")
        connection.pending_setup_token_id = None
        connection.connected_at = datetime.now(timezone.utc)
        connection.updated_at = datetime.now(timezone.utc)
        db.commit()
    except PayPalError as exc:
        logger.warning(
            "PayPal Vault token exchange failed: status=%s code=%s issue=%s debug_id=%s",
            exc.status_code,
            exc.name,
            exc.issue,
            exc.debug_id,
        )
        return _frontend_redirect(
            paypal_connect="error",
            reason="paypal_token_exchange_failed",
            paypal_status=exc.status_code,
            paypal_code=exc.name,
            paypal_issue=exc.issue,
            paypal_debug_id=exc.debug_id,
        )
    except PayPalVaultConfigurationError:
        logger.exception("PayPal Vault token exchange could not encrypt the returned token")
        return _frontend_redirect(
            paypal_connect="error",
            reason="encryption_key_invalid",
        )
    except ValueError:
        logger.exception("PayPal Vault token exchange returned an invalid response")
        return _frontend_redirect(
            paypal_connect="error",
            reason="invalid_token_response",
        )

    return _frontend_redirect(paypal_connect="connected")


@router.get("/cancel")
def paypal_connection_cancel(
    token: str | None = None,
    setup_token_id: str | None = None,
    ba_token: str | None = None,
    approval_session_id: str | None = None,
    db: Session = Depends(get_db),
):
    token_id = token or setup_token_id or ba_token or approval_session_id
    if token_id:
        connection = (
            db.query(PayPalWalletConnection)
            .filter(PayPalWalletConnection.pending_setup_token_id == token_id)
            .first()
        )
        if connection:
            connection.pending_setup_token_id = None
            db.commit()
    return _frontend_redirect(paypal_connect="cancelled")


@router.delete("")
async def disconnect_paypal(
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    connection = (
        db.query(PayPalWalletConnection)
        .filter(PayPalWalletConnection.user_id == current_user.id)
        .first()
    )
    if not connection or not connection.payment_token_ciphertext:
        return {"connected": False, "status": "not_connected"}

    try:
        payment_token_id = decrypt_payment_token(connection.payment_token_ciphertext)
        await PayPalClient().delete_payment_token(payment_token_id)
    except PayPalResourceNotFound:
        pass
    except PayPalError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except PayPalVaultConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    connection.payment_token_ciphertext = None
    connection.paypal_customer_id = None
    connection.payer_id = None
    connection.email_address = None
    connection.connected_at = None
    connection.pending_setup_token_id = None
    db.delete(connection)
    db.commit()
    return {"connected": False, "status": "not_connected"}
