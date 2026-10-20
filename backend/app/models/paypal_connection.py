from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PayPalWalletConnection(Base):
    __tablename__ = "paypal_wallet_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), unique=True, index=True)
    paypal_customer_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payment_token_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    pending_setup_token_id: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    pending_state: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    payer_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
