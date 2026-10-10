from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import PaymentRequest
from app.schemas.payment import PaymentIntent
from app.services.risk_engine import assess_payment


def make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_new_small_payment_is_allowed_with_new_recipient_signal():
    db = make_db()

    result = assess_payment(
        db,
        PaymentIntent(
            recipient_name="John",
            amount=200,
            currency="USD",
            purpose="website",
        ),
        "Pay John $200 for the website",
    )

    assert result.decision == "ALLOW"
    assert result.risk_score == 20
    assert result.new_recipient is True


def test_large_first_payment_is_blocked():
    db = make_db()

    result = assess_payment(
        db,
        PaymentIntent(
            recipient_name="John",
            amount=10000,
            currency="USD",
            purpose="website",
        ),
        "Pay John $10000 for the website",
    )

    assert result.decision == "BLOCK"
    assert result.risk_score >= 70
    assert result.amount_anomaly is True


def test_large_amount_after_normal_history_is_blocked():
    db = make_db()

    db.add_all(
        [
            PaymentRequest(
                raw_instruction="Pay John $200 for website",
                recipient_name="John",
                amount=200,
                currency="USD",
                status="COMPLETED",
                purpose="website",
            ),
            PaymentRequest(
                raw_instruction="Pay John $150 for website",
                recipient_name="John",
                amount=150,
                currency="USD",
                status="COMPLETED",
                purpose="website",
            ),
        ]
    )
    db.commit()

    result = assess_payment(
        db,
        PaymentIntent(
            recipient_name="John",
            amount=5000,
            currency="USD",
            purpose="website",
        ),
        "Pay John $5000 for the website",
    )

    assert result.decision == "BLOCK"
    assert result.amount_anomaly is True


def test_repeat_recipient_normal_amount_is_allowed():
    db = make_db()

    db.add(
        PaymentRequest(
            raw_instruction="Pay John $200 for website",
            recipient_name="John",
            amount=200,
            currency="USD",
            status="COMPLETED",
            purpose="website",
        )
    )
    db.commit()

    result = assess_payment(
        db,
        PaymentIntent(
            recipient_name="John",
            amount=250,
            currency="USD",
            purpose="website",
        ),
        "Pay John $250 for the website",
    )

    assert result.decision == "ALLOW"
    assert result.risk_score == 0
    assert result.new_recipient is False
