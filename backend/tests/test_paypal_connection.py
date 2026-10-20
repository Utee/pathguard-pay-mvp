from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import security
from app.db import Base, get_db
from app.main import app
import app.api.paypal_connection as paypal_connection_api
import app.services.paypal as paypal_service
import app.services.paypal_vault as paypal_vault


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    vault_key = Fernet.generate_key().decode("utf-8")

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
        paypal_vault,
        "get_settings",
        lambda: SimpleNamespace(paypal_vault_encryption_key=vault_key),
    )
    paypal_settings = SimpleNamespace(
        paypal_client_id="sandbox-client-id",
        paypal_client_secret="sandbox-client-secret",
        paypal_base_url="https://api-m.sandbox.paypal.com",
        paypal_return_url="http://127.0.0.1:8000/api/payments/paypal/return",
        paypal_cancel_url="http://127.0.0.1:8000/api/payments/paypal/cancel",
    )
    monkeypatch.setattr(paypal_service, "settings", paypal_settings)
    monkeypatch.setattr(
        paypal_connection_api,
        "settings",
        SimpleNamespace(
            paypal_frontend_url="http://localhost:5173",
            paypal_connection_return_url="http://127.0.0.1:8000/api/paypal/connection/return",
            paypal_connection_cancel_url="http://127.0.0.1:8000/api/paypal/connection/cancel",
        ),
    )
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def register(client, email="wallet-owner@example.com"):
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


def auth_headers(account):
    return {"Authorization": f"Bearer {account['access_token']}"}


def test_paypal_connection_requires_authentication(client):
    assert client.get("/api/paypal/connection").status_code == 401
    assert client.post("/api/paypal/connection/setup").status_code == 401
    assert client.delete("/api/paypal/connection").status_code == 401


def test_connect_saved_wallet_use_it_for_approved_payment_and_disconnect(client, monkeypatch):
    account = register(client)
    headers = auth_headers(account)
    calls = {}

    async def create_setup_token(
        self,
        *,
        merchant_customer_id,
        return_url,
        cancel_url,
    ):
        calls["merchant_customer_id"] = merchant_customer_id
        calls["return_url"] = return_url
        calls["cancel_url"] = cancel_url
        return {
            "id": "sandbox-setup-token",
            "status": "PAYER_ACTION_REQUIRED",
            "links": [
                {
                    "rel": "approve",
                    "href": "https://www.sandbox.paypal.com/agreements/approve?token=sandbox-setup-token",
                }
            ],
        }

    async def create_payment_token(self, setup_token_id):
        assert setup_token_id == "sandbox-setup-token"
        return {
            "id": "sandbox-vault-payment-token",
            "customer": {"id": "sandbox-customer-id"},
            "payment_source": {
                "paypal": {
                    "email_address": "payer@example.com",
                    "payer_id": "sandbox-payer-id",
                }
            },
        }

    async def create_order(
        self,
        amount,
        currency,
        description,
        *,
        reference_id=None,
        vault_id=None,
    ):
        calls["vault_id"] = vault_id
        calls["order_amount"] = amount
        calls["order_currency"] = currency
        calls["reference_id"] = reference_id
        return {
            "id": "sandbox-vault-order",
            "status": "COMPLETED",
            "purchase_units": [
                {
                    "payments": {
                        "captures": [{"id": "sandbox-capture-id", "status": "COMPLETED"}]
                    }
                }
            ],
        }

    async def delete_payment_token(self, payment_token_id):
        calls["deleted_token"] = payment_token_id

    monkeypatch.setattr(paypal_service.PayPalClient, "create_setup_token", create_setup_token)
    monkeypatch.setattr(paypal_service.PayPalClient, "create_payment_token", create_payment_token)
    monkeypatch.setattr(paypal_service.PayPalClient, "create_order", create_order)
    monkeypatch.setattr(paypal_service.PayPalClient, "delete_payment_token", delete_payment_token)

    setup = client.post("/api/paypal/connection/setup", headers=headers)
    assert setup.status_code == 200
    assert setup.json()["status"] == "PAYER_ACTION_REQUIRED"
    assert "sandbox.paypal.com" in setup.json()["approval_url"]
    assert calls["merchant_customer_id"] == f"pathguard-user-{account['user']['id']}"

    returned = client.get(
        "/api/paypal/connection/return?token=sandbox-setup-token",
        follow_redirects=False,
    )
    assert returned.status_code == 303
    assert "paypal_connect=connected" in returned.headers["location"]

    connection = client.get("/api/paypal/connection", headers=headers)
    assert connection.status_code == 200
    assert connection.json()["connected"] is True
    assert connection.json()["email_address"] == "payer@example.com"
    assert "payment_token" not in connection.json()
    assert "ciphertext" not in connection.json()

    analysis = client.post(
        "/api/payments/analyze",
        headers=headers,
        json={"instruction": "Pay Sarah $150 for the logo"},
    )
    assert analysis.status_code == 200
    assert analysis.json()["risk"]["decision"] == "ALLOW"
    payment_id = analysis.json()["payment_id"]

    checkout = client.post(
        f"/api/payments/{payment_id}/paypal/create",
        headers=headers,
    )
    assert checkout.status_code == 200
    assert checkout.json()["status"] == "COMPLETED"
    assert checkout.json()["capture_id"] == "sandbox-capture-id"
    assert calls["vault_id"] == "sandbox-vault-payment-token"
    assert calls["order_currency"] == "USD"

    detail = client.get(f"/api/payments/{payment_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["status"] == "COMPLETED"
    assert detail.json()["paypal"]["capture_id"] == "sandbox-capture-id"

    disconnected = client.delete("/api/paypal/connection", headers=headers)
    assert disconnected.status_code == 200
    assert disconnected.json() == {"connected": False, "status": "not_connected"}
    assert calls["deleted_token"] == "sandbox-vault-payment-token"
    assert client.get("/api/paypal/connection", headers=headers).json()["connected"] is False


def test_connection_status_is_private_to_each_account(client):
    first = register(client, "first-wallet@example.com")
    second = register(client, "second-wallet@example.com")

    assert client.get(
        "/api/paypal/connection",
        headers=auth_headers(first),
    ).json()["connected"] is False
    assert client.get(
        "/api/paypal/connection",
        headers=auth_headers(second),
    ).json()["connected"] is False
