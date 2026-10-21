from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PaymentRequest
from app.schemas.payment import PaymentIntent, RiskResult


def _normalized_words(value: str | None) -> set[str]:
    if not value:
        return set()
    ignored = {"pay", "for", "the", "a", "an", "to", "and", "of", "payment"}
    return {
        word.strip(".,!?;:'\"()[]{}").lower()
        for word in value.split()
        if len(word.strip(".,!?;:'\"()[]{}")) > 2
        and word.strip(".,!?;:'\"()[]{}").lower() not in ignored
    }


def assess_payment(
    db: Session,
    intent: PaymentIntent,
    raw_instruction: str,
    user_id: int | None = None,
) -> RiskResult:
    query = select(PaymentRequest).where(
        PaymentRequest.recipient_name.ilike(intent.recipient_name.strip()),
        PaymentRequest.status == "COMPLETED",
        PaymentRequest.currency == intent.currency.upper(),
    )
    if user_id is not None:
        query = query.where(PaymentRequest.user_id == user_id)

    previous = db.execute(
        query.order_by(PaymentRequest.created_at.desc()).limit(20)
    ).scalars().all()

    score = 0
    reasons = []
    amount_anomaly = False
    new_recipient = len(previous) == 0
    instruction_mismatch = False
    frequency_anomaly = False

    if new_recipient:
        score += 20
        reasons.append("This is a new recipient with no completed payment history on your account.")

    if previous:
        amounts = [float(payment.amount) for payment in previous if payment.amount is not None]
        if amounts:
            recent_amounts = amounts[:10]
            average_amount = sum(recent_amounts) / len(recent_amounts)
            anomaly_threshold = max(average_amount * 5, average_amount + 1000)

            if intent.amount > anomaly_threshold:
                amount_anomaly = True
                severe_threshold = max(average_amount * 10, average_amount + 2500)
                if intent.amount > severe_threshold:
                    score += 70
                    reasons.append(
                        "The requested amount is severely above this recipient's "
                        f"recent average of {intent.currency.upper()} {average_amount:.2f}."
                    )
                else:
                    score += 40
                    reasons.append(
                        "The requested amount is unusually high for this recipient "
                        f"(recent average: {intent.currency.upper()} {average_amount:.2f})."
                    )
            else:
                reasons.append(
                    f"The amount is within this recipient's recent payment range "
                    f"(average: {intent.currency.upper()} {average_amount:.2f})."
                )

        if intent.purpose and len(previous) >= 3:
            prior_purposes = [
                _normalized_words(item.purpose)
                for item in previous
                if item.purpose and _normalized_words(item.purpose)
            ]
            current_purpose = _normalized_words(intent.purpose)
            if len(prior_purposes) >= 3 and current_purpose:
                common_prior_words = set.intersection(*prior_purposes)
                if common_prior_words and not (common_prior_words & current_purpose):
                    instruction_mismatch = True
                    score += 30
                    reasons.append(
                        "The payment purpose differs from the consistent purpose used "
                        "in previous completed payments to this recipient."
                    )

    elif intent.amount >= 5000:
        amount_anomaly = True
        score += 40
        reasons.append("The amount is high for a first payment to this recipient.")

    if intent.amount >= 10000:
        amount_anomaly = True
        score += 35
        reasons.append("The requested payment amount is very large.")

    recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    frequency_query = select(PaymentRequest).where(
        PaymentRequest.recipient_name.ilike(intent.recipient_name.strip()),
        PaymentRequest.status == "COMPLETED",
        PaymentRequest.currency == intent.currency.upper(),
        PaymentRequest.created_at >= recent_cutoff,
    )
    if user_id is not None:
        frequency_query = frequency_query.where(PaymentRequest.user_id == user_id)
    recent_count = len(db.execute(frequency_query).scalars().all())
    if recent_count >= 5:
        frequency_anomaly = True
        score += 30
        reasons.append(
            f"You have made {recent_count} completed payments to this recipient in the last 24 hours."
        )

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
