"""审计日志写入辅助。"""
from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog


def client_ip(request: Request | None) -> str:
    if not request:
        return ""
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


def log_event(
    db: Session,
    domain: str,
    action: str,
    *,
    actor=None,
    ip: str = "",
    target: str = "",
    detail: str = "",
):
    """domain.action 形式记录审计事件。"""
    rec = AuditLog(
        event_domain=domain,
        action=action,
        actor_id=actor.id if actor else None,
        actor_role=actor.role if actor else "",
        actor_name=actor.display_name if actor else "",
        ip=ip,
        target=target,
        detail=detail,
    )
    db.add(rec)
    db.commit()
