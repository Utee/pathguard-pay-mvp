from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import PaymentRequest, RiskAssessment, ReviewEvent
from app.api.payments import _has_human_approval


def make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_review_approval_survives_paypal_processing_status():
    db = make_db()

    payment = PaymentRequest(
        raw_instruction="Pay John $10000 for the website",
        recipient_name="John",
        amount=10000,
        currency="USD",
        purpose="the website",
        status="PAYPAL_PENDING_APPROVAL",
    )
    db.add(payment)
    db.flush()

    db.add(
        RiskAssessment(
            payment_request_id=payment.id,
            risk_score=35,
            decision="REVIEW",
            reasons=["Large payment"],
        )
    )
    db.add(
        ReviewEvent(
            payment_request_id=payment.id,
            action="SUBMITTED",
            note="Queued for review.",
            created_at=datetime(2026, 10, 4, tzinfo=timezone.utc),
        )
    )
    db.add(
        ReviewEvent(
            payment_request_id=payment.id,
            action="APPROVED",
            note="Approved.",
            created_at=datetime(2026, 10, 4, 0, 1, tzinfo=timezone.utc),
        )
    )
    db.commit()
    db.refresh(payment)

    assert _has_human_approval(payment) is True


def test_rejected_review_never_counts_as_approved():
    db = make_db()

    payment = PaymentRequest(
        raw_instruction="Pay John $10000 for the website",
        recipient_name="John",
        amount=10000,
        currency="USD",
        purpose="the website",
        status="REVIEW_REJECTED",
    )
    db.add(payment)
    db.flush()

    db.add(
        RiskAssessment(
            payment_request_id=payment.id,
            risk_score=70,
            decision="REVIEW",
            reasons=["Large payment"],
        )
    )
    db.add(
        ReviewEvent(
            payment_request_id=payment.id,
            action="REJECTED",
            note="Rejected.",
        )
    )
    db.commit()
    db.refresh(payment)

    assert _has_human_approval(payment) is False
