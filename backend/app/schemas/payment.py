from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator


class AnalyzePaymentRequest(BaseModel):
    instruction: str = Field(min_length=3, max_length=2000)


class PaymentIntent(BaseModel):
    recipient_name: str = Field(min_length=1, max_length=120)
    amount: float = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    purpose: str | None = Field(default=None, max_length=500)


class RiskResult(BaseModel):
    risk_score: int
    decision: str
    reasons: list[str]
    amount_anomaly: bool = False
    new_recipient: bool = False
    instruction_mismatch: bool = False
    frequency_anomaly: bool = False


class AnalyzePaymentResponse(BaseModel):
    payment_id: int
    intent: PaymentIntent
    risk: RiskResult


class PayPalCreateResponse(BaseModel):
    payment_id: int
    paypal_order_id: str
    status: str
    approval_url: str | None = None


class PayPalCaptureResponse(BaseModel):
    payment_id: int
    paypal_order_id: str
    status: str
    capture_id: str | None = None


class RecipientHistoryResponse(BaseModel):
    recipient: str
    total_payments: int
    total_amount: float
    average_amount: float
    last_payment_at: datetime | None = None


class AuditEventResponse(BaseModel):
    id: int
    event_type: str
    actor: str | None
    message: str
    metadata: dict | None
    created_at: datetime


class SpendingLimitsUpdate(BaseModel):
    daily_limit: float | None = Field(default=1000.0, gt=0)
    weekly_limit: float | None = Field(default=10000.0, gt=0)
    monthly_limit: float | None = Field(default=10000.0, gt=0)
    per_transaction_limit: float | None = Field(default=None, gt=0)
    timezone: str = Field(default="Africa/Lagos", min_length=1, max_length=80)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Use a valid IANA timezone, for example Africa/Lagos or UTC.") from exc
        return value

    @model_validator(mode="after")
    def require_at_least_one_limit(self):
        if all(value is None for value in (
            self.daily_limit,
            self.weekly_limit,
            self.monthly_limit,
            self.per_transaction_limit,
        )):
            raise ValueError("At least one spending limit must remain enabled.")
        return self


class SpendingLimitsSettingsResponse(BaseModel):
    daily_limit: float | None
    weekly_limit: float | None
    monthly_limit: float | None
    per_transaction_limit: float | None
    timezone: str
    currency: str = "USD"


class SpendingLimitsSummaryResponse(BaseModel):
    currency: str
    timezone: str
    daily_limit: float | None
    weekly_limit: float | None
    monthly_limit: float | None
    per_transaction_limit: float | None
    daily_used: float
    weekly_used: float
    monthly_used: float
    active_reserved: float
    daily_remaining: float | None
    weekly_remaining: float | None
    monthly_remaining: float | None
