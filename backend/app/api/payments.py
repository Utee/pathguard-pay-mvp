from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_db
from app.models import AuditEvent, PayPalOrder, PaymentRequest, Recipient, RiskAssessment, ReviewEvent
from app.schemas.payment import (
    AnalyzePaymentRequest,
    AnalyzePaymentResponse,
    AuditEventResponse,
    PayPalCaptureResponse,
    PayPalCreateResponse,
    RecipientHistoryResponse,
)
from app.services.ai import extract_payment_intent
from app.services.paypal import PayPalClient, PayPalError
from app.services.risk_engine import assess_payment

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


def _has_human_approval(payment: PaymentRequest) -> bool:
    """Return whether a REVIEW payment has an explicit human approval event."""
    if not payment.risk or payment.risk.decision != "REVIEW":
        return True

    return any(
        event.action == "APPROVED"
        for event in payment.review_events
    )


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


@router.post("/analyze", response_model=AnalyzePaymentResponse)
def analyze_payment(payload: AnalyzePaymentRequest, db: Session = Depends(get_db)):
    try:
        intent = extract_payment_intent(payload.instruction)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    risk = assess_payment(db, intent, payload.instruction)

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
        raw_instruction=payload.instruction,
        recipient_name=recipient.name,
        recipient_id=recipient.id,
        amount=intent.amount,
        currency=intent.currency.upper(),
        purpose=intent.purpose,
        status="REVIEW_PENDING" if risk.decision == "REVIEW" else risk.decision,
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
        metadata={"decision": risk.decision, "risk_score": risk.risk_score},
    )

    db.commit()
    db.refresh(payment)

    return AnalyzePaymentResponse(payment_id=payment.id, intent=intent, risk=risk)


@router.get("")
def list_payments(db: Session = Depends(get_db)):
    payments = (
        db.query(PaymentRequest)
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
def recipient_history(recipient_name: str, db: Session = Depends(get_db)):
    recipient = (
        db.query(Recipient)
        .filter(Recipient.name.ilike(recipient_name))
        .first()
    )
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")

    payments = (
        db.query(PaymentRequest)
        .filter(PaymentRequest.recipient_id == recipient.id)
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

    if not _has_human_approval(payment):
        return _frontend_redirect(
            "/", paypal="blocked", payment_id=payment.id,
            message="This payment requires human approval before capture.",
        )

    if not payment.risk or payment.risk.decision == "BLOCK":
        return _frontend_redirect("/", paypal="blocked", payment_id=payment.id)

    try:
        client = PayPalClient()
        order_data = await client.get_order(order.paypal_order_id)
        paypal_status = order_data.get("status")

        if paypal_status == "COMPLETED":
            capture_id = _extract_capture_id(order_data)
            order.status = "COMPLETED"
            order.capture_id = capture_id
            order.captured_at = order.captured_at or datetime.now(timezone.utc)
            payment.status = "COMPLETED"
            _audit(db, payment, "PAYMENT_COMPLETED", "PayPal reported the order as completed.", metadata={"capture_id": capture_id})
            db.commit()
            return _frontend_redirect("/", paypal="completed", payment_id=payment.id, order_id=order.paypal_order_id, capture_id=capture_id)

        if paypal_status != "APPROVED":
            order.status = paypal_status or "UNKNOWN"
            payment.status = "PAYPAL_PENDING_CAPTURE"
            db.commit()
            return _frontend_redirect(
                "/", paypal="error", payment_id=payment.id, order_id=order.paypal_order_id,
                message=f"PayPal order was not approved. Current status: {paypal_status}",
            )

        capture_data = await client.capture_order(order.paypal_order_id)
        capture_id = _extract_capture_id(capture_data)
        capture_status = capture_data.get("status", "UNKNOWN")
        order.status = capture_status
        order.capture_id = capture_id

        if capture_status == "COMPLETED":
            order.captured_at = datetime.now(timezone.utc)
            payment.status = "COMPLETED"
            _audit(db, payment, "PAYMENT_COMPLETED", "PayPal payment captured after return.", metadata={"capture_id": capture_id})
        else:
            payment.status = "PAYPAL_PENDING_CAPTURE"

        db.commit()

        if capture_status == "COMPLETED":
            return _frontend_redirect("/", paypal="completed", payment_id=payment.id, order_id=order.paypal_order_id, capture_id=capture_id)

        return _frontend_redirect(
            "/", paypal="pending", payment_id=payment.id, order_id=order.paypal_order_id,
            message="PayPal approved the payment, but capture is still pending.",
        )
    except PayPalError as exc:
        order.status = "CAPTURE_ERROR"
        payment.status = "PAYPAL_CAPTURE_ERROR"
        _audit(db, payment, "PAYPAL_CAPTURE_ERROR", str(exc))
        db.commit()
        return _frontend_redirect(
            "/", paypal="error", payment_id=payment.id, order_id=order.paypal_order_id, message=str(exc),
        )


@router.get("/paypal/cancel")
def paypal_cancel(token: str | None = None):
    return _frontend_redirect("/", paypal="cancelled", payment_id=token)


@router.post("/paypal/sync")
async def sync_paypal_order(token: str, db: Session = Depends(get_db)):
    """
    Recover and finalize a PayPal checkout after the buyer returns.

    The endpoint is intentionally idempotent: if PayPal already completed
    the order, PathGuard simply synchronizes its local state.
    """
    order = db.query(PayPalOrder).filter(PayPalOrder.paypal_order_id == token).first()
    if not order:
        raise HTTPException(status_code=404, detail="Unknown PayPal order")

    payment = db.get(PaymentRequest, order.payment_request_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment.risk and payment.risk.decision == "BLOCK":
        raise HTTPException(status_code=403, detail="PathGuard blocked this payment.")

    if not _has_human_approval(payment):
        raise HTTPException(
            status_code=403,
            detail="This payment requires human approval before PayPal processing.",
        )

    try:
        client = PayPalClient()
        order_data = await client.get_order(order.paypal_order_id)
        paypal_status = order_data.get("status")

        if paypal_status == "COMPLETED":
            capture_id = _extract_capture_id(order_data)
            order.status = "COMPLETED"
            order.capture_id = capture_id
            order.captured_at = order.captured_at or datetime.now(timezone.utc)
            payment.status = "COMPLETED"
            _audit(
                db,
                payment,
                "PAYMENT_COMPLETED",
                "PayPal order was already completed; PathGuard synchronized the payment.",
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

        if paypal_status != "APPROVED":
            order.status = paypal_status or "UNKNOWN"
            payment.status = "PAYPAL_PENDING_APPROVAL" if paypal_status in {"CREATED", "PAYER_ACTION_REQUIRED"} else "PAYPAL_PENDING_CAPTURE"
            db.commit()
            return {
                "payment_id": payment.id,
                "paypal_order_id": order.paypal_order_id,
                "paypal_status": paypal_status,
                "status": payment.status,
                "capture_id": order.capture_id,
            }

        capture_data = await client.capture_order(order.paypal_order_id)
        capture_status = capture_data.get("status", "UNKNOWN")
        capture_id = _extract_capture_id(capture_data)

        order.status = capture_status
        order.capture_id = capture_id

        if capture_status == "COMPLETED":
            order.captured_at = datetime.now(timezone.utc)
            payment.status = "COMPLETED"
            _audit(
                db,
                payment,
                "PAYMENT_COMPLETED",
                "PayPal payment captured during synchronization.",
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
    except PayPalError as exc:
        order.status = "CAPTURE_ERROR"
        payment.status = "PAYPAL_CAPTURE_ERROR"
        _audit(db, payment, "PAYPAL_CAPTURE_ERROR", str(exc))
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{payment_id}")
def get_payment(payment_id: int, db: Session = Depends(get_db)):
    payment = db.get(PaymentRequest, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment request not found")

    history = None
    if payment.recipient:
        amounts = [float(p.amount) for p in payment.recipient.payments]
        history = {
            "recipient": payment.recipient.name,
            "total_payments": len(amounts),
            "total_amount": sum(amounts),
            "average_amount": (sum(amounts) / len(amounts)) if amounts else 0.0,
            "last_payment_at": max(
                (p.created_at for p in payment.recipient.payments),
                default=None,
            ),
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
def payment_audit(payment_id: int, db: Session = Depends(get_db)):
    payment = db.get(PaymentRequest, payment_id)
    if not payment:
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
async def create_paypal_order(payment_id: int, db: Session = Depends(get_db)):
    payment = db.get(PaymentRequest, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment request not found")
    if not payment.risk:
        raise HTTPException(status_code=400, detail="Payment has not been risk assessed")

    if payment.risk.decision == "BLOCK":
        raise HTTPException(status_code=403, detail="PathGuard blocked this payment. No PayPal order was created.")

    if not _has_human_approval(payment):
        raise HTTPException(
            status_code=403,
            detail="This payment requires human approval before PayPal checkout.",
        )

    if payment.status == "REVIEW_REJECTED":
        raise HTTPException(status_code=403, detail="This payment was rejected during human review.")

    if payment.paypal_order and payment.paypal_order.status in {"CREATED", "SAVED", "APPROVED"}:
        return PayPalCreateResponse(
            payment_id=payment.id,
            paypal_order_id=payment.paypal_order.paypal_order_id,
            status=payment.paypal_order.status,
            approval_url=payment.paypal_order.approval_url,
        )

    try:
        data = await PayPalClient().create_order(
            amount=payment.amount,
            currency=payment.currency,
            description=payment.purpose or f"Payment to {payment.recipient_name}",
        )
    except PayPalError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    paypal_order_id = data.get("id")
    approval_url = _paypal_approval_url(data)
    if not paypal_order_id or not approval_url:
        raise HTTPException(status_code=502, detail="PayPal did not return a usable approval URL.")

    order = PayPalOrder(
        payment_request_id=payment.id,
        paypal_order_id=paypal_order_id,
        status=data.get("status", "CREATED"),
        approval_url=approval_url,
    )
    db.add(order)

    payment.status = "PAYPAL_PENDING_APPROVAL"
    _audit(db, payment, "PAYPAL_ORDER_CREATED", "PayPal order created.", metadata={"paypal_order_id": paypal_order_id})
    db.commit()
    db.refresh(order)

    return PayPalCreateResponse(
        payment_id=payment.id,
        paypal_order_id=order.paypal_order_id,
        status=order.status,
        approval_url=order.approval_url,
    )


@router.post("/{payment_id}/paypal/capture", response_model=PayPalCaptureResponse)
async def capture_paypal_order(payment_id: int, db: Session = Depends(get_db)):
    payment = db.get(PaymentRequest, payment_id)
    if not payment or not payment.paypal_order:
        raise HTTPException(status_code=404, detail="PayPal order not found")

    if payment.risk and payment.risk.decision == "BLOCK":
        raise HTTPException(status_code=403, detail="PathGuard blocked this payment.")

    if not _has_human_approval(payment):
        raise HTTPException(status_code=403, detail="This payment requires human approval before PayPal processing.")

    paypal_order = payment.paypal_order

    if paypal_order.status == "COMPLETED":
        return PayPalCaptureResponse(
            payment_id=payment.id,
            paypal_order_id=paypal_order.paypal_order_id,
            status=paypal_order.status,
            capture_id=paypal_order.capture_id,
        )

    try:
        client = PayPalClient()
        order_data = await client.get_order(paypal_order.paypal_order_id)
        paypal_status = order_data.get("status")

        if paypal_status != "APPROVED":
            raise HTTPException(
                status_code=400,
                detail=f"PayPal order is not approved. Current status: {paypal_status}",
            )

        data = await client.capture_order(paypal_order.paypal_order_id)
    except PayPalError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    capture_id = _extract_capture_id(data)
    paypal_order.status = data.get("status", "UNKNOWN")
    paypal_order.capture_id = capture_id

    if paypal_order.status == "COMPLETED":
        paypal_order.captured_at = datetime.now(timezone.utc)
        payment.status = "COMPLETED"
        _audit(db, payment, "PAYMENT_COMPLETED", "PayPal payment captured.", metadata={"capture_id": capture_id})
    else:
        payment.status = "PAYPAL_PENDING_CAPTURE"

    db.commit()

    return PayPalCaptureResponse(
        payment_id=payment.id,
        paypal_order_id=paypal_order.paypal_order_id,
        status=paypal_order.status,
        capture_id=capture_id,
    )

