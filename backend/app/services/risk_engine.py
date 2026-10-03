from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PaymentRequest
from app.schemas.payment import PaymentIntent, RiskResult


def assess_payment(
    db: Session,
    intent: PaymentIntent,
    raw_instruction: str,
) -> RiskResult:
    """
    Deterministic PathGuard payment-risk assessment.

    Rules:
    - New recipient: +20
    - Large first payment (>= $5,000): +40
    - Unusually large payment compared with recipient history: +40
    - Very large payment (>= $10,000): +35
    - Risk score >= 70: BLOCK
    - Risk score >= 30: REVIEW
    - Otherwise: ALLOW
    """

    previous = (
        db.execute(
            select(PaymentRequest)
            .where(
                PaymentRequest.recipient_name.ilike(
                    intent.recipient_name
                )
            )
            .order_by(PaymentRequest.created_at.desc())
        )
        .scalars()
        .all()
    )

    score = 0
    reasons: list[str] = []

    amount_anomaly = False
    new_recipient = len(previous) == 0
    instruction_mismatch = False
    frequency_anomaly = False

    # ---------------------------------------------------------
    # New recipient
    # ---------------------------------------------------------

    if new_recipient:
        score += 20
        reasons.append("This is a new recipient.")

    # ---------------------------------------------------------
    # Amount anomaly
    # ---------------------------------------------------------

    if previous:
        amounts = [
            float(payment.amount)
            for payment in previous
            if payment.amount is not None
        ]

        if amounts:
            average_amount = sum(amounts) / len(amounts)

            if intent.amount > max(
                average_amount * 5,
                average_amount + 1000,
            ):
                amount_anomaly = True
                score += 40

                reasons.append(
                    "The requested amount is unusually high "
                    f"for this recipient "
                    f"(recent average: ${average_amount:.2f})."
                )
            else:
                reasons.append(
                    "The amount is within the recipient's "
                    "recent payment range."
                )

    else:
        # First payment to this recipient.
        if intent.amount >= 5000:
            amount_anomaly = True
            score += 40

            reasons.append(
                "The amount is high for a first payment "
                "to this recipient."
            )

    # ---------------------------------------------------------
    # Very large payment
    # ---------------------------------------------------------

    if intent.amount >= 10000:
        amount_anomaly = True
        score += 35

        reasons.append(
            "The requested payment amount is very large."
        )

    # ---------------------------------------------------------
    # Keep risk score within 0-100
    # ---------------------------------------------------------

    score = min(score, 100)

    # ---------------------------------------------------------
    # Decision
    # ---------------------------------------------------------

    if score >= 70:
        decision = "BLOCK"
    elif score >= 30:
        decision = "REVIEW"
    else:
        decision = "ALLOW"

    if not reasons:
        reasons.append(
            "No significant risk signals were detected."
        )

    # IMPORTANT:
    # Return the Pydantic RiskResult from app.schemas.payment.
    # Do not define another RiskResult class in this file.
    return RiskResult(
        risk_score=score,
        decision=decision,
        reasons=reasons,
        amount_anomaly=amount_anomaly,
        new_recipient=new_recipient,
        instruction_mismatch=instruction_mismatch,
        frequency_anomaly=frequency_anomaly,
    )