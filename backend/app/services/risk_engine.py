from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PaymentRequest
from app.schemas.payment import PaymentIntent, RiskResult


def assess_payment(
    db: Session,
    intent: PaymentIntent,
    raw_instruction: str,
    user_id: int | None = None,
) -> RiskResult:
    query = select(PaymentRequest).where(
        PaymentRequest.recipient_name.ilike(intent.recipient_name),
        PaymentRequest.status == "COMPLETED",
    )
    if user_id is not None:
        query = query.where(PaymentRequest.user_id == user_id)
    previous = db.execute(query.order_by(PaymentRequest.created_at.desc())).scalars().all()

    score = 0
    reasons = []
    amount_anomaly = False
    new_recipient = len(previous) == 0
    instruction_mismatch = False
    frequency_anomaly = False

    if new_recipient:
        score += 20
        reasons.append("This is a new recipient.")

    if previous:
        amounts = [float(payment.amount) for payment in previous if payment.amount is not None]
        if amounts:
            average_amount = sum(amounts) / len(amounts)
            anomaly_threshold = max(average_amount * 5, average_amount + 1000)

            if intent.amount > anomaly_threshold:
                amount_anomaly = True
                severe_threshold = max(average_amount * 10, average_amount + 2500)
                if intent.amount > severe_threshold:
                    score += 70
                    reasons.append(
                        "The requested amount is severely above this recipient's "
                        f"normal range (recent average: ${average_amount:.2f})."
                    )
                else:
                    score += 40
                    reasons.append(
                        "The requested amount is unusually high "
                        f"for this recipient (recent average: ${average_amount:.2f})."
                    )
            else:
                reasons.append("The amount is within the recipient's recent payment range.")
    else:
        if intent.amount >= 5000:
            amount_anomaly = True
            score += 40
            reasons.append("The amount is high for a first payment to this recipient.")

    if intent.amount >= 10000:
        amount_anomaly = True
        score += 35
        reasons.append("The requested payment amount is very large.")

    score = min(score, 100)
    if score >= 70:
        decision = "BLOCK"
    elif score >= 30:
        decision = "REVIEW"
    else:
        decision = "ALLOW"

    if not reasons:
        reasons.append("No significant risk signals were detected.")

    return RiskResult(
        risk_score=score,
        decision=decision,
        reasons=reasons,
        amount_anomaly=amount_anomaly,
        new_recipient=new_recipient,
        instruction_mismatch=instruction_mismatch,
        frequency_anomaly=frequency_anomaly,
    )
