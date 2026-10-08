import pytest

from app.services.ai import _local_parse


def test_local_parser_extracts_recipient_before_amount():
    intent = _local_parse("Pay John $10000 for the website")

    assert intent.recipient_name == "John"
    assert intent.amount == 10000
    assert intent.currency == "USD"
    assert intent.purpose == "the website"


def test_local_parser_handles_send_to():
    intent = _local_parse("Send to Acme Studio $250 for logo design")

    assert intent.recipient_name == "Acme Studio"
    assert intent.amount == 250
    assert intent.purpose == "logo design"


def test_local_parser_rejects_missing_recipient():
    with pytest.raises(ValueError, match="recipient"):
        _local_parse("Pay $200 for the website")
