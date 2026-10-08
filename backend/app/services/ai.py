import json
import re
from math import isfinite

from app.core.config import get_settings
from app.schemas.payment import PaymentIntent

settings = get_settings()

_AMOUNT_RE = re.compile(
    r"(?:(?:\$|USD\s*)\s*)?([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)\s*(?:USD|dollars?)?",
    re.IGNORECASE,
)


def _local_parse(instruction: str) -> PaymentIntent:
    """Parse common payment instructions without an LLM.

    The fallback parser is deliberately conservative because its output
    controls a money-moving workflow. It must identify a real recipient
    rather than silently using a placeholder.
    """
    text = " ".join(instruction.strip().split())

    amount_match = _AMOUNT_RE.search(text)
    if not amount_match:
        raise ValueError(
            "Could not find a payment amount. "
            "Try: 'Pay John $200 for the website'."
        )

    amount = float(amount_match.group(1).replace(",", ""))
    if not isfinite(amount) or amount <= 0:
        raise ValueError("Payment amount must be a positive number.")

    # Prefer the explicit payment verb. This prevents "for the website"
    # from being mistaken for the recipient in phrases such as
    # "Pay John $200 for the website".
    before_amount = text[: amount_match.start()].strip()
    recipient_match = re.search(
        r"\b(?:pay|send|transfer)\s+(?:to\s+)?(.+?)\s*$",
        before_amount,
        re.IGNORECASE,
    )

    if not recipient_match:
        raise ValueError(
            "Could not identify the recipient. "
            "Try: 'Pay John $200 for the website'."
        )

    recipient = recipient_match.group(1).strip(" ,")
    recipient = re.sub(r"\s+", " ", recipient)

    if recipient.lower() in {"me", "someone", "somebody", "unknown", "the website"}:
        raise ValueError("Could not identify a valid payment recipient.")

    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 ._'&-]{0,119}", recipient):
        raise ValueError("Could not identify a valid payment recipient.")

    purpose_match = re.search(
        r"\b(?:for|of)\s+(.+)$",
        text[amount_match.end():],
        re.IGNORECASE,
    )
    purpose = purpose_match.group(1).strip(" .") if purpose_match else None

    return PaymentIntent(
        recipient_name=recipient,
        amount=amount,
        currency="USD",
        purpose=purpose,
    )


def extract_payment_intent(instruction: str) -> PaymentIntent:
    if not settings.openai_api_key:
        return _local_parse(instruction)

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)

    prompt = f"""
Extract a payment intent from this user instruction.

Return ONLY valid JSON with:
recipient_name, amount, currency, purpose.

Rules:
- Never invent an amount.
- Never invent a recipient.
- The recipient is the person/business being paid, not the purpose.
- Currency defaults to USD if not explicitly stated.
- purpose may be null.
- If the recipient or amount cannot be identified confidently, return null for that field.

User instruction:
{instruction}
"""

    response = client.responses.create(
        model=settings.openai_model,
        input=prompt,
    )

    data = json.loads(response.output_text)
    intent = PaymentIntent.model_validate(data)

    if not intent.recipient_name.strip():
        raise ValueError("Could not identify a valid payment recipient.")

    if not isfinite(intent.amount) or intent.amount <= 0:
        raise ValueError("Payment amount must be a positive number.")

    intent.recipient_name = intent.recipient_name.strip()
    intent.currency = intent.currency.upper().strip()
    if intent.purpose:
        intent.purpose = intent.purpose.strip()

    return intent
