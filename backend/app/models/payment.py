from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class Recipient(Base):
    __tablename__ = "recipients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    name: Mapped[str] = mapped_column(
        String(120),
        unique=True,
        index=True,
    )

    total_payments: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    total_amount: Mapped[float] = mapped_column(
        Float,
        default=0.0,
    )

    last_payment_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )

    payments: Mapped[list["PaymentRequest"]] = relationship(
        back_populates="recipient",
    )


class PaymentRequest(Base):
    __tablename__ = "payment_requests"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    raw_instruction: Mapped[str] = mapped_column(
        Text,
    )

    recipient_name: Mapped[str] = mapped_column(
        String(120),
        index=True,
    )

    recipient_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipients.id"),
        nullable=True,
    )

    amount: Mapped[float] = mapped_column(
        Float,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        default="USD",
    )

    purpose: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # ANALYZED
    # REVIEW
    # APPROVED
    # REJECTED
    # BLOCK
    # PAYPAL_PENDING_APPROVAL
    # PAYPAL_PENDING_CAPTURE
    # COMPLETED
    # CANCELLED
    # PAYPAL_CAPTURE_ERROR
    status: Mapped[str] = mapped_column(
        String(40),
        default="ANALYZED",
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        index=True,
    )

    recipient: Mapped["Recipient | None"] = relationship(
        back_populates="payments",
    )

    risk: Mapped["RiskAssessment | None"] = relationship(
        back_populates="payment_request", uselist=False,
        cascade="all, delete-orphan",
    )

    paypal_order: Mapped["PayPalOrder | None"] = relationship(
        back_populates="payment_request", uselist=False,
        cascade="all, delete-orphan",
    )

    review: Mapped["PaymentReview | None"] = relationship(
        back_populates="payment_request",
        uselist=False,
        cascade="all, delete-orphan",
    )

    audit_events: Mapped[list["AuditEvent"]] = relationship(
        back_populates="payment_request",
        cascade="all, delete-orphan",
        order_by="AuditEvent.created_at",
    )


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    payment_request_id: Mapped[int] = mapped_column(
        ForeignKey("payment_requests.id"),
        unique=True,
    )

    risk_score: Mapped[int] = mapped_column(
        Integer,
    )

    decision: Mapped[str] = mapped_column(
        String(20),
    )

    amount_anomaly: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    new_recipient: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    instruction_mismatch: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    frequency_anomaly: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    reasons: Mapped[list] = mapped_column(
        JSON,
        default=list,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )

    payment_request: Mapped[PaymentRequest] = relationship(
        back_populates="risk",
    )


class PaymentReview(Base):
    __tablename__ = "payment_reviews"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    payment_request_id: Mapped[int] = mapped_column(
        ForeignKey("payment_requests.id"),
        unique=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="PENDING",
        index=True,
    )

    reviewer: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )

    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    payment_request: Mapped[PaymentRequest] = relationship(
        back_populates="review",
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    payment_request_id: Mapped[int] = mapped_column(
        ForeignKey("payment_requests.id"),
        index=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(60),
        index=True,
    )

    actor: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )

    message: Mapped[str] = mapped_column(
        Text,
    )

    metadata: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        index=True,
    )

    payment_request: Mapped[PaymentRequest] = relationship(
        back_populates="audit_events",
    )


class PayPalOrder(Base):
    __tablename__ = "paypal_orders"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    payment_request: Mapped[PaymentRequest] = relationship(back_populates="paypal_order")


class ReviewEvent(Base):
    __tablename__ = "review_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_request_id: Mapped[int] = mapped_column(
        ForeignKey("payment_requests.id"), index=True
    )
    action: Mapped[str] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    reviewer: Mapped[str] = mapped_column(String(120), default="local-reviewer")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
