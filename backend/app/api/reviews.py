from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import PaymentRequest, ReviewEvent

router = APIRouter(prefix="/api/reviews", tags=["human-review"])


class ReviewDecision(BaseModel):
    note: str | None = Field(default=None, max_length=1000)
    reviewer: str = Field(default="local-reviewer", min_length=1, max_length=120)


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


@router.get("")
def review_queue(db: Session = Depends(get_db)):
    """List payments awaiting a human decision."""
    items = (
        db.query(PaymentRequest)
        .filter(PaymentRequest.status.in_(("REVIEW", "REVIEW_PENDING")))
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
):
    payment = db.get(PaymentRequest, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment request not found")
    if not payment.risk or payment.risk.decision != "REVIEW":
        raise HTTPException(status_code=409, detail="Only REVIEW payments can be approved")
    if payment.status == "REVIEW_REJECTED":
        raise HTTPException(status_code=409, detail="This payment was already rejected")
    if payment.status == "REVIEW_APPROVED":
        raise HTTPException(status_code=409, detail="This payment was already approved")
    if payment.status == "COMPLETED" or payment.paypal_order:
        raise HTTPException(status_code=409, detail="Payment has already entered PayPal processing")

    payment.status = "REVIEW_APPROVED"
    db.add(ReviewEvent(
        payment_request_id=payment.id,
        action="APPROVED",
        note=payload.note,
        reviewer=payload.reviewer.strip(),
    ))
    db.commit()
    db.refresh(payment)
    return _payment_payload(payment)


@router.post("/{payment_id}/reject")
def reject_review(
    payment_id: int,
    payload: ReviewDecision,
    db: Session = Depends(get_db),
):
    payment = db.get(PaymentRequest, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment request not found")
    if not payment.risk or payment.risk.decision != "REVIEW":
        raise HTTPException(status_code=409, detail="Only REVIEW payments can be rejected")
    if payment.status == "REVIEW_APPROVED":
        raise HTTPException(status_code=409, detail="This payment was already approved")
    if payment.status == "REVIEW_REJECTED":
        raise HTTPException(status_code=409, detail="This payment was already rejected")
    if payment.status == "COMPLETED" or payment.paypal_order:
        raise HTTPException(status_code=409, detail="Payment has already entered PayPal processing")

    payment.status = "REVIEW_REJECTED"
    db.add(ReviewEvent(
        payment_request_id=payment.id,
        action="REJECTED",
        note=payload.note,
        reviewer=payload.reviewer.strip(),
    ))
    db.commit()
    db.refresh(payment)
    return _payment_payload(payment)


@router.get("/{payment_id}/events")
def review_events(payment_id: int, db: Session = Depends(get_db)):
    if not db.get(PaymentRequest, payment_id):
        raise HTTPException(status_code=404, detail="Payment request not found")
    events = (
        db.query(ReviewEvent)
        .filter(ReviewEvent.payment_request_id == payment_id)
        .order_by(ReviewEvent.created_at.asc())
        .all()
    )
    return [{
        "id": event.id,
        "action": event.action,
        "note": event.note,
        "reviewer": event.reviewer,
        "created_at": event.created_at,
    } for event in events]
