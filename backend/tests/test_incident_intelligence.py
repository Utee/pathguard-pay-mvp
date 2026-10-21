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


def test_summary_uses_rules_when_openrouter_is_not_configured(monkeypatch):
    from types import SimpleNamespace
    import app.services.incident_intelligence as intelligence

    db = make_db()
    user = add_user(db, "summary@example.com")
    add_event(
        db, user, "PAYPAL_ERROR",
        datetime.now(timezone.utc) - timedelta(minutes=3),
    )
    add_event(
        db, user, "PAYPAL_ERROR",
        datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    db.commit()
    monkeypatch.setattr(
        intelligence, "get_settings",
        lambda: SimpleNamespace(openrouter_api_key=None, openrouter_model="unused"),
    )

    result = intelligence.summarize_intelligence(db, user)

    assert result["source"] == "rules"
    assert "incident signal group" in result["summary"]
    assert result["priority_actions"][0]["title"] == "Repeated PayPal processing errors"
    db.close()


def test_openrouter_summary_uses_aggregate_only_context(monkeypatch):
    from types import SimpleNamespace
    import app.services.incident_intelligence as intelligence

    db = make_db()
    user = add_user(db, "private-customer@example.com")
    add_event(
        db, user, "PAYPAL_ERROR",
        datetime.now(timezone.utc) - timedelta(minutes=3),
        amount=735,
    )
    add_event(
        db, user, "PAYPAL_ERROR",
        datetime.now(timezone.utc) - timedelta(minutes=2),
        amount=735,
    )
    db.commit()
    monkeypatch.setattr(
        intelligence, "get_settings",
        lambda: SimpleNamespace(
            openrouter_api_key="test-only-key",
            openrouter_model="test/model",
            openrouter_base_url="https://openrouter.ai/api/v1",
        ),
    )

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "Two provider errors need investigation."}}]}

    def fake_post(url, headers, json, timeout):
        assert url == "https://openrouter.ai/api/v1/chat/completions"
        assert json["model"] == "test/model"
        assert "private-customer@example.com" not in json["messages"][1]["content"]
        assert "Test payment" not in json["messages"][1]["content"]
        assert '"completed_spend_usd"' in json["messages"][1]["content"] or '"metrics"' in json["messages"][1]["content"]
        assert timeout == 8.0
        return FakeResponse()

    monkeypatch.setattr(intelligence.httpx, "post", fake_post)

    result = intelligence.summarize_intelligence(db, user)

    assert result["source"] == "openrouter"
    assert result["summary"] == "Two provider errors need investigation."
    assert result["disclaimer"]
    db.close()


def test_notifications_are_scoped_to_customer_and_available_to_staff():
    from app.services.incident_intelligence import build_notifications

    db = make_db()
    now = datetime.now(timezone.utc)
    first = add_user(db, "notifications-first@example.com")
    second = add_user(db, "notifications-second@example.com")
    staff = add_user(db, "notifications-reviewer@example.com", role="reviewer")

    first_payment = add_event(
        db, first, "SPENDING_LIMIT_BLOCKED", now - timedelta(minutes=2),
        metadata={"violations": ["Daily limit exceeded"]},
    )
    second_payment = add_event(
        db, second, "PAYPAL_ERROR", now - timedelta(minutes=1),
    )
    db.commit()

    first_feed = build_notifications(db, first, now=now)
    staff_feed = build_notifications(db, staff, now=now)

    assert len(first_feed) == 1
    assert first_feed[0]["payment_id"] == first_payment.id
    assert first_feed[0]["title"] == "Spending limit enforced"
    assert len(staff_feed) == 2
    assert {item["payment_id"] for item in staff_feed} == {first_payment.id, second_payment.id}
    db.close()


def test_routine_allow_events_do_not_hide_actionable_notifications():
    from app.services.incident_intelligence import build_notifications

    db = make_db()
    now = datetime.now(timezone.utc)
    user = add_user(db, "notification-priority@example.com")
    for seconds in range(20):
        add_event(
            db, user, "RISK_ASSESSED",
            now - timedelta(seconds=seconds + 1),
            metadata={"decision": "ALLOW"},
            status="ALLOW",
        )
    error_payment = add_event(
        db, user, "PAYPAL_ERROR",
        now - timedelta(minutes=10),
    )
    db.commit()

    feed = build_notifications(db, user, now=now, limit=5)

    assert any(item["payment_id"] == error_payment.id for item in feed)
    db.close()
