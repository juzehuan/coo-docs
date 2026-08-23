"""操作日志与导出（F-10）。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import client_ip, log_event
from app.core.http_headers import content_disposition
from app.core.timefmt import fmt as time_fmt
from app.core.xlsx import XLSX_MEDIA_TYPE, build_xlsx
from app.core.rbac import audit_viewer
from app.db import get_db
from app.models import AuditDomain, AuditLog, User
from app.schemas import AuditLogList, AuditLogOut

router = APIRouter(prefix="/audit", tags=["audit"])


def _apply_filters(q, actor_id, actor, target, domain, start, end):
    """列表与导出共用同一套过滤：两边若各写一份，迟早会出现"导出的内容和屏幕上不一样"。"""
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
    return q


@router.get("/logs", response_model=AuditLogList)
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
    """按条件返回操作日志，并**同时返回命中总数**。

    此前只返回一页数据，界面拿到 1000 条就停住，用户无从得知"还有没有更多"——
    审计场景里这尤其危险：查不到记录与被截断看起来完全一样，而结论截然相反。
    """
    q = _apply_filters(db.query(AuditLog), actor_id, actor, target, domain, start, end)
    total = q.with_entities(func.count(AuditLog.id)).scalar() or 0
    items = q.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return {"total": total, "items": [AuditLogOut.model_validate(r) for r in items]}


# 单次导出行数上限。Excel 单表可容纳 104 万行，此处远低于该限制，
# 目的是防止一次导出把内存与响应时间拖垮；超限时**明确报错让用户缩小范围**，
# 绝不返回一个"看起来完整、实则被截断"的证据文件。
MAX_EXPORT_ROWS = 100000


@router.get("/export")
def export_logs(
    request: Request,
    actor_id: int | None = Query(None),
    actor: str | None = Query(None),
    target: str | None = Query(None),
    domain: str | None = Query(None),
    start: str | None = Query(None),
    end: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(audit_viewer),
):
    """按与列表**完全相同**的条件导出操作日志。

    此前导出只认 domain 且前端一个参数都不传：用户在界面上筛出十几条记录，
    点导出却拿到全部日志（实测界面 53 条 / 导出 2396 条），而这份文件是要
    作为佐证材料交出去的——与查询对不上的证据比没有证据更糟。
    """
    q = _apply_filters(db.query(AuditLog), actor_id, actor, target, domain, start, end)
    total = q.with_entities(func.count(AuditLog.id)).scalar() or 0
    if total > MAX_EXPORT_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"符合条件的记录有 {total} 条，超过单次导出上限 {MAX_EXPORT_ROWS} 条，请缩小时间范围后重试",
        )
    rows = q.order_by(AuditLog.created_at.desc()).all()
    header = ["时间（站点时区）", "域", "动作", "操作人", "角色", "IP", "目标", "说明"]
    data = [[
        time_fmt(r.created_at),   # 站点时区 + 显式偏移，导出的证据必须自解释
        r.event_domain, r.action, r.actor_name, r.actor_role, r.ip, r.target, r.detail,
    ] for r in rows]
    content = build_xlsx(header, data, sheet_title="操作日志")
    # 留痕记录导出了多少条、用了什么条件：事后要能回答"这份佐证材料是怎么来的"
    cond = ",".join(f"{k}={v}" for k, v in
                    (("actor", actor), ("target", target), ("domain", domain),
                     ("start", start), ("end", end)) if v)
    log_event(db, AuditDomain.EXPORT, "audit_xlsx", actor=user, ip=client_ip(request),
              detail=f"rows={len(rows)}" + (f",{cond}" if cond else ",无筛选条件"))
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": content_disposition("audit_logs.xlsx")},
    )
