import json

import httpx
import pytest

from app.services.paypal import PayPalResourceNotFound, _paypal_error


def test_paypal_invalid_resource_id_is_classified():
    response = httpx.Response(
        404,
        json={
            "name": "RESOURCE_NOT_FOUND",
            "details": [
                {
                    "issue": "INVALID_RESOURCE_ID",
                    "description": "Specified resource ID does not exist.",
                }
            ],
            "debug_id": "test-debug-id",
        },
    )

    error = _paypal_error(response, "get order")

    assert isinstance(error, PayPalResourceNotFound)
    assert error.status_code == 404
    assert error.name == "RESOURCE_NOT_FOUND"
    assert error.debug_id == "test-debug-id"
    assert "INVALID_RESOURCE_ID" in str(error)
