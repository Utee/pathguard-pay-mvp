from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import PaymentRequest, SpendingLimitSettings
from app.schemas.payment import PaymentIntent, RiskResult
from app.services.spending_limits import (
    apply_spending_policy,
    calculate_usage,
    check_spending_limits,
    get_or_create_settings,
)


def make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def default_policy(db):
    policy = get_or_create_settings(db)
    policy.daily_limit = 1000
    policy.weekly_limit = 10000
    policy.monthly_limit = 10000
    policy.per_transaction_limit = None
    policy.timezone = "Africa/Lagos"
    db.commit()
    return policy


def payment(*, amount, status, created_at, reservation_expires_at=None, currency="USD"):
    return PaymentRequest(
        raw_instruction=f"Pay Test ${amount} for testing",
        recipient_name="Test",
        amount=amount,
        currency=currency,
        purpose="testing",
        status=status,
        created_at=created_at,
        limit_reservation_expires_at=reservation_expires_at,
    )


def test_daily_limit_blocks_payment_even_when_risk_engine_allows_it():
    db = make_db()
    policy = default_policy(db)
    now = datetime(2026, 10, 10, 10, tzinfo=timezone.utc)
    result, violations = apply_spending_policy(
        db,
        PaymentIntent(recipient_name="Sarah", amount=1200, currency="USD", purpose="logo"),
        RiskResult(risk_score=20, decision="ALLOW", reasons=["New recipient"]),
        now=now,
    )
    assert result.decision == "BLOCK"
    assert result.risk_score == 100
    assert any("Daily spending limit exceeded" in item for item in violations)
    db.close()


def test_completed_spend_counts_against_daily_weekly_and_monthly_limits():
    db = make_db()
    policy = default_policy(db)
    now = datetime(2026, 10, 10, 10, tzinfo=timezone.utc)
    db.add(payment(
        amount=700,
        status="COMPLETED",
        created_at=now - timedelta(hours=1),
    ))
    db.commit()

    violations, usage = check_spending_limits(
        db, amount=400, currency="USD", policy=policy, now=now,
    )
    assert usage["daily"] == 700
    assert any("Daily spending limit exceeded" in item for item in violations)
    assert not any("Weekly spending limit exceeded" in item for item in violations)
    db.close()


def test_active_reservation_counts_but_expired_reservation_does_not():
    db = make_db()
    policy = default_policy(db)
    now = datetime(2026, 10, 10, 10, tzinfo=timezone.utc)
    db.add_all([
        payment(
            amount=750,
            status="ALLOW",
            created_at=now - timedelta(minutes=5),
            reservation_expires_at=now + timedelta(minutes=20),
        ),
        payment(
            amount=900,
            status="ALLOW",
            created_at=now - timedelta(hours=2),
            reservation_expires_at=now - timedelta(minutes=1),
        ),
    ])
    db.commit()

    violations, usage = check_spending_limits(
        db, amount=300, currency="USD", policy=policy, now=now,
    )
    assert usage["daily"] == 750
    assert usage["reserved_amount"] == 750
    assert any("Daily spending limit exceeded" in item for item in violations)
    db.close()


def test_blocked_attempt_does_not_consume_budget_or_recipient_history():
    db = make_db()
    policy = default_policy(db)
    now = datetime(2026, 10, 10, 10, tzinfo=timezone.utc)
    db.add(payment(
        amount=10000,
        status="BLOCK",
        created_at=now - timedelta(minutes=1),
    ))
    db.commit()

    violations, usage = check_spending_limits(
        db, amount=900, currency="USD", policy=policy, now=now,
    )
    assert usage["daily"] == 0
    assert violations == []
    db.close()


def test_non_usd_payment_is_blocked_until_currency_conversion_exists():
    db = make_db()
    policy = default_policy(db)
    violations, _ = check_spending_limits(
        db,
        amount=100,
        currency="NGN",
        policy=policy,
        now=datetime(2026, 10, 10, tzinfo=timezone.utc),
    )
    assert len(violations) == 1
    assert "configured in USD" in violations[0]
    db.close()


def test_per_transaction_limit_is_enforced():
    db = make_db()
    policy = default_policy(db)
    policy.per_transaction_limit = 250
    db.commit()

    violations, _ = check_spending_limits(
        db,
        amount=300,
        currency="USD",
        policy=policy,
        now=datetime(2026, 10, 10, 10, tzinfo=timezone.utc),
    )
    assert any("Per-transaction limit exceeded" in item for item in violations)
    db.close()
