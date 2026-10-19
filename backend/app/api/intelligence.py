from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db import get_db
from app.models import UserAccount
from app.services.incident_intelligence import build_overview, detect_incidents

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
