import os

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app import db
from app.core.config import Settings
from app.models import AuditEvent, PaymentRequest


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+psycopg"])
def test_render_database_urls_use_installed_driver(scheme):
    url, options = db.database_engine_options(f"{scheme}://user:password@localhost/demo")
    assert url.drivername == "postgresql+psycopg"
    assert options["pool_pre_ping"] is True
    assert options["pool_size"] + options["max_overflow"] == 10


def test_hosted_callbacks_preserve_explicit_overrides():
    settings = Settings(
        _env_file=None,
        public_api_url="https://example.onrender.com/",
        paypal_cancel_url="https://custom.example/cancel",
    )
    assert settings.paypal_return_url == "https://example.onrender.com/api/payments/paypal/return"
    assert settings.paypal_connection_return_url == "https://example.onrender.com/api/paypal/connection/return"
    assert settings.paypal_connection_cancel_url == "https://example.onrender.com/api/paypal/connection/cancel"
    assert settings.paypal_cancel_url == "https://custom.example/cancel"


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="Requires a disposable PostgreSQL database")
def test_postgres_schema_initialization_and_audit_roundtrip(monkeypatch):
    # CI supplies an isolated database, never the deployed application's database.
    url, options = db.database_engine_options(os.environ["TEST_POSTGRES_URL"])
    engine = create_engine(url, **options)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db.settings, "database_url", str(url))
    try:
        db.initialize_database()
        db.initialize_database()
        assert "metadata" in {c["name"] for c in inspect(engine).get_columns("audit_events")}
        with Session(engine) as session:
            payment = PaymentRequest(raw_instruction="Pay John $20", recipient_name="John", amount=20)
            session.add(payment)
            session.flush()
            event = AuditEvent(payment_request_id=payment.id, event_type="TEST", message="Roundtrip",
                               event_metadata={"decision": "REVIEW", "reasons": ["New recipient"]})
            session.add(event)
            session.commit()
            event_id = event.id
        with Session(engine) as session:
            event = session.scalar(select(AuditEvent).where(AuditEvent.id == event_id))
            assert event.event_metadata["reasons"] == ["New recipient"]
    finally:
        db.Base.metadata.drop_all(engine)
        engine.dispose()
