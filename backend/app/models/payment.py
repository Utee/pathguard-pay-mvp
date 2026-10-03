from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class PaymentRequest(Base):
    __tablename__ = "payment_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    raw_instruction: Mapped[str] = mapped_column(Text)
    recipient_name: Mapped[str] = mapped_column(String(120))
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    purpose: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="ANALYZED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    risk: Mapped["RiskAssessment | None"] = relationship(
        back_populates="payment_request",
        uselist=False,
        cascade="all, delete-orphan",
    )
    paypal_order: Mapped["PayPalOrder | None"] = relationship(
        back_populates="payment_request",
        uselist=False,
        cascade="all, delete-orphan",
    )


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_request_id: Mapped[int] = mapped_column(
        ForeignKey("payment_requests.id"), unique=True
    )
    risk_score: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(20))
    amount_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    new_recipient: Mapped[bool] = mapped_column(Boolean, default=False)
    instruction_mismatch: Mapped[bool] = mapped_column(Boolean, default=False)
    frequency_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    payment_request: Mapped[PaymentRequest] = relationship(back_populates="risk")


class PayPalOrder(Base):
    __tablename__ = "paypal_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_request_id: Mapped[int] = mapped_column(
        ForeignKey("payment_requests.id"), unique=True
    )
    paypal_order_id: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(40))
    approval_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    capture_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    payment_request: Mapped[PaymentRequest] = relationship(back_populates="paypal_order")
