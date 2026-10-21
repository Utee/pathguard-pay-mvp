from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.core.security import require_roles
from app.db import get_db
from app.models import PaymentRequest, UserAccount

router = APIRouter(prefix="/api/admin", tags=["administration"])


class UserUpdate(BaseModel):
    is_active: bool | None = None
    role: str | None = Field(default=None, pattern="^(customer|reviewer|admin)$")


def _user_data(user: UserAccount, payment_count: int = 0) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "payment_count": payment_count,
    }


@router.get("/overview")
def overview(
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin")),
):
    users_total = db.query(func.count(UserAccount.id)).scalar() or 0
    active_users = db.query(func.count(UserAccount.id)).filter(UserAccount.is_active.is_(True)).scalar() or 0
    payments_total = db.query(func.count(PaymentRequest.id)).scalar() or 0
    completed = db.query(func.count(PaymentRequest.id)).filter(PaymentRequest.status == "COMPLETED").scalar() or 0
    blocked = db.query(func.count(PaymentRequest.id)).filter(PaymentRequest.status == "BLOCK").scalar() or 0
    pending = db.query(func.count(PaymentRequest.id)).filter(
        PaymentRequest.status.in_(["REVIEW_PENDING", "PAYPAL_PENDING_APPROVAL", "PAYPAL_PENDING_CAPTURE"])
    ).scalar() or 0
    total_amount = db.query(func.coalesce(func.sum(PaymentRequest.amount), 0.0)).filter(
        PaymentRequest.status == "COMPLETED"
    ).scalar() or 0.0
    return {
        "users_total": users_total,
        "active_users": active_users,
        "payments_total": payments_total,
        "completed_payments": completed,
        "blocked_payments": blocked,
        "pending_payments": pending,
        "completed_payment_volume": float(total_amount),
    }


@router.get("/users")
def list_users(
    q: str | None = Query(default=None, max_length=255),
    role: str | None = Query(default=None, pattern="^(customer|reviewer|admin)$"),
    active: bool | None = None,
    limit: int = Query(default=100, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin")),
):
    query = db.query(UserAccount)
    if q:
        search = f"%{q.strip()}%"
        query = query.filter(or_(UserAccount.email.ilike(search), UserAccount.display_name.ilike(search)))
    if role:
        query = query.filter(UserAccount.role == role)
    if active is not None:
        query = query.filter(UserAccount.is_active.is_(active))

    total = query.count()
    users = query.order_by(UserAccount.created_at.desc()).offset(offset).limit(limit).all()
    user_ids = [user.id for user in users]
    counts = {}
    if user_ids:
        rows = db.query(PaymentRequest.user_id, func.count(PaymentRequest.id)).filter(
            PaymentRequest.user_id.in_(user_ids)
        ).group_by(PaymentRequest.user_id).all()
        counts = {user_id: count for user_id, count in rows}
    return {
        "items": [_user_data(user, counts.get(user.id, 0)) for user in users],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    actor: UserAccount = Depends(require_roles("admin")),
):
    target = db.get(UserAccount, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    if payload.is_active is None and payload.role is None:
        raise HTTPException(status_code=400, detail="Provide a role or account status change.")
    if target.id == actor.id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")
    if target.id == actor.id and payload.role is not None and payload.role != "admin":
        raise HTTPException(status_code=400, detail="You cannot remove your own administrator role.")

    will_remove_admin = target.role == "admin" and (
        payload.role is not None and payload.role != "admin"
        or payload.is_active is False
    )
    if will_remove_admin:
        active_admins = db.query(func.count(UserAccount.id)).filter(
            UserAccount.role == "admin",
            UserAccount.is_active.is_(True),
        ).scalar() or 0
        if target.is_active and active_admins <= 1:
            raise HTTPException(status_code=409, detail="The last active administrator cannot be deactivated or demoted.")

    if payload.role is not None:
        target.role = payload.role
    if payload.is_active is not None:
        target.is_active = payload.is_active
    db.commit()
    db.refresh(target)
    payment_count = db.query(func.count(PaymentRequest.id)).filter(PaymentRequest.user_id == target.id).scalar() or 0
    return _user_data(target, payment_count)


@router.get("/payments")
def list_payments(
    q: str | None = Query(default=None, max_length=255),
    status_filter: str | None = Query(default=None, alias="status", max_length=40),
    limit: int = Query(default=100, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin")),
):
    query = db.query(PaymentRequest).options(
        joinedload(PaymentRequest.user),
        joinedload(PaymentRequest.risk),
    )
    if q:
        search = f"%{q.strip()}%"
        query = query.join(UserAccount, PaymentRequest.user_id == UserAccount.id, isouter=True).filter(
            or_(
                PaymentRequest.recipient_name.ilike(search),
                PaymentRequest.purpose.ilike(search),
                UserAccount.email.ilike(search),
                PaymentRequest.status.ilike(search),
            )
        )
    if status_filter:
        query = query.filter(PaymentRequest.status == status_filter)
    total = query.count()
    payments = query.order_by(PaymentRequest.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "items": [
            {
                "id": payment.id,
                "user_id": payment.user_id,
                "user_email": payment.user.email if payment.user else "Unassigned account",
                "recipient": payment.recipient_name,
                "amount": float(payment.amount),
                "currency": payment.currency,
                "purpose": payment.purpose,
                "status": payment.status,
                "risk_score": payment.risk.risk_score if payment.risk else None,
                "risk_decision": payment.risk.decision if payment.risk else None,
                "created_at": payment.created_at,
            }
            for payment in payments
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
