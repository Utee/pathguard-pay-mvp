import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from types import SimpleNamespace

from app.core import security
from app.db import Base, get_db
from app.main import app


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
    return response.json()


def test_authentication_required_for_payment_and_limit_apis(client):
    assert client.get("/api/payments").status_code == 401
    assert client.get("/api/limits/settings").status_code == 401


def test_register_login_and_current_account(client):
    account = register(client, "Person@Example.com")
    assert account["user"]["email"] == "person@example.com"
    assert account["user"]["role"] == "customer"
    token = account["access_token"]

    current = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert current.status_code == 200
    assert current.json()["email"] == "person@example.com"

    login = client.post(
        "/api/auth/login",
        json={"email": "PERSON@example.com", "password": "a-long-test-password-123"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["id"] == account["user"]["id"]


def test_customer_cannot_access_staff_review_queue(client):
    account = register(client, "customer@example.com")
    response = client.get(
        "/api/reviews",
        headers={"Authorization": f"Bearer {account['access_token']}"},
    )
    assert response.status_code == 403


def test_spending_limits_belong_to_each_account(client):
    first = register(client, "first@example.com")
    second = register(client, "second@example.com")
    first_headers = {"Authorization": f"Bearer {first['access_token']}"}
    second_headers = {"Authorization": f"Bearer {second['access_token']}"}

    changed = client.put(
        "/api/limits/settings",
        headers=first_headers,
        json={
            "daily_limit": 75,
            "weekly_limit": 300,
            "monthly_limit": 900,
            "per_transaction_limit": 50,
            "timezone": "Africa/Lagos",
        },
    )
    assert changed.status_code == 200
    assert changed.json()["daily_limit"] == 75

    first_settings = client.get("/api/limits/settings", headers=first_headers).json()
    second_settings = client.get("/api/limits/settings", headers=second_headers).json()
    assert first_settings["daily_limit"] == 75
    assert second_settings["daily_limit"] == 1000
    assert second_settings["per_transaction_limit"] is None


def test_expired_or_invalid_tokens_are_rejected(client):
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )
    assert response.status_code == 401


def test_payment_history_and_details_are_private_to_the_owner(client):
    first = register(client, "owner@example.com")
    second = register(client, "other@example.com")
    first_headers = {"Authorization": f"Bearer {first['access_token']}"}
    second_headers = {"Authorization": f"Bearer {second['access_token']}"}

    first_analysis = client.post(
        "/api/payments/analyze",
        headers=first_headers,
        json={"instruction": "Pay Alice $100 for groceries"},
    )
    second_analysis = client.post(
        "/api/payments/analyze",
        headers=second_headers,
        json={"instruction": "Pay Bob $75 for utilities"},
    )
    assert first_analysis.status_code == 200
    assert second_analysis.status_code == 200

    first_id = first_analysis.json()["payment_id"]
    second_id = second_analysis.json()["payment_id"]
    first_history = client.get("/api/payments", headers=first_headers).json()
    second_history = client.get("/api/payments", headers=second_headers).json()

    assert [item["id"] for item in first_history] == [first_id]
    assert [item["id"] for item in second_history] == [second_id]
    assert client.get(f"/api/payments/{first_id}", headers=second_headers).status_code == 404
    assert client.get(f"/api/payments/{second_id}", headers=first_headers).status_code == 404
