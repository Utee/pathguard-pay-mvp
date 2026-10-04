from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_db
from app.models import PaymentRequest, RiskAssessment, PayPalOrder, ReviewEvent
from app.schemas.payment import (
    AnalyzePaymentRequest,
    AnalyzePaymentResponse,
    PayPalCaptureResponse,
    PayPalCreateResponse,
)
from app.services.ai import extract_payment_intent
from app.services.paypal import PayPalClient, PayPalError
from app.services.risk_engine import assess_payment


settings = get_settings()

router = APIRouter(
    prefix="/api/payments",
    tags=["payments"],
)


def _paypal_approval_url(data: dict) -> str | None:
    """
    Extract the PayPal approval URL from the order response.
    """

    for link in data.get("links", []):
        if link.get("rel") in {"approve", "payer-action"}:
            return link.get("href")

    return None


def _extract_capture_id(data: dict) -> str | None:
    """
    Extract the capture ID from a PayPal capture response.
    """

    try:
        captures = data["purchase_units"][0]["payments"]["captures"]

        if captures:
            return captures[0].get("id")

    except (KeyError, IndexError, TypeError):
        pass

    return None


def _frontend_redirect(
    path: str,
    **params,
) -> RedirectResponse:
    """
    Build a safe frontend redirect URL.
    """

    query = "&".join(
        f"{quote(str(key))}={quote(str(value))}"
        for key, value in params.items()
        if value is not None
    )

    url = f"{settings.paypal_frontend_url.rstrip('/')}/{path.lstrip('/')}"

    if query:
        url = f"{url}?{query}"

    return RedirectResponse(url)


@router.post(
    "/analyze",
    response_model=AnalyzePaymentResponse,
)
def analyze_payment(
    payload: AnalyzePaymentRequest,
    db: Session = Depends(get_db),
):
    """
    Analyze a payment instruction with PathGuard's AI
    and risk engine.
    """

    try:
        intent = extract_payment_intent(payload.instruction)

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    risk = assess_payment(
        db,
        intent,
        payload.instruction,
    )

    payment = PaymentRequest(
        raw_instruction=payload.instruction,
        recipient_name=intent.recipient_name,
        amount=intent.amount,
        currency=intent.currency.upper(),
        purpose=intent.purpose,
        status=("REVIEW_PENDING" if risk.decision == "REVIEW" else risk.decision),
    )

    db.add(payment)
    db.flush()

    assessment = RiskAssessment(
        payment_request_id=payment.id,
        risk_score=risk.risk_score,
        decision=risk.decision,
        amount_anomaly=risk.amount_anomaly,
        new_recipient=risk.new_recipient,
        instruction_mismatch=risk.instruction_mismatch,
        frequency_anomaly=risk.frequency_anomaly,
        reasons=risk.reasons,
    )

    db.add(assessment)
    if risk.decision == "REVIEW":
        db.add(ReviewEvent(
            payment_request_id=payment.id,
            action="SUBMITTED",
            note="Queued for human review after automated risk assessment.",
        ))
    db.commit()
    db.refresh(payment)

    return AnalyzePaymentResponse(
        payment_id=payment.id,
        intent=intent,
        risk=risk,
    )


@router.get("")
def list_payments(
    db: Session = Depends(get_db),
):
    """
    List recent PathGuard payment requests.
    """

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
            "risk_score": (
                payment.risk.risk_score
                if payment.risk
                else None
            ),
            "created_at": payment.created_at,
        }
        for payment in payments
    ]


@router.get("/{payment_id}")
def get_payment(
    payment_id: int,
    db: Session = Depends(get_db),
):
    """
    Get a payment request and its PathGuard/PayPal status.
    """

    payment = db.get(
        PaymentRequest,
        payment_id,
    )

    if not payment:
        raise HTTPException(
            status_code=404,
            detail="Payment request not found",
        )

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
                "score": payment.risk.risk_score,
                "decision": payment.risk.decision,
                "reasons": payment.risk.reasons,
            }
            if payment.risk
            else None
        ),
        "paypal": (
            {
                "order_id": (
                    payment.paypal_order.paypal_order_id
                ),
                "status": payment.paypal_order.status,
                "approval_url": (
                    payment.paypal_order.approval_url
                ),
                "capture_id": (
                    payment.paypal_order.capture_id
                ),
            }
            if payment.paypal_order
            else None
        ),
    }


@router.post(
    "/{payment_id}/paypal/create",
    response_model=PayPalCreateResponse,
)
async def create_paypal_order(
    payment_id: int,
    db: Session = Depends(get_db),
):
    """
    Create a PayPal order after PathGuard has
    analyzed and approved the payment.
    """

    payment = db.get(
        PaymentRequest,
        payment_id,
    )

    if not payment:
        raise HTTPException(
            status_code=404,
            detail="Payment request not found",
        )

    if not payment.risk:
        raise HTTPException(
            status_code=400,
            detail="Payment has not been risk assessed",
        )

    if payment.risk.decision == "BLOCK":
        raise HTTPException(
            status_code=403,
            detail=(
                "PathGuard blocked this payment. "
                "No PayPal order was created."
            ),
        )

    if (
        payment.risk.decision == "REVIEW"
        and payment.status != "REVIEW_APPROVED"
    ):
        raise HTTPException(
            status_code=403,
            detail="This payment requires human approval before PayPal checkout.",
        )

    # Don't create duplicate PayPal orders.
    if payment.paypal_order:
        existing_order = payment.paypal_order

        if existing_order.status in {
            "CREATED",
            "SAVED",
            "APPROVED",
        }:
            return PayPalCreateResponse(
                payment_id=payment.id,
                paypal_order_id=(
                    existing_order.paypal_order_id
                ),
                status=existing_order.status,
                approval_url=(
                    existing_order.approval_url
                ),
            )

    try:
        client = PayPalClient()

        data = await client.create_order(
            amount=payment.amount,
            currency=payment.currency,
            description=(
                payment.purpose
                or f"Payment to {payment.recipient_name}"
            ),
        )

    except PayPalError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    paypal_order_id = data.get("id")

    if not paypal_order_id:
        raise HTTPException(
            status_code=502,
            detail="PayPal did not return an order ID.",
        )

    approval_url = _paypal_approval_url(data)

    if not approval_url:
        raise HTTPException(
            status_code=502,
            detail=(
                "PayPal created the order but did not "
                "return an approval URL."
            ),
        )

    order = PayPalOrder(
        payment_request_id=payment.id,
        paypal_order_id=paypal_order_id,
        status=data.get(
            "status",
            "CREATED",
        ),
        approval_url=approval_url,
    )

    db.add(order)

    payment.status = "PAYPAL_PENDING_APPROVAL"

    db.commit()
    db.refresh(order)

    return PayPalCreateResponse(
        payment_id=payment.id,
        paypal_order_id=order.paypal_order_id,
        status=order.status,
        approval_url=order.approval_url,
    )


@router.post(
    "/{payment_id}/paypal/capture",
    response_model=PayPalCaptureResponse,
)
async def capture_paypal_order(
    payment_id: int,
    db: Session = Depends(get_db),
):
    """
    Capture an approved PayPal order.

    PathGuard verifies the order before marking
    the payment as completed.
    """

    payment = db.get(
        PaymentRequest,
        payment_id,
    )

    if not payment or not payment.paypal_order:
        raise HTTPException(
            status_code=404,
            detail="PayPal order not found",
        )

    if payment.risk and payment.risk.decision == "BLOCK":
        raise HTTPException(
            status_code=403,
            detail="PathGuard blocked this payment.",
        )

    if (
        payment.risk
        and payment.risk.decision == "REVIEW"
        and payment.status != "REVIEW_APPROVED"
    ):
        raise HTTPException(
            status_code=403,
            detail="This payment requires human approval before PayPal processing.",
        )

    paypal_order = payment.paypal_order

    # Idempotency protection.
    if paypal_order.status == "COMPLETED":
        return PayPalCaptureResponse(
            payment_id=payment.id,
            paypal_order_id=(
                paypal_order.paypal_order_id
            ),
            status=paypal_order.status,
            capture_id=paypal_order.capture_id,
        )

    try:
        client = PayPalClient()

        # Verify the order with PayPal first.
        order_data = await client.get_order(
            paypal_order.paypal_order_id
        )

        paypal_status = order_data.get("status")

        if paypal_status != "APPROVED":
            raise HTTPException(
                status_code=400,
                detail=(
                    "PayPal order is not approved. "
                    f"Current status: {paypal_status}"
                ),
            )

        # Capture only after PayPal confirms approval.
        data = await client.capture_order(
            paypal_order.paypal_order_id
        )

    except PayPalError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    capture_id = _extract_capture_id(data)

    paypal_order.status = data.get(
        "status",
        "UNKNOWN",
    )

    paypal_order.capture_id = capture_id

    if paypal_order.status == "COMPLETED":
        paypal_order.captured_at = datetime.now(
            timezone.utc
        )

        payment.status = "COMPLETED"

    else:
        payment.status = "PAYPAL_PENDING_CAPTURE"

    db.commit()

    return PayPalCaptureResponse(
        payment_id=payment.id,
        paypal_order_id=(
            paypal_order.paypal_order_id
        ),
        status=paypal_order.status,
        capture_id=capture_id,
    )


@router.get("/paypal/return")
async def paypal_return(
    token: str | None = None,
    db: Session = Depends(get_db),
):
    """
    PayPal redirects the customer here after approval.

    PathGuard verifies the order and automatically captures
    the approved PayPal order before redirecting the user
    back to the frontend.
    """

    if not token:
        return _frontend_redirect(
            "/",
            paypal="error",
            message="Missing PayPal order token",
        )

    order = (
        db.query(PayPalOrder)
        .filter(
            PayPalOrder.paypal_order_id == token
        )
        .first()
    )

    if not order:
        return _frontend_redirect(
            "/",
            paypal="error",
            message="Unknown PayPal order",
        )

    payment = db.get(
        PaymentRequest,
        order.payment_request_id,
    )

    if not payment:
        return _frontend_redirect(
            "/",
            paypal="error",
            message="Payment not found",
        )

    # A REVIEW decision must be explicitly approved before checkout capture.
    if (
        payment.risk
        and payment.risk.decision == "REVIEW"
        and payment.status != "REVIEW_APPROVED"
    ):
        return _frontend_redirect(
            "/",
            paypal="blocked",
            payment_id=payment.id,
            message="This payment requires human approval before capture.",
        )

    # Never capture a payment that PathGuard blocked.
    if (
        not payment.risk
        or payment.risk.decision == "BLOCK"
    ):
        return _frontend_redirect(
            "/",
            paypal="blocked",
            payment_id=payment.id,
        )

    try:
        client = PayPalClient()

        # Verify the current PayPal order status first.
        order_data = await client.get_order(
            order.paypal_order_id
        )

        paypal_status = order_data.get("status")

        # If PayPal already completed the order,
        # don't attempt another capture.
        if paypal_status == "COMPLETED":
            capture_id = _extract_capture_id(order_data)

            order.status = "COMPLETED"
            order.capture_id = capture_id

            if not order.captured_at:
                order.captured_at = datetime.now(
                    timezone.utc
                )

            payment.status = "COMPLETED"

            db.commit()

            return _frontend_redirect(
                "/",
                paypal="completed",
                payment_id=payment.id,
                order_id=order.paypal_order_id,
                capture_id=capture_id,
            )

        # We expect PayPal to report APPROVED after
        # the buyer has approved the checkout.
        if paypal_status != "APPROVED":
            order.status = paypal_status or "UNKNOWN"
            payment.status = "PAYPAL_PENDING_CAPTURE"

            db.commit()

            return _frontend_redirect(
                "/",
                paypal="error",
                payment_id=payment.id,
                order_id=order.paypal_order_id,
                message=(
                    "PayPal order was not approved. "
                    f"Current status: {paypal_status}"
                ),
            )

        # Capture the approved order.
        capture_data = await client.capture_order(
            order.paypal_order_id
        )

        capture_id = _extract_capture_id(
            capture_data
        )

        capture_status = capture_data.get(
            "status",
            "UNKNOWN",
        )

        order.status = capture_status
        order.capture_id = capture_id

        if capture_status == "COMPLETED":
            order.captured_at = datetime.now(
                timezone.utc
            )

            payment.status = "COMPLETED"
        else:
            payment.status = "PAYPAL_PENDING_CAPTURE"

        db.commit()

        if capture_status == "COMPLETED":
            return _frontend_redirect(
                "/",
                paypal="completed",
                payment_id=payment.id,
                order_id=order.paypal_order_id,
                capture_id=capture_id,
            )

        return _frontend_redirect(
            "/",
            paypal="pending",
            payment_id=payment.id,
            order_id=order.paypal_order_id,
            message=(
                "PayPal approved the payment, "
                "but capture is still pending."
            ),
        )

    except PayPalError as exc:
        # Keep the local order state useful for debugging.
        order.status = "CAPTURE_ERROR"
        payment.status = "PAYPAL_CAPTURE_ERROR"
        db.commit()

        return _frontend_redirect(
            "/",
            paypal="error",
            payment_id=payment.id,
            order_id=order.paypal_order_id,
            message=str(exc),
        )

@router.get("/paypal/cancel")
def paypal_cancel(
    token: str | None = None,
):
    """
    Handle a customer cancelling the PayPal checkout.
    """

    return _frontend_redirect(
        "/",
        paypal="cancelled",
        payment_id=token,
    )