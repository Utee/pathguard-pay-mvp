from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db import get_db
from app.models import UserAccount
from app.services.incident_intelligence import build_notifications, build_overview, detect_incidents, summarize_intelligence

router = APIRouter(prefix="/api/intelligence", tags=["payment-intelligence"])


@router.get("/overview")
def intelligence_overview(
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    return build_overview(db, current_user)


@router.get("/incidents")
def intelligence_incidents(
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    return {
        "scope": "organization" if current_user.role in {"reviewer", "admin"} else "account",
        "window_hours": 24,
        "history_window_days": 7,
        "incidents": detect_incidents(db, current_user),
    }


@router.get("/summary")
def intelligence_summary(
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    return summarize_intelligence(db, current_user)


@router.get("/notifications")
def intelligence_notifications(
    limit: int = 15,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    notifications = build_notifications(db, current_user, limit=limit)
    return {
        "scope": "organization" if current_user.role in {"reviewer", "admin"} else "account",
        "history_window_days": 7,
        "notifications": notifications,
    }
