from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import AuditEvent, PaymentRequest, UserAccount
from app.services.incident_intelligence import build_overview, detect_incidents


def make_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def add_user(db, email, role="customer"):
    user = UserAccount(
        email=email,
        display_name=email.split("@")[0],
        password_hash="test-hash",
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def add_event(db, user, event_type, created_at, metadata=None, amount=25, status="BLOCK"):
    payment = PaymentRequest(
        user_id=user.id,
        raw_instruction="Test payment",
        recipient_name=f"Recipient {created_at.timestamp()}",
        amount=amount,
        currency="USD",
        status=status,
        created_at=created_at,
    )
    db.add(payment)
    db.flush()
    db.add(AuditEvent(
        payment_request_id=payment.id,
        event_type=event_type,
        actor=user.email,
        message="Test event",
        metadata=metadata,
        created_at=created_at,
    ))
    db.flush()
    return payment


def test_repeated_paypal_errors_create_an_actionable_incident():
    db = make_db()
    now = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
    user = add_user(db, "customer@example.com")
    add_event(db, user, "PAYPAL_ERROR", now - timedelta(hours=2))
    add_event(db, user, "PAYPAL_ERROR", now - timedelta(hours=1))
    db.commit()

    incidents = detect_incidents(db, user, now=now)

    assert len(incidents) == 1
    assert incidents[0]["category"] == "paypal_errors"
    assert incidents[0]["severity"] == "high"
    assert incidents[0]["event_count_24h"] == 2
    assert "recommended_action" in incidents[0]
    db.close()


def test_a_spike_in_limit_blocks_is_reported_as_policy_signal():
    db = make_db()
    now = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
    user = add_user(db, "customer@example.com")
    for minutes in (10, 20, 30):
        add_event(
            db, user, "SPENDING_LIMIT_BLOCKED",
            now - timedelta(minutes=minutes),
            metadata={"violations": ["Daily spending limit exceeded"]},
        )
    db.commit()

    incidents = detect_incidents(db, user, now=now)

    assert len(incidents) == 1
    assert incidents[0]["category"] == "limit_blocks"
    assert incidents[0]["event_count_24h"] == 3
    assert "not evidence of a system failure" in incidents[0]["summary"]
    db.close()


def test_customer_incidents_are_scoped_but_staff_can_see_organization_signals():
    db = make_db()
    now = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
    first = add_user(db, "first@example.com")
    second = add_user(db, "second@example.com")
    staff = add_user(db, "reviewer@example.com", role="reviewer")

    add_event(db, first, "PAYPAL_ERROR", now - timedelta(hours=1))
    add_event(db, second, "PAYPAL_ERROR", now - timedelta(minutes=30))
    db.commit()

    assert detect_incidents(db, first, now=now) == []
    staff_incidents = detect_incidents(db, staff, now=now)
    assert len(staff_incidents) == 1
    assert staff_incidents[0]["event_count_24h"] == 2
    db.close()


def test_overview_counts_completed_spend_and_operational_outcomes():
    db = make_db()
    user = add_user(db, "metrics@example.com")
    db.add_all([
        PaymentRequest(
            user_id=user.id, raw_instruction="first", recipient_name="A", amount=80,
            currency="USD", status="COMPLETED",
        ),
        PaymentRequest(
            user_id=user.id, raw_instruction="second", recipient_name="B", amount=20,
            currency="USD", status="PAYPAL_CAPTURE_ERROR",
        ),
        PaymentRequest(
            user_id=user.id, raw_instruction="third", recipient_name="C", amount=500,
            currency="USD", status="BLOCK",
        ),
    ])
    db.commit()

    overview = build_overview(db, user)

    assert overview["scope"] == "account"
    assert overview["total_payments"] == 3
    assert overview["completed_payments"] == 1
    assert overview["completed_spend_usd"] == 80
    assert overview["blocked_payments"] == 1
    assert overview["paypal_errors"] == 1
    assert overview["success_rate_percent"] == 50
    db.close()
