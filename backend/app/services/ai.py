import json
import re
from app.core.config import get_settings
from app.schemas.payment import PaymentIntent

settings = get_settings()


def _local_parse(instruction: str) -> PaymentIntent:
    amount_match = re.search(
        r"(?:\$|USD\s*)?(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:USD|dollars?)?",
        instruction,
        flags=re.IGNORECASE,
    )
    if not amount_match:
        raise ValueError("Could not find a payment amount. Try: 'Pay John $200 for the website'.")

    amount = float(amount_match.group(1).replace(",", ""))

    recipient_match = re.search(
        r"\b(?:to|for)\s+([A-Za-z][A-Za-z0-9 _-]{1,80}?)(?=\s+\$|\s+USD\b|\s+for\b|\s+of\b|$)",
        instruction,
        flags=re.IGNORECASE,
    )

    recipient = recipient_match.group(1).strip() if recipient_match else "Unknown recipient"

    purpose_match = re.search(
        r"\bfor\s+(.+)$",
        instruction,
        flags=re.IGNORECASE,
    )
    purpose = purpose_match.group(1).strip() if purpose_match else None

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
- Currency defaults to USD if not explicitly stated.
- purpose may be null.

User instruction:
{instruction}
"""

    response = client.responses.create(
        model=settings.openai_model,
        input=prompt,
    )

    data = json.loads(response.output_text)
    return PaymentIntent.model_validate(data)
