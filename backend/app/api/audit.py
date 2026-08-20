"""操作日志与导出（F-10）。"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.audit import client_ip, log_event
from app.core.rbac import coo_or_admin, get_current_user
from app.db import get_db
from app.models import AuditDomain, AuditLog, User
from app.schemas import AuditLogOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs", response_model=list[AuditLogOut])
def list_logs(
    actor_id: int | None = Query(None),
    domain: str | None = Query(None),
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(AuditLog)
    if actor_id:
        q = q.filter(AuditLog.actor_id == actor_id)
    if domain:
        q = q.filter(AuditLog.event_domain == domain)
    if start:
        q = q.filter(AuditLog.created_at >= start)
    if end:
        q = q.filter(AuditLog.created_at <= end)
    return q.order_by(AuditLog.created_at.desc()).limit(limit).all()


@router.get("/export")
def export_logs(
    domain: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(coo_or_admin),
):
    q = db.query(AuditLog)
    if domain:
        q = q.filter(AuditLog.event_domain == domain)
    rows = q.order_by(AuditLog.created_at.desc()).limit(5000).all()
    header = ["时间", "域", "动作", "操作人", "角色", "IP", "目标", "说明"]
    lines = [",".join(header)]
    for r in rows:
        line = [
            r.created_at.isoformat() if r.created_at else "",
            r.event_domain, r.action, r.actor_name, r.actor_role, r.ip, r.target, r.detail,
        ]
        lines.append(",".join(f'"{c.replace(chr(34), chr(34)*2)}"' for c in line))
    csv = "\n".join(lines)
    log_event(db, AuditDomain.EXPORT, "audit_csv", actor=user, ip=client_ip(None))
    return Response(
        content="\ufeff" + csv,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
    )
