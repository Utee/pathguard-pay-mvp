import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AuditEvent, PaymentRequest, UserAccount

STAFF_ROLES = {"reviewer", "admin"}
WINDOW_HOURS = 24
HISTORY_DAYS = 7

EVENT_CATEGORIES = {
    "PAYPAL_ERROR": "paypal_errors",
    "PAYPAL_ORDER_STALE": "stale_paypal_orders",
    "SPENDING_LIMIT_BLOCKED": "limit_blocks",
}
INCIDENT_RULES = {
    "paypal_errors": {
        "title": "Repeated PayPal processing errors",
        "severity": "high",
        "threshold": 2,
        "summary": "Several PayPal operations failed recently. Review provider response codes and Sandbox or API availability before retrying payments.",
        "action": "Inspect recent PayPal error audit entries and verify the configured API environment and credentials.",
    },
    "stale_paypal_orders": {
        "title": "PayPal checkouts repeatedly becoming stale",
        "severity": "medium",
        "threshold": 2,
        "summary": "Multiple stored PayPal orders were no longer recognized by the provider. This can interrupt checkout and require fresh approval links.",
        "action": "Review stale-order timestamps and check whether old Sandbox orders or environment changes explain the pattern.",
    },
    "limit_blocks": {
        "title": "Spike in spending-limit blocks",
        "severity": "medium",
        "threshold": 3,
        "summary": "Several payment attempts hit a configured spending cap in the last 24 hours. This is a policy signal, not evidence of a system failure.",
        "action": "Review the affected accounts' budget settings and pending reservations; do not relax limits automatically.",
    },
    "risk_blocks": {
        "title": "Unusual volume of risk-based blocks",
        "severity": "high",
        "threshold": 5,
        "summary": "The risk engine blocked an unusually high number of payment requests in the last 24 hours. Inspect the recorded reasons before changing risk policy.",
        "action": "Compare the recorded risk reasons and recipient patterns. Keep deterministic hard blocks in place during investigation.",
    },
}


def _scope_statement(statement, user: UserAccount):
    if user.role not in STAFF_ROLES:
        statement = statement.where(PaymentRequest.user_id == user.id)
    return statement


def _event_query(db: Session, user: UserAccount, since: datetime):
    statement = (
        select(AuditEvent, PaymentRequest.user_id)
        .join(PaymentRequest, PaymentRequest.id == AuditEvent.payment_request_id)
        .where(AuditEvent.created_at >= since)
        .order_by(AuditEvent.created_at.desc())
    )
    if user.role not in STAFF_ROLES:
        statement = statement.where(PaymentRequest.user_id == user.id)
    return db.execute(statement).all()


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _event_time(value: datetime | None) -> str | None:
    normalized = _as_utc(value)
    return normalized.isoformat() if normalized else None


def detect_incidents(db: Session, user: UserAccount, *, now: datetime | None = None) -> list[dict]:
    now = _as_utc(now or datetime.now(timezone.utc))
    assert now is not None
    start = now - timedelta(days=HISTORY_DAYS)
    recent_start = now - timedelta(hours=WINDOW_HOURS)
    events = _event_query(db, user, start)

    recent_counts = defaultdict(int)
    historical_counts = defaultdict(int)
    latest_times = {}
    first_seen_times = {}
    affected_payments = defaultdict(set)

    for event, _owner_id in events:
        category = EVENT_CATEGORIES.get(event.event_type)
        if event.event_type == "RISK_ASSESSED":
            details = event.metadata if isinstance(event.metadata, dict) else {}
            if details.get("decision") == "BLOCK":
                category = "risk_blocks"
        if category is None:
            continue

        event_time = _as_utc(event.created_at)
        if event_time is None:
            continue
        if event_time >= recent_start:
            recent_counts[category] += 1
            affected_payments[category].add(event.payment_request_id)
            if category not in latest_times or event_time > latest_times[category]:
                latest_times[category] = event_time
            if category not in first_seen_times or event_time < first_seen_times[category]:
                first_seen_times[category] = event_time
        else:
            historical_counts[category] += 1

    incidents = []
    for category, rule in INCIDENT_RULES.items():
        recent = recent_counts[category]
        previous = historical_counts[category]
        threshold = rule["threshold"]
        prior_daily_average = previous / max(HISTORY_DAYS - 1, 1)
        is_burst = recent >= threshold
        is_emerging = recent >= 2 and previous >= 3 and recent > prior_daily_average * 2

        if not (is_burst or is_emerging):
            continue

        severity = rule["severity"]
        if is_emerging and severity == "medium":
            severity = "high"
        incidents.append({
            "id": category,
            "category": category,
            "title": rule["title"],
            "severity": severity,
            "status": "observed",
            "event_count_24h": recent,
            "event_count_previous_6d": previous,
            "affected_payments": len(affected_payments[category]),
            "first_seen": _event_time(first_seen_times.get(category)),
            "last_seen": _event_time(latest_times.get(category)),
            "summary": rule["summary"],
            "recommended_action": rule["action"],
            "signal": "burst" if is_burst else "emerging",
        })

    priority = {"high": 0, "medium": 1, "low": 2}
    incidents.sort(key=lambda item: (priority.get(item["severity"], 9), -item["event_count_24h"]))
    return incidents


def build_overview(db: Session, user: UserAccount) -> dict:
    statement = select(
        PaymentRequest.status,
        func.count(PaymentRequest.id),
        func.sum(
            case(
                (PaymentRequest.status == "COMPLETED", PaymentRequest.amount),
                else_=0.0,
            )
        ),
    ).group_by(PaymentRequest.status)
    statement = _scope_statement(statement, user)
    rows = db.execute(statement).all()

    status_counts = {str(status): int(count) for status, count, _spent in rows}
    total_spend = sum(float(spent or 0.0) for _status, _count, spent in rows)
    completed = status_counts.get("COMPLETED", 0)
    failed = status_counts.get("PAYPAL_CAPTURE_ERROR", 0)
    cancelled = status_counts.get("CANCELLED", 0)
    terminal_attempts = completed + failed + cancelled
    success_rate = (completed / terminal_attempts * 100.0) if terminal_attempts else 0.0

    audit_statement = (
        select(AuditEvent.event_type, func.count(AuditEvent.id))
        .join(PaymentRequest, PaymentRequest.id == AuditEvent.payment_request_id)
        .group_by(AuditEvent.event_type)
    )
    if user.role not in STAFF_ROLES:
        audit_statement = audit_statement.where(PaymentRequest.user_id == user.id)
    audit_counts = {
        str(event_type): int(count)
        for event_type, count in db.execute(audit_statement).all()
    }

    incidents = detect_incidents(db, user)
    return {
        "scope": "organization" if user.role in STAFF_ROLES else "account",
        "total_payments": sum(status_counts.values()),
        "completed_payments": completed,
        "completed_spend_usd": round(total_spend, 2),
        "blocked_payments": status_counts.get("BLOCK", 0),
        "rejected_payments": status_counts.get("REVIEW_REJECTED", 0),
        "awaiting_review": status_counts.get("REVIEW_PENDING", 0),
        "paypal_errors": failed,
        "cancelled_payments": cancelled,
        "success_rate_percent": round(success_rate, 2),
        "spending_limit_blocks": audit_counts.get("SPENDING_LIMIT_BLOCKED", 0),
        "stale_paypal_orders": audit_counts.get("PAYPAL_ORDER_STALE", 0),
        "incident_count": len(incidents),
        "incident_window_hours": WINDOW_HOURS,
        "history_window_days": HISTORY_DAYS,
    }


def _rule_based_summary(overview: dict, incidents: list[dict]) -> str:
    if not overview["total_payments"]:
        return "There is no payment activity yet, so PathGuard has no transaction patterns to investigate."
    if not incidents:
        return (
            f"PathGuard recorded {overview['total_payments']} payment attempt(s), "
            f"including {overview['completed_payments']} completed payment(s) and "
            f"${overview['completed_spend_usd']:,.2f} in completed spend. "
            "No recurring incident pattern met the current 24-hour detection thresholds. "
            "This does not mean every payment is risk-free."
        )
    highest = incidents[0]
    return (
        f"{len(incidents)} recurring incident signal group(s) met the detection thresholds. "
        f"The highest-priority signal is '{highest['title']}' "
        f"({highest['event_count_24h']} event(s) in 24 hours). "
        f"Suggested next step: {highest['recommended_action']} "
        "These are heuristic signals, not confirmed root causes; keep deterministic risk "
        "checks and spending caps in control."
    )


def summarize_intelligence(db: Session, user: UserAccount) -> dict:
    overview = build_overview(db, user)
    incidents = detect_incidents(db, user)
    fallback = _rule_based_summary(overview, incidents)
    settings = get_settings()
    generated_at = datetime.now(timezone.utc).isoformat()

    result = {
        "scope": overview["scope"],
        "source": "rules",
        "summary": fallback,
        "priority_actions": [
            {
                "title": item["title"],
                "severity": item["severity"],
                "action": item["recommended_action"],
            }
            for item in incidents[:3]
        ],
        "generated_at": generated_at,
        "disclaimer": "This explanation is based on aggregate operational signals. It does not confirm root cause and never changes risk decisions or spending limits.",
    }

    api_key = settings.openrouter_api_key
    if not api_key:
        return result

    aggregate = {
        "metrics": {
            "total_payments": overview["total_payments"],
            "completed_payments": overview["completed_payments"],
            "completed_spend_usd": overview["completed_spend_usd"],
            "blocked_payments": overview["blocked_payments"],
            "rejected_payments": overview["rejected_payments"],
            "awaiting_review": overview["awaiting_review"],
            "paypal_errors": overview["paypal_errors"],
            "success_rate_percent": overview["success_rate_percent"],
        },
        "incident_signals": [
            {
                "title": item["title"],
                "severity": item["severity"],
                "count_24h": item["event_count_24h"],
                "count_previous_6d": item["event_count_previous_6d"],
                "summary": item["summary"],
                "recommended_action": item["recommended_action"],
                "signal": item["signal"],
            }
            for item in incidents[:5]
        ],
    }
    try:
        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-Title": "PathGuard Pay",
            },
            json={
                "model": settings.openrouter_model,
                "temperature": 0.2,
                "max_tokens": 220,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are an operational analyst for a payment safety system. "
                            "Summarize only the supplied aggregate metrics and incident signals "
                            "in plain language. Clearly separate observed signals from hypotheses. "
                            "Do not claim a confirmed root cause, do not invent data, and recommend "
                            "safe investigations. Never propose bypassing a risk block or spending cap. "
                            "Keep the response under 100 words."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(aggregate, separators=(",", ":")),
                    },
                ],
            },
            timeout=8.0,
        )
        response.raise_for_status()
        payload = response.json()
        summary = payload["choices"][0]["message"]["content"]
        if isinstance(summary, str) and summary.strip():
            result["summary"] = summary.strip()
            result["source"] = "openrouter"
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        result["provider_status"] = "unavailable"
    return result


NOTIFICATION_EVENT_TYPES = {
    "RISK_ASSESSED",
    "SPENDING_LIMIT_BLOCKED",
    "PAYPAL_ERROR",
    "PAYPAL_ORDER_STALE",
    "PAYMENT_COMPLETED",
    "PAYPAL_CHECKOUT_CANCELLED",
    "PAYPAL_ORDER_CREATED",
}


def build_notifications(
    db: Session,
    user: UserAccount,
    *,
    now: datetime | None = None,
    limit: int = 15,
) -> list[dict]:
    now = _as_utc(now or datetime.now(timezone.utc))
    assert now is not None
    since = now - timedelta(days=7)
    statement = (
        select(AuditEvent, PaymentRequest)
        .join(PaymentRequest, PaymentRequest.id == AuditEvent.payment_request_id)
        .where(
            AuditEvent.created_at >= since,
            AuditEvent.event_type.in_(NOTIFICATION_EVENT_TYPES),
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(max(50, min(limit * 5, 250)))
    )
    if user.role not in STAFF_ROLES:
        statement = statement.where(PaymentRequest.user_id == user.id)

    notifications = []
    for event, payment in db.execute(statement).all():
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        decision = str(metadata.get("decision", "")).upper()

        if event.event_type == "RISK_ASSESSED":
            if decision == "ALLOW":
                continue
            if decision == "BLOCK":
                title = "Payment blocked by risk checks"
                severity = "high"
                message = "The deterministic risk engine blocked this payment. Review its recorded risk reasons."
            elif decision == "REVIEW":
                title = "Payment queued for human review"
                severity = "medium"
                message = "The payment needs a staff decision before it can continue to PayPal."
            else:
                continue
        elif event.event_type == "SPENDING_LIMIT_BLOCKED":
            title = "Spending limit enforced"
            severity = "medium"
            message = "The payment was blocked because a configured spending cap would be exceeded."
        elif event.event_type == "PAYPAL_ERROR":
            title = "PayPal processing error"
            severity = "high"
            message = "PayPal processing reported an error. Check provider status before retrying."
        elif event.event_type == "PAYPAL_ORDER_STALE":
            title = "PayPal checkout needs refreshing"
            severity = "medium"
            message = "The saved PayPal order was not found; a fresh checkout may be required."
        elif event.event_type == "PAYMENT_COMPLETED":
            title = "Payment completed"
            severity = "low"
            message = "PathGuard recorded the payment as completed."
        elif event.event_type == "PAYPAL_CHECKOUT_CANCELLED":
            title = "PayPal checkout cancelled"
            severity = "low"
            message = "The checkout was cancelled and the local spending reservation was released."
        else:
            title = "PayPal checkout created"
            severity = "low"
            message = "A PayPal checkout order was created and is waiting for buyer approval."

        notifications.append({
            "id": event.id,
            "payment_id": payment.id,
            "event_type": event.event_type,
            "title": title,
            "severity": severity,
            "message": message,
            "recipient": payment.recipient_name,
            "amount": float(payment.amount),
            "currency": payment.currency,
            "created_at": _event_time(event.created_at),
        })
    return notifications[:max(1, min(limit, 50))]
