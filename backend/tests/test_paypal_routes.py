from fastapi.testclient import TestClient

from app.main import app


def test_paypal_return_route_is_not_shadowed_by_payment_id_route():
    client = TestClient(app)

    response = client.get("/api/payments/paypal/return", follow_redirects=False)

    assert response.status_code == 307
    assert "paypal=error" in response.headers["location"]
    assert "Missing%20PayPal%20order%20token" in response.headers["location"]


def test_paypal_cancel_route_is_not_shadowed_by_payment_id_route():
    client = TestClient(app)

    response = client.get("/api/payments/paypal/cancel", follow_redirects=False)

    assert response.status_code == 307
    assert "paypal=cancelled" in response.headers["location"]
