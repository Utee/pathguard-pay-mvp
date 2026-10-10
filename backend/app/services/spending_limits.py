from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PaymentRequest, SpendingLimitSettings
from app.schemas.payment import PaymentIntent, RiskResult

LIMIT_CURRENCY = "USD"
ANALYSIS_RESERVATION_MINUTES = 30
PAYPAL_RESERVATION_HOURS = 24

# Completed payments count as actual spend. Eligible in-flight payments count
# only while their explicit reservation is active. Blocked/rejected/cancelled
# attempts never contribute to the spend baseline.
RESERVABLE_STATUSES = {
    "ALLOW",
    "REVIEW_PENDING",
    "REVIEW_APPROVED",
    "PAYPAL_PENDING_APPROVAL",
    "PAYPAL_PENDING_CAPTURE",
    "PAYPAL_CAPTURE_ERROR",
}
COUNTED_STATUSES = RESERVABLE_STATUSES | {"COMPLETED"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        # SQLite removes timezone metadata from DateTime columns; values are
        # written in UTC throughout this MVP.
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def get_or_create_settings(db: Session) -> SpendingLimitSettings:
    policy = db.get(SpendingLimitSettings, 1)
    if policy is None:
        policy = SpendingLimitSettings(
            id=1,
            daily_limit=1000.0,
            weekly_limit=10000.0,
            monthly_limit=10000.0,
            per_transaction_limit=None,
            timezone="Africa/Lagos",
        )
        db.add(policy)
        db.flush()
    return policy


def _period_starts(now: datetime, timezone_name: str) -> dict[str, datetime]:
    try:
        local_now = now.astimezone(ZoneInfo(timezone_name))
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown timezone: {timezone_name}") from exc

    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = (day_start - timedelta(days=local_now.weekday()))
    month_start = day_start.replace(day=1)
    return {
        "daily": day_start.astimezone(timezone.utc),
        "weekly": week_start.astimezone(timezone.utc),
        "monthly": month_start.astimezone(timezone.utc),
    }


def calculate_usage(
    db: Session,
    policy: SpendingLimitSettings | None = None,
    *,
    now: datetime | None = None,
    exclude_payment_id: int | None = None,
) -> dict:
    """Return current-period completed spend plus active reservation amounts."""
    policy = policy or get_or_create_settings(db)
    now = as_utc(now or utc_now())
    assert now is not None
    starts = _period_starts(now, policy.timezone)

    payments = db.execute(
        select(PaymentRequest)
        .where(
            PaymentRequest.currency == LIMIT_CURRENCY,
            PaymentRequest.status.in_(COUNTED_STATUSES),
        )
    ).scalars().unique().all()

    usage = {"daily": 0.0, "weekly": 0.0, "monthly": 0.0}
    reserved_amount = 0.0

    for payment in payments:
        if payment.id == exclude_payment_id:
            continue

        amount = float(payment.amount or 0.0)
        if payment.status == "COMPLETED":
            captured_at = None
            if payment.paypal_order:
                captured_at = as_utc(payment.paypal_order.captured_at)
            effective_at = captured_at or as_utc(payment.created_at)
            if effective_at is None or effective_at > now:
                continue
            for period, start in starts.items():
                if effective_at >= start:
                    usage[period] += amount
            continue

        expiry = as_utc(payment.limit_reservation_expires_at)
        if payment.status in RESERVABLE_STATUSES and expiry and expiry > now:
            # A live reservation consumes capacity in each current period even
            # if the request was originally analyzed before a period boundary.
            for period in usage:
                usage[period] += amount
            reserved_amount += amount

    usage["reserved_amount"] = reserved_amount
    usage["currency"] = LIMIT_CURRENCY
    return usage


def check_spending_limits(
    db: Session,
    *,
    amount: float,
    currency: str,
    policy: SpendingLimitSettings | None = None,
    now: datetime | None = None,
    exclude_payment_id: int | None = None,
) -> tuple[list[str], dict]:
    policy = policy or get_or_create_settings(db)
    now = as_utc(now or utc_now())
    assert now is not None
    usage = calculate_usage(
        db,
        policy,
        now=now,
        exclude_payment_id=exclude_payment_id,
    )
    violations: list[str] = []

    normalized_currency = (currency or "").upper().strip()
    if normalized_currency != LIMIT_CURRENCY:
        return [
            f"Spending limits are configured in {LIMIT_CURRENCY}; payments in "
            f"{normalized_currency or 'an unknown currency'} cannot proceed until "
            "currency-specific limits or reliable currency conversion are configured."
        ], usage

    per_transaction = policy.per_transaction_limit
    if per_transaction is not None and amount > float(per_transaction):
        violations.append(
            f"Per-transaction limit exceeded: this payment is "
            f"{LIMIT_CURRENCY} {amount:,.2f}, above the "
            f"{LIMIT_CURRENCY} {float(per_transaction):,.2f} cap."
        )

    period_config = (
        ("daily", "Daily", policy.daily_limit),
        ("weekly", "Weekly", policy.weekly_limit),
        ("monthly", "Monthly", policy.monthly_limit),
    )
    for key, label, limit in period_config:
        if limit is None:
            continue
        used = float(usage[key])
        projected = used + float(amount)
        if projected > float(limit) + 1e-9:
            violations.append(
                f"{label} spending limit exceeded: "
                f"{LIMIT_CURRENCY} {used:,.2f} is already spent or reserved; "
                f"this payment would bring the total to {LIMIT_CURRENCY} "
                f"{projected:,.2f}, above the {LIMIT_CURRENCY} {float(limit):,.2f} cap."
            )

    usage["projected_daily"] = float(usage["daily"]) + float(amount)
    usage["projected_weekly"] = float(usage["weekly"]) + float(amount)
    usage["projected_monthly"] = float(usage["monthly"]) + float(amount)
    return violations, usage


def apply_spending_policy(
    db: Session,
    intent: PaymentIntent,
    risk: RiskResult,
    *,
    now: datetime | None = None,
) -> tuple[RiskResult, list[str]]:
    policy = get_or_create_settings(db)
    violations, _ = check_spending_limits(
        db,
        amount=float(intent.amount),
        currency=intent.currency,
        policy=policy,
        now=now,
    )
    if not violations:
        return risk, []

    reasons = list(risk.reasons)
    for violation in violations:
        if violation not in reasons:
            reasons.append(violation)
    blocked = risk.model_copy(update={
        "risk_score": 100,
        "decision": "BLOCK",
        "reasons": reasons,
    })
    return blocked, violations


def payment_limit_violations(
    db: Session,
    payment: PaymentRequest,
    *,
    now: datetime | None = None,
) -> list[str]:
    policy = get_or_create_settings(db)
    violations, _ = check_spending_limits(
        db,
        amount=float(payment.amount),
        currency=payment.currency,
        policy=policy,
        now=now,
        exclude_payment_id=payment.id,
    )
    return violations
