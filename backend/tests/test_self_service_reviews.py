from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import security
from app.db import Base, get_db
from app.main import app
from app.schemas.payment import RiskResult


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            jwt_secret_key="test-signing-secret-with-at-least-thirty-two-chars",
            access_token_expire_minutes=60,
        ),
    )
    monkeypatch.setattr(
        "app.api.payments.assess_payment",
        lambda *args, **kwargs: RiskResult(
            risk_score=58,
            decision="REVIEW",
            reasons=["Unusually large amount for this recipient."],
            amount_anomaly=True,
        ),
    )
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def register(client, email):
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "display_name": email.split("@")[0],
            "password": "a-long-test-password-123",
        },
    )
    assert response.status_code == 201
    data = response.json()
    return data, {"Authorization": f"Bearer {data['access_token']}"}


def create_review_payment(client, headers):
    response = client.post(
        "/api/payments/analyze",
        headers=headers,
        json={"instruction": "Pay Sarah $150 for the logo"},
    )
    assert response.status_code == 200
    assert response.json()["risk"]["decision"] == "REVIEW"
    return response.json()["payment_id"]


def test_customer_can_list_only_their_own_review_payments(client):
    _, owner_headers = register(client, "owner@example.com")
    _, other_headers = register(client, "other@example.com")
    payment_id = create_review_payment(client, owner_headers)
    create_review_payment(client, other_headers)

    reviews = client.get("/api/reviews/mine", headers=owner_headers)

    assert reviews.status_code == 200
    assert [item["id"] for item in reviews.json()] == [payment_id]
    assert reviews.json()[0]["status"] == "REVIEW_PENDING"


def test_review_confirmation_requires_password_and_records_user_override(client):
    _, headers = register(client, "owner@example.com")
    payment_id = create_review_payment(client, headers)

    wrong_password = client.post(
        f"/api/reviews/{payment_id}/confirm",
        headers=headers,
        json={"password": "incorrect-password"},
    )
    assert wrong_password.status_code == 401

    confirmed = client.post(
        f"/api/reviews/{payment_id}/confirm",
        headers=headers,
        json={"password": "a-long-test-password-123"},
    )

    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "REVIEW_APPROVED"

    detail = client.get(f"/api/payments/{payment_id}", headers=headers)
    assert detail.status_code == 200
    assert any(event["action"] == "USER_CONFIRMED" for event in detail.json()["review_events"])
    assert any(event["event_type"] == "USER_CONFIRMED_REVIEW" for event in detail.json()["audit"])


def test_user_cannot_confirm_another_accounts_review(client):
    _, owner_headers = register(client, "owner@example.com")
    _, other_headers = register(client, "other@example.com")
    payment_id = create_review_payment(client, owner_headers)

    response = client.post(
        f"/api/reviews/{payment_id}/confirm",
        headers=other_headers,
        json={"password": "a-long-test-password-123"},
    )

    assert response.status_code == 404


def test_user_can_reject_own_review_and_cannot_confirm_after_rejection(client):
    _, headers = register(client, "owner@example.com")
    payment_id = create_review_payment(client, headers)

    rejected = client.post(f"/api/reviews/{payment_id}/reject-own", headers=headers)

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REVIEW_REJECTED"

    confirmed = client.post(
        f"/api/reviews/{payment_id}/confirm",
        headers=headers,
        json={"password": "a-long-test-password-123"},
    )
    assert confirmed.status_code == 409
