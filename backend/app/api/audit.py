"""操作日志与导出（F-10）。"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.audit import client_ip, log_event
from app.core.csv_safe import csv_row
from app.core.timefmt import fmt as time_fmt
from app.core.rbac import audit_viewer
from app.db import get_db
from app.models import AuditDomain, AuditLog, User
from app.schemas import AuditLogOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs", response_model=list[AuditLogOut])
def list_logs(
    actor_id: int | None = Query(None),
    actor: str | None = Query(None),      # 按操作人姓名模糊查询（F-10「按人员」）
    target: str | None = Query(None),     # 按目标模糊查询：资料包编号/订单号/文件名（F-10「按资料包」）
    domain: str | None = Query(None),
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),   # ge=1：负数会让 MySQL 的 LIMIT -n 语法报错 500
    db: Session = Depends(get_db),
    _: User = Depends(audit_viewer),
):
    q = db.query(AuditLog)
    if actor_id:
        q = q.filter(AuditLog.actor_id == actor_id)
    if actor:
        q = q.filter(AuditLog.actor_name.contains(actor))
    if target:
        q = q.filter(AuditLog.target.contains(target))
    if domain:
        q = q.filter(AuditLog.event_domain == domain)
    if start:
        q = q.filter(AuditLog.created_at >= start)
    if end:
        # 纯日期视为当日整天（含当天 23:59:59）
        q = q.filter(AuditLog.created_at <= (end + " 23:59:59" if len(end) == 10 else end))
    return q.order_by(AuditLog.created_at.desc()).limit(limit).all()


@router.get("/export")
def export_logs(
    request: Request,
    domain: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(audit_viewer),
):
    q = db.query(AuditLog)
    if domain:
        q = q.filter(AuditLog.event_domain == domain)
    rows = q.order_by(AuditLog.created_at.desc()).limit(5000).all()
    header = ["时间（站点时区）", "域", "动作", "操作人", "角色", "IP", "目标", "说明"]
    lines = [",".join(header)]
    for r in rows:
        lines.append(csv_row([
            time_fmt(r.created_at),   # 站点时区 + 显式偏移，导出的证据必须自解释
            r.event_domain, r.action, r.actor_name, r.actor_role, r.ip, r.target, r.detail,
        ]))
    csv = "\n".join(lines)
    log_event(db, AuditDomain.EXPORT, "audit_csv", actor=user, ip=client_ip(request))
    return Response(
        content="\ufeff" + csv,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
    )
