from pydantic import BaseModel, Field


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
