from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import get_current_user
from app.db import get_db
from app.models import (
    AuditEvent,
    PayPalOrder,
    PaymentRequest,
    Recipient,
    RiskAssessment,
    ReviewEvent,
    UserAccount,
    PayPalWalletConnection,
)
from app.schemas.payment import (
    AnalyzePaymentRequest,
    AnalyzePaymentResponse,
    AuditEventResponse,
    PayPalCaptureResponse,
    PayPalCreateResponse,
    RecipientHistoryResponse,
)
from app.services.ai import extract_payment_intent
from app.services.paypal import (
    PayPalClient,
    PayPalError,
    PayPalResourceNotFound,
)
from app.services.risk_engine import assess_payment
from app.services.paypal_vault import PayPalVaultConfigurationError, decrypt_payment_token
from app.services.spending_limits import (
    ANALYSIS_RESERVATION_MINUTES,
    PAYPAL_RESERVATION_HOURS,
    apply_spending_policy,
    payment_limit_violations,
)

settings = get_settings()

router = APIRouter(prefix="/api/payments", tags=["payments"])


def _audit(
    db: Session,
    payment: PaymentRequest,
    event_type: str,
    message: str,
    actor: str | None = None,
    metadata: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            payment_request_id=payment.id,
            event_type=event_type,
            actor=actor,
            message=message,
            metadata=metadata,
        )
    )


def _block_for_spending_limit(
    db: Session,
    payment: PaymentRequest,
    violations: list[str],
) -> None:
    """Persist a hard policy block and stop the payment before capture."""
    unique_reasons = list(payment.risk.reasons if payment.risk else [])
    for reason in violations:
        if reason not in unique_reasons:
            unique_reasons.append(reason)

    payment.status = "BLOCK"
    payment.limit_reservation_expires_at = None
    if payment.risk:
        payment.risk.decision = "BLOCK"
        payment.risk.risk_score = 100
        payment.risk.reasons = unique_reasons

    _audit(
        db,
        payment,
        "SPENDING_LIMIT_BLOCKED",
        "PathGuard blocked payment because a configured spending limit would be exceeded.",
        metadata={"violations": violations},
    )
    db.commit()
    raise HTTPException(
        status_code=403,
        detail="PathGuard spending limits blocked this payment: " + " ".join(violations),
    )


def _enforce_current_spending_limits(
    db: Session,
    payment: PaymentRequest,
    *,
    reserve_hours: int | None = None,
) -> None:
    violations = payment_limit_violations(db, payment)
    if violations:
        _block_for_spending_limit(db, payment, violations)

    if reserve_hours is not None:
        payment.limit_reservation_expires_at = datetime.now(timezone.utc) + timedelta(
            hours=reserve_hours
        )
        db.commit()


def _has_human_approval(payment: PaymentRequest) -> bool:
    """A REVIEW payment is approved only when its review history says so."""
    if not payment.risk or payment.risk.decision != "REVIEW":
        return True

    approved_at = None
    for event in payment.review_events:
        if event.action == "REJECTED":
            return False
        if event.action == "APPROVED":
            approved_at = event.created_at

    return approved_at is not None


def _paypal_approval_url(data: dict) -> str | None:
    for link in data.get("links", []):
        if link.get("rel") in {"approve", "payer-action"}:
            return link.get("href")
    return None


def _extract_capture_id(data: dict) -> str | None:
    try:
        captures = data["purchase_units"][0]["payments"]["captures"]
        if captures:
            return captures[0].get("id")
    except (KeyError, IndexError, TypeError):
        pass
    return None


def _frontend_redirect(path: str, **params) -> RedirectResponse:
    query = "&".join(
        f"{quote(str(key))}={quote(str(value))}"
        for key, value in params.items()
        if value is not None
    )
    url = f"{settings.paypal_frontend_url.rstrip('/')}/{path.lstrip('/')}"
    if query:
        url = f"{url}?{query}"
    return RedirectResponse(url)


def _ensure_payment_can_use_paypal(payment: PaymentRequest) -> None:
    if not payment.risk:
        raise HTTPException(status_code=400, detail="Payment has not been risk assessed.")

    if payment.risk.decision == "BLOCK":
        raise HTTPException(
            status_code=403,
            detail="PathGuard blocked this payment. No PayPal order was created.",
        )

    if not _has_human_approval(payment):
        raise HTTPException(
            status_code=403,
            detail="This payment requires human approval before PayPal processing.",
        )

    if payment.status == "REVIEW_REJECTED":
        raise HTTPException(
            status_code=403,
            detail="This payment was rejected during human review.",
        )


async def _create_or_replace_paypal_order(
    db: Session,
    payment: PaymentRequest,
    order: PayPalOrder | None = None,
    *,
    use_saved_wallet: bool = True,
) -> PayPalOrder:
    """Create a PayPal order, replacing a stale local order record when needed."""
    vault_id = None
    connection = None
    if use_saved_wallet and payment.user_id:
        connection = (
            db.query(PayPalWalletConnection)
            .filter(
                PayPalWalletConnection.user_id == payment.user_id,
                PayPalWalletConnection.payment_token_ciphertext.is_not(None),
            )
            .first()
        )
    if connection and connection.payment_token_ciphertext:
        try:
            vault_id = decrypt_payment_token(connection.payment_token_ciphertext)
        except PayPalVaultConfigurationError as exc:
            raise PayPalError(str(exc)) from exc

    data = await PayPalClient().create_order(
        amount=payment.amount,
        currency=payment.currency,
        description=payment.purpose or f"Payment to {payment.recipient_name}",
        reference_id=f"pathguard-payment-{payment.id}",
        vault_id=vault_id,
    )

    paypal_order_id = data.get("id")
    approval_url = _paypal_approval_url(data)
    paypal_status = data.get("status", "CREATED")
    if not paypal_order_id or (not approval_url and paypal_status != "COMPLETED"):
        raise PayPalError("PayPal did not return a usable order ID and approval URL.")

    if order is None:
        order = PayPalOrder(payment_request_id=payment.id)
        db.add(order)

    capture_id = _extract_capture_id(data)
    order.paypal_order_id = paypal_order_id
    order.status = paypal_status
    order.approval_url = approval_url
    order.capture_id = capture_id
    order.captured_at = datetime.now(timezone.utc) if paypal_status == "COMPLETED" else None

    if paypal_status == "COMPLETED":
        payment.status = "COMPLETED"
        payment.limit_reservation_expires_at = None
        _audit(
            db,
            payment,
            "PAYMENT_COMPLETED",
            "PayPal completed the payment using the saved wallet after PathGuard approval.",
            metadata={
                "paypal_order_id": paypal_order_id,
                "capture_id": capture_id,
                "saved_wallet": bool(vault_id),
            },
        )
    else:
        payment.status = "PAYPAL_PENDING_APPROVAL"
        payment.limit_reservation_expires_at = datetime.now(timezone.utc) + timedelta(
            hours=PAYPAL_RESERVATION_HOURS
        )
        _audit(
            db,
            payment,
            "PAYPAL_ORDER_CREATED",
            "PayPal order created.",
            metadata={
                "paypal_order_id": paypal_order_id,
                "saved_wallet": bool(vault_id),
            },
        )

    db.commit()
    db.refresh(order)
    return order


async def _refresh_paypal_order(
    db: Session,
    payment: PaymentRequest,
    order: PayPalOrder,
) -> dict:
    """Synchronize one local order with PayPal and capture when approved."""
    client = PayPalClient()

    try:
        order_data = await client.get_order(order.paypal_order_id)
    except PayPalResourceNotFound as exc:
        order.status = "STALE"
        _audit(
            db,
            payment,
            "PAYPAL_ORDER_STALE",
            "PayPal no longer recognizes the stored order. A new checkout is required.",
            metadata={"paypal_order_id": order.paypal_order_id, "debug_id": exc.debug_id},
        )
        db.commit()
        return {
            "payment_id": payment.id,
            "status": "PAYPAL_REAUTH_REQUIRED",
            "paypal_order_id": order.paypal_order_id,
            "approval_url": None,
            "message": "The previous PayPal checkout is no longer valid. A new checkout must be created.",
        }

    paypal_status = order_data.get("status")

    if paypal_status == "COMPLETED":
        capture_id = _extract_capture_id(order_data)
        order.status = "COMPLETED"
        order.capture_id = capture_id
        order.captured_at = order.captured_at or datetime.now(timezone.utc)
        payment.status = "COMPLETED"
        payment.limit_reservation_expires_at = None
        _audit(
            db,
            payment,
            "PAYMENT_COMPLETED",
            "PayPal reported the order as completed; PathGuard synchronized the payment.",
            metadata={"capture_id": capture_id},
        )
        db.commit()
        return {
            "payment_id": payment.id,
            "paypal_order_id": order.paypal_order_id,
            "paypal_status": paypal_status,
            "status": payment.status,
            "capture_id": capture_id,
        }

    order.status = paypal_status or "UNKNOWN"

    if paypal_status in {"CREATED", "PAYER_ACTION_REQUIRED"}:
        payment.status = "PAYPAL_PENDING_APPROVAL"
        db.commit()
        return {
            "payment_id": payment.id,
            "paypal_order_id": order.paypal_order_id,
            "paypal_status": paypal_status,
            "status": payment.status,
            "capture_id": order.capture_id,
            "approval_url": order.approval_url,
        }

    if paypal_status != "APPROVED":
        payment.status = "PAYPAL_PENDING_CAPTURE"
        db.commit()
        return {
            "payment_id": payment.id,
            "paypal_order_id": order.paypal_order_id,
            "paypal_status": paypal_status,
            "status": payment.status,
            "capture_id": order.capture_id,
        }

    # Re-check limits immediately before capture; a checkout can stay open while
    # the user changes policy or other pending payments consume the budget.
    _enforce_current_spending_limits(
        db, payment, reserve_hours=PAYPAL_RESERVATION_HOURS
    )
    capture_data = await client.capture_order(order.paypal_order_id)
    capture_status = capture_data.get("status", "UNKNOWN")
    capture_id = _extract_capture_id(capture_data)

    order.status = capture_status
    order.capture_id = capture_id

    if capture_status == "COMPLETED":
        order.captured_at = datetime.now(timezone.utc)
        payment.status = "COMPLETED"
        payment.limit_reservation_expires_at = None
        _audit(
            db,
            payment,
            "PAYMENT_COMPLETED",
            "PayPal payment captured by PathGuard.",
            metadata={"capture_id": capture_id},
        )
    else:
        payment.status = "PAYPAL_PENDING_CAPTURE"

    db.commit()

    return {
        "payment_id": payment.id,
        "paypal_order_id": order.paypal_order_id,
        "paypal_status": capture_status,
        "status": payment.status,
        "capture_id": capture_id,
    }


@router.post("/analyze", response_model=AnalyzePaymentResponse)
def analyze_payment(
    payload: AnalyzePaymentRequest,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    try:
        intent = extract_payment_intent(payload.instruction)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    risk = assess_payment(db, intent, payload.instruction, user_id=current_user.id)
    risk, limit_violations = apply_spending_policy(
        db, intent, risk, user_id=current_user.id
    )

    recipient_name = intent.recipient_name.strip()
    recipient = (
        db.query(Recipient)
        .filter(Recipient.name.ilike(recipient_name))
        .first()
    )

    if not recipient:
        recipient = Recipient(name=recipient_name)
        db.add(recipient)
        db.flush()

    payment = PaymentRequest(
        user_id=current_user.id,
        raw_instruction=payload.instruction,
        recipient_name=recipient.name,
        recipient_id=recipient.id,
        amount=intent.amount,
        currency=intent.currency.upper(),
        purpose=intent.purpose,
        status="REVIEW_PENDING" if risk.decision == "REVIEW" else risk.decision,
        limit_reservation_expires_at=(
            datetime.now(timezone.utc) + timedelta(minutes=ANALYSIS_RESERVATION_MINUTES)
            if risk.decision != "BLOCK"
            else None
        ),
    )
    db.add(payment)
    db.flush()

    db.add(
        RiskAssessment(
            payment_request_id=payment.id,
            risk_score=risk.risk_score,
            decision=risk.decision,
            amount_anomaly=risk.amount_anomaly,
            new_recipient=risk.new_recipient,
            instruction_mismatch=risk.instruction_mismatch,
            frequency_anomaly=risk.frequency_anomaly,
            reasons=risk.reasons,
        )
    )

    if risk.decision == "REVIEW":
        db.add(
            ReviewEvent(
                payment_request_id=payment.id,
                action="SUBMITTED",
                note="Queued for human review after automated risk assessment.",
            )
        )

    _audit(
        db,
        payment,
        "RISK_ASSESSED",
        f"PathGuard decision: {risk.decision} ({risk.risk_score}/100).",
        metadata={
            "decision": risk.decision,
            "risk_score": risk.risk_score,
            "spending_limit_violations": limit_violations,
        },
    )

    db.commit()
    db.refresh(payment)

    return AnalyzePaymentResponse(payment_id=payment.id, intent=intent, risk=risk)


@router.get("")
def list_payments(
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    payments = (
        db.query(PaymentRequest)
        .filter(PaymentRequest.user_id == current_user.id)
        .order_by(PaymentRequest.created_at.desc())
        .limit(50)
        .all()
    )

    return [
        {
            "id": payment.id,
            "recipient": payment.recipient_name,
            "amount": payment.amount,
            "currency": payment.currency,
            "purpose": payment.purpose,
            "status": payment.status,
            "risk_score": payment.risk.risk_score if payment.risk else None,
            "created_at": payment.created_at,
        }
        for payment in payments
    ]


@router.get("/recipients/{recipient_name}/history", response_model=RecipientHistoryResponse)
def recipient_history(
    recipient_name: str,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    recipient = (
        db.query(Recipient)
        .join(PaymentRequest, PaymentRequest.recipient_id == Recipient.id)
        .filter(
            Recipient.name.ilike(recipient_name),
            PaymentRequest.user_id == current_user.id,
            PaymentRequest.status == "COMPLETED",
        )
        .first()
    )
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")

    payments = (
        db.query(PaymentRequest)
        .filter(
            PaymentRequest.recipient_id == recipient.id,
            PaymentRequest.user_id == current_user.id,
            PaymentRequest.status == "COMPLETED",
        )
        .order_by(PaymentRequest.created_at.desc())
        .all()
    )
    amounts = [float(p.amount) for p in payments]
    return RecipientHistoryResponse(
        recipient=recipient.name,
        total_payments=len(payments),
        total_amount=sum(amounts),
        average_amount=(sum(amounts) / len(amounts)) if amounts else 0.0,
        last_payment_at=payments[0].created_at if payments else recipient.last_payment_at,
    )


@router.get("/paypal/return")
async def paypal_return(token: str | None = None, db: Session = Depends(get_db)):
    if not token:
        return _frontend_redirect("/", paypal="error", message="Missing PayPal order token")

    order = db.query(PayPalOrder).filter(PayPalOrder.paypal_order_id == token).first()
    if not order:
        return _frontend_redirect("/", paypal="error", message="Unknown PayPal order")

    payment = db.get(PaymentRequest, order.payment_request_id)
    if not payment:
        return _frontend_redirect("/", paypal="error", message="Payment not found")

    try:
        _ensure_payment_can_use_paypal(payment)
        result = await _refresh_paypal_order(db, payment, order)

        if result.get("status") == "PAYPAL_REAUTH_REQUIRED":
            replacement = await _create_or_replace_paypal_order(db, payment, order, use_saved_wallet=False)
            return _frontend_redirect(
                "/",
                paypal="reauth",
                payment_id=payment.id,
                order_id=replacement.paypal_order_id,
                approval_url=replacement.approval_url,
            )

        if result.get("status") == "COMPLETED":
            return _frontend_redirect(
                "/",
                paypal="completed",
                payment_id=payment.id,
                order_id=result.get("paypal_order_id"),
                capture_id=result.get("capture_id"),
            )

        if result.get("status") == "PAYPAL_PENDING_APPROVAL":
            return _frontend_redirect(
                "/",
                paypal="pending",
                payment_id=payment.id,
                order_id=result.get("paypal_order_id"),
                message="PayPal checkout has not been approved yet.",
            )

        return _frontend_redirect(
            "/",
            paypal="pending",
            payment_id=payment.id,
            order_id=result.get("paypal_order_id"),
            message="PayPal approved the order, but capture is still pending.",
        )
    except HTTPException as exc:
        return _frontend_redirect(
            "/",
            paypal="blocked",
            payment_id=payment.id,
            message=str(exc.detail),
        )
    except PayPalResourceNotFound:
        # _refresh_paypal_order normally consumes this case. Keep the callback
        # safe if that behavior changes later.
        return _frontend_redirect(
            "/",
            paypal="reauth",
            payment_id=payment.id,
            message="The previous PayPal checkout is no longer valid.",
        )
    except PayPalError as exc:
        payment.status = "PAYPAL_CAPTURE_ERROR"
        _audit(
            db,
            payment,
            "PAYPAL_ERROR",
            str(exc),
            metadata={"status_code": exc.status_code, "debug_id": exc.debug_id},
        )
        db.commit()
        return _frontend_redirect(
            "/",
            paypal="error",
            payment_id=payment.id,
            message=str(exc),
        )


@router.get("/paypal/cancel")
def paypal_cancel(token: str | None = None, db: Session = Depends(get_db)):
    if token:
        order = db.query(PayPalOrder).filter(PayPalOrder.paypal_order_id == token).first()
        if order and order.status != "COMPLETED":
            payment = db.get(PaymentRequest, order.payment_request_id)
            order.status = "CANCELLED"
            if payment and payment.status != "COMPLETED":
                payment.status = "CANCELLED"
                payment.limit_reservation_expires_at = None
                _audit(
                    db,
                    payment,
                    "PAYPAL_CHECKOUT_CANCELLED",
                    "Buyer cancelled PayPal checkout; the spending reservation was released.",
                    metadata={"paypal_order_id": order.paypal_order_id},
                )
            db.commit()
    return _frontend_redirect("/", paypal="cancelled", payment_id=token)


@router.post("/paypal/sync")
async def sync_paypal_order(
    token: str,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    order = db.query(PayPalOrder).filter(PayPalOrder.paypal_order_id == token).first()
    if not order:
        raise HTTPException(status_code=404, detail="Unknown PayPal order")

    payment = db.get(PaymentRequest, order.payment_request_id)
    if not payment or payment.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Payment not found")

    _ensure_payment_can_use_paypal(payment)

    try:
        result = await _refresh_paypal_order(db, payment, order)

        if result.get("status") == "PAYPAL_REAUTH_REQUIRED":
            replacement = await _create_or_replace_paypal_order(db, payment, order, use_saved_wallet=False)
            return {
                **result,
                "paypal_order_id": replacement.paypal_order_id,
                "approval_url": replacement.approval_url,
                "message": "The previous PayPal checkout was stale. A fresh checkout is ready.",
            }

        return result
    except PayPalError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{payment_id}")
def get_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    payment = db.get(PaymentRequest, payment_id)
    if not payment or payment.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Payment request not found")

    history = None
    if payment.recipient:
        completed_payments = (
            db.query(PaymentRequest)
            .filter(
                PaymentRequest.recipient_id == payment.recipient.id,
                PaymentRequest.user_id == current_user.id,
                PaymentRequest.status == "COMPLETED",
            )
            .order_by(PaymentRequest.created_at.desc())
            .all()
        )
        amounts = [float(p.amount) for p in completed_payments]
        history = {
            "recipient": payment.recipient.name,
            "total_payments": len(amounts),
            "total_amount": sum(amounts),
            "average_amount": (sum(amounts) / len(amounts)) if amounts else 0.0,
            "last_payment_at": completed_payments[0].created_at if completed_payments else None,
        }

    return {
        "id": payment.id,
        "instruction": payment.raw_instruction,
        "recipient": payment.recipient_name,
        "amount": payment.amount,
        "currency": payment.currency,
        "purpose": payment.purpose,
        "status": payment.status,
        "risk": (
            {
                "risk_score": payment.risk.risk_score,
                "decision": payment.risk.decision,
                "reasons": payment.risk.reasons,
            }
            if payment.risk
            else None
        ),
        "review_events": [
            {
                "action": event.action,
                "note": event.note,
                "reviewer": event.reviewer,
                "created_at": event.created_at,
            }
            for event in payment.review_events
        ],
        "audit": [
            AuditEventResponse.model_validate(
                {
                    "id": event.id,
                    "event_type": event.event_type,
                    "actor": event.actor,
                    "message": event.message,
                    "metadata": event.metadata,
                    "created_at": event.created_at,
                }
            ).model_dump(mode="json")
            for event in payment.audit_events
        ],
        "recipient_history": history,
        "paypal": (
            {
                "order_id": payment.paypal_order.paypal_order_id,
                "status": payment.paypal_order.status,
                "approval_url": payment.paypal_order.approval_url,
                "capture_id": payment.paypal_order.capture_id,
            }
            if payment.paypal_order
            else None
        ),
    }


@router.get("/{payment_id}/audit", response_model=list[AuditEventResponse])
def payment_audit(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    payment = db.get(PaymentRequest, payment_id)
    if not payment or payment.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Payment request not found")

    return [
        AuditEventResponse(
            id=event.id,
            event_type=event.event_type,
            actor=event.actor,
            message=event.message,
            metadata=event.metadata,
            created_at=event.created_at,
        )
        for event in payment.audit_events
    ]


@router.post("/{payment_id}/paypal/create", response_model=PayPalCreateResponse)
async def create_paypal_order(
    payment_id: int,
    use_saved_wallet: bool = False,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    payment = db.get(PaymentRequest, payment_id)
    if not payment or payment.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Payment request not found")

    _ensure_payment_can_use_paypal(payment)

    if use_saved_wallet:
        connection = (
            db.query(PayPalWalletConnection)
            .filter(
                PayPalWalletConnection.user_id == current_user.id,
                PayPalWalletConnection.payment_token_ciphertext.is_not(None),
            )
            .first()
        )
        if not connection:
            raise HTTPException(
                status_code=409,
                detail="Connect a PayPal wallet in account settings before choosing saved-wallet payment.",
            )

    existing = payment.paypal_order

    if existing and existing.status == "COMPLETED":
        return PayPalCreateResponse(
            payment_id=payment.id,
            paypal_order_id=existing.paypal_order_id,
            status=existing.status,
            approval_url=existing.approval_url,
            capture_id=existing.capture_id,
        )

    _enforce_current_spending_limits(
        db, payment, reserve_hours=PAYPAL_RESERVATION_HOURS
    )

    if existing and existing.status in {"CREATED", "SAVED", "APPROVED"}:
        try:
            current = await PayPalClient().get_order(existing.paypal_order_id)
            current_status = current.get("status")
            existing.status = current_status or existing.status
            existing.approval_url = _paypal_approval_url(current) or existing.approval_url
            db.commit()

            if current_status == "COMPLETED":
                existing.capture_id = _extract_capture_id(current)
                existing.captured_at = existing.captured_at or datetime.now(timezone.utc)
                payment.status = "COMPLETED"
                payment.limit_reservation_expires_at = None
                db.commit()
                return PayPalCreateResponse(
                    payment_id=payment.id,
                    paypal_order_id=existing.paypal_order_id,
                    status=existing.status,
                    approval_url=existing.approval_url,
                    capture_id=existing.capture_id,
                )
            return PayPalCreateResponse(
                payment_id=payment.id,
                paypal_order_id=existing.paypal_order_id,
                status=existing.status,
                approval_url=existing.approval_url,
                capture_id=existing.capture_id,
            )
        except PayPalResourceNotFound:
            existing.status = "STALE"
            _audit(
                db,
                payment,
                "PAYPAL_ORDER_STALE",
                "Stored PayPal order was not found; creating a replacement checkout.",
                metadata={"paypal_order_id": existing.paypal_order_id},
            )
            db.commit()
        except PayPalError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        order = await _create_or_replace_paypal_order(
            db,
            payment,
            existing,
            use_saved_wallet=use_saved_wallet,
        )
    except PayPalError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return PayPalCreateResponse(
        payment_id=payment.id,
        paypal_order_id=order.paypal_order_id,
        status=order.status,
        approval_url=order.approval_url,
        capture_id=order.capture_id,
    )


@router.post("/{payment_id}/paypal/capture", response_model=PayPalCaptureResponse)
async def capture_paypal_order(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    payment = db.get(PaymentRequest, payment_id)
    if not payment or payment.user_id != current_user.id or not payment.paypal_order:
        raise HTTPException(status_code=404, detail="PayPal order not found")

    _ensure_payment_can_use_paypal(payment)

    paypal_order = payment.paypal_order

    if paypal_order.status == "COMPLETED":
        return PayPalCaptureResponse(
            payment_id=payment.id,
            paypal_order_id=paypal_order.paypal_order_id,
            status=paypal_order.status,
            capture_id=paypal_order.capture_id,
        )

    try:
        result = await _refresh_paypal_order(db, payment, paypal_order)
    except PayPalResourceNotFound:
        raise HTTPException(
            status_code=409,
            detail="The PayPal order is no longer valid. Create a new checkout.",
        ) from None
    except PayPalError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if result.get("status") == "PAYPAL_REAUTH_REQUIRED":
        raise HTTPException(
            status_code=409,
            detail="The PayPal order is no longer valid. Create a new checkout.",
        )

    return PayPalCaptureResponse(
        payment_id=payment.id,
        paypal_order_id=result["paypal_order_id"],
        status=result["status"],
        capture_id=result.get("capture_id"),
    )
