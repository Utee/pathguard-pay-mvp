from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_roles, verify_password
from app.db import get_db
from app.models import AuditEvent, PaymentRequest, ReviewEvent, UserAccount
from app.services.spending_limits import ANALYSIS_RESERVATION_MINUTES, payment_limit_violations

router = APIRouter(prefix="/api/reviews", tags=["human-review"])


class ReviewDecision(BaseModel):
    note: str | None = Field(default=None, max_length=1000)
    reviewer: str = Field(default="local-reviewer", min_length=1, max_length=120)


class SelfReviewConfirmation(BaseModel):
    password: str = Field(min_length=1, max_length=256)


def _payment_payload(payment: PaymentRequest) -> dict:
    return {
        "id": payment.id,
        "recipient": payment.recipient_name,
        "amount": payment.amount,
        "currency": payment.currency,
        "purpose": payment.purpose,
        "instruction": payment.raw_instruction,
        "status": payment.status,
        "risk": {
            "score": payment.risk.risk_score,
            "decision": payment.risk.decision,
            "reasons": payment.risk.reasons,
        } if payment.risk else None,
        "created_at": payment.created_at,
    }


@router.get("/mine")
def my_payment_reviews(
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    items = (
        db.query(PaymentRequest)
        .filter(
            PaymentRequest.user_id == current_user.id,
            PaymentRequest.status.in_(["REVIEW_PENDING", "REVIEW_APPROVED", "REVIEW_REJECTED", "BLOCK"]),
            PaymentRequest.risk.has(decision="REVIEW"),
        )
        .order_by(PaymentRequest.created_at.desc())
        .limit(100)
        .all()
    )
    return [_payment_payload(item) for item in items]


@router.post("/{payment_id}/confirm")
def confirm_own_review(
    payment_id: int,
    payload: SelfReviewConfirmation,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if not verify_password(payload.password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Password is incorrect.")

    payment = db.get(PaymentRequest, payment_id)
    if not payment or payment.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Payment request not found")
    if not payment.risk or payment.risk.decision != "REVIEW":
        raise HTTPException(status_code=409, detail="Only REVIEW payments can be confirmed.")
    if payment.status != "REVIEW_PENDING":
        raise HTTPException(status_code=409, detail="This payment is no longer awaiting your decision.")
    if payment.paypal_order:
        raise HTTPException(status_code=409, detail="This payment has already entered PayPal processing.")

    violations = payment_limit_violations(db, payment)
    if violations:
        payment.status = "BLOCK"
        payment.limit_reservation_expires_at = None
        payment.risk.decision = "BLOCK"
        payment.risk.risk_score = 100
        payment.risk.reasons = list(dict.fromkeys([*(payment.risk.reasons or []), *violations]))
        db.add(AuditEvent(
            payment_request_id=payment.id,
            event_type="SPENDING_LIMIT_BLOCKED",
            actor=current_user.email,
            message="User confirmation denied because a configured spending limit would be exceeded.",
            metadata={"violations": violations},
        ))
        db.commit()
        raise HTTPException(
            status_code=403,
            detail="Spending limits blocked this payment: " + " ".join(violations),
        )

    payment.status = "REVIEW_APPROVED"
    payment.limit_reservation_expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=ANALYSIS_RESERVATION_MINUTES
    )
    db.add(ReviewEvent(
        payment_request_id=payment.id,
        action="USER_CONFIRMED",
        note="User confirmed the payment after reviewing the risk warning and re-entering their password.",
        reviewer=current_user.email,
    ))
    db.add(AuditEvent(
        payment_request_id=payment.id,
        event_type="USER_CONFIRMED_REVIEW",
        actor=current_user.email,
        message="User explicitly confirmed a payment flagged for review after password verification.",
        metadata={"risk_decision": "REVIEW", "confirmation_method": "password_reentry"},
    ))
    db.commit()
    db.refresh(payment)
    return _payment_payload(payment)


@router.post("/{payment_id}/reject-own")
def reject_own_review(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    payment = db.get(PaymentRequest, payment_id)
    if not payment or payment.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Payment request not found")
    if not payment.risk or payment.risk.decision != "REVIEW":
        raise HTTPException(status_code=409, detail="Only REVIEW payments can be rejected.")
    if payment.status != "REVIEW_PENDING" or payment.paypal_order:
        raise HTTPException(status_code=409, detail="This payment is no longer awaiting your decision.")

    payment.status = "REVIEW_REJECTED"
    payment.limit_reservation_expires_at = None
    db.add(ReviewEvent(
        payment_request_id=payment.id,
        action="USER_REJECTED",
        note="User rejected the payment after reviewing the risk warning.",
        reviewer=current_user.email,
    ))
    db.add(AuditEvent(
        payment_request_id=payment.id,
        event_type="USER_REJECTED_REVIEW",
        actor=current_user.email,
        message="User rejected a payment flagged for review.",
    ))
    db.commit()
    db.refresh(payment)
    return _payment_payload(payment)


@router.get("")
def review_queue(
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(require_roles("reviewer", "admin")),
):
    items = (
        db.query(PaymentRequest)
        .filter(PaymentRequest.status == "REVIEW_PENDING")
        .order_by(PaymentRequest.created_at.asc())
        .limit(100)
        .all()
    )
    return [_payment_payload(item) for item in items]


@router.post("/{payment_id}/approve")
def approve_review(
    payment_id: int,
    payload: ReviewDecision,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(require_roles("reviewer", "admin")),
):
    payment = db.get(PaymentRequest, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment request not found")
    if payment.user_id == current_user.id:
        raise HTTPException(status_code=403, detail="A staff member cannot review their own payment.")
    if not payment.risk or payment.risk.decision != "REVIEW":
        raise HTTPException(status_code=409, detail="Only REVIEW payments can be approved")
    if payment.status == "REVIEW_REJECTED":
        raise HTTPException(status_code=409, detail="This payment was already rejected")
    if payment.status == "REVIEW_APPROVED":
        raise HTTPException(status_code=409, detail="This payment was already approved")
    if payment.status == "COMPLETED" or payment.paypal_order:
        raise HTTPException(status_code=409, detail="Payment has already entered PayPal processing")

    violations = payment_limit_violations(db, payment)
    if violations:
        payment.status = "BLOCK"
        payment.limit_reservation_expires_at = None
        payment.risk.decision = "BLOCK"
        payment.risk.risk_score = 100
        payment.risk.reasons = list(dict.fromkeys([*(payment.risk.reasons or []), *violations]))
        db.add(AuditEvent(
            payment_request_id=payment.id,
            event_type="SPENDING_LIMIT_BLOCKED",
            actor=current_user.email,
            message="Payment approval denied because a configured spending limit would be exceeded.",
            metadata={"violations": violations},
        ))
        db.commit()
        raise HTTPException(
            status_code=403,
            detail="Spending limits blocked this payment: " + " ".join(violations),
        )

    payment.status = "REVIEW_APPROVED"
    payment.limit_reservation_expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=ANALYSIS_RESERVATION_MINUTES
    )
    db.add(ReviewEvent(
        payment_request_id=payment.id,
        action="APPROVED",
        note=payload.note,
        reviewer=current_user.email,
    ))
    db.commit()
    db.refresh(payment)
    return _payment_payload(payment)


@router.post("/{payment_id}/reject")
def reject_review(
    payment_id: int,
    payload: ReviewDecision,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(require_roles("reviewer", "admin")),
):
    payment = db.get(PaymentRequest, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment request not found")
    if payment.user_id == current_user.id:
        raise HTTPException(status_code=403, detail="A staff member cannot review their own payment.")
    if not payment.risk or payment.risk.decision != "REVIEW":
        raise HTTPException(status_code=409, detail="Only REVIEW payments can be rejected")
    if payment.status == "REVIEW_APPROVED":
        raise HTTPException(status_code=409, detail="This payment was already approved")
    if payment.status == "REVIEW_REJECTED":
        raise HTTPException(status_code=409, detail="This payment was already rejected")
    if payment.status == "COMPLETED" or payment.paypal_order:
        raise HTTPException(status_code=409, detail="Payment has already entered PayPal processing")

    payment.status = "REVIEW_REJECTED"
    payment.limit_reservation_expires_at = None
    db.add(ReviewEvent(
        payment_request_id=payment.id,
        action="REJECTED",
        note=payload.note,
        reviewer=current_user.email,
    ))
    db.commit()
    db.refresh(payment)
    return _payment_payload(payment)


@router.get("/{payment_id}/events")
def review_events(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    payment = db.get(PaymentRequest, payment_id)
    if not payment or (
        payment.user_id != current_user.id
        and current_user.role not in {"reviewer", "admin"}
    ):
        raise HTTPException(status_code=404, detail="Payment request not found")
    events = (
        db.query(ReviewEvent)
        .filter(ReviewEvent.payment_request_id == payment_id)
        .order_by(ReviewEvent.created_at.asc())
        .all()
    )
    return [
        {
            "id": event.id,
            "action": event.action,
            "note": event.note,
            "reviewer": event.reviewer,
            "created_at": event.created_at,
        }
        for event in events
    ]
