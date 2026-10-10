from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import SpendingLimitSettings
from app.schemas.payment import (
    SpendingLimitsSettingsResponse,
    SpendingLimitsSummaryResponse,
    SpendingLimitsUpdate,
)
from app.services.spending_limits import calculate_usage, get_or_create_settings

router = APIRouter(prefix="/api/limits", tags=["spending-limits"])


def _settings_response(policy: SpendingLimitSettings) -> SpendingLimitsSettingsResponse:
    return SpendingLimitsSettingsResponse(
        daily_limit=policy.daily_limit,
        weekly_limit=policy.weekly_limit,
        monthly_limit=policy.monthly_limit,
        per_transaction_limit=policy.per_transaction_limit,
        timezone=policy.timezone,
        currency="USD",
    )


@router.get("/settings", response_model=SpendingLimitsSettingsResponse)
def read_spending_limit_settings(db: Session = Depends(get_db)):
    policy = get_or_create_settings(db)
    db.commit()
    return _settings_response(policy)


@router.put("/settings", response_model=SpendingLimitsSettingsResponse)
def update_spending_limit_settings(
    payload: SpendingLimitsUpdate,
    db: Session = Depends(get_db),
):
    policy = get_or_create_settings(db)
    policy.daily_limit = payload.daily_limit
    policy.weekly_limit = payload.weekly_limit
    policy.monthly_limit = payload.monthly_limit
    policy.per_transaction_limit = payload.per_transaction_limit
    policy.timezone = payload.timezone
    db.commit()
    db.refresh(policy)
    return _settings_response(policy)


@router.get("/summary", response_model=SpendingLimitsSummaryResponse)
def spending_limit_summary(db: Session = Depends(get_db)):
    policy = get_or_create_settings(db)
    usage = calculate_usage(db, policy)

    def remaining(limit, used):
        return None if limit is None else max(0.0, float(limit) - float(used))

    db.commit()
    return SpendingLimitsSummaryResponse(
        currency="USD",
        timezone=policy.timezone,
        daily_limit=policy.daily_limit,
        weekly_limit=policy.weekly_limit,
        monthly_limit=policy.monthly_limit,
        per_transaction_limit=policy.per_transaction_limit,
        daily_used=usage["daily"],
        weekly_used=usage["weekly"],
        monthly_used=usage["monthly"],
        active_reserved=usage["reserved_amount"],
        daily_remaining=remaining(policy.daily_limit, usage["daily"]),
        weekly_remaining=remaining(policy.weekly_limit, usage["weekly"]),
        monthly_remaining=remaining(policy.monthly_limit, usage["monthly"]),
    )
