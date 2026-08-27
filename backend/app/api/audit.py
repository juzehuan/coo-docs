"""操作日志与导出（F-10）。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import client_ip, log_event
from app.core.http_headers import content_disposition
from app.core.i18n import t
from app.core.timefmt import fmt as time_fmt
from app.core.xlsx import XLSX_MEDIA_TYPE, build_xlsx
from app.core.rbac import audit_viewer
from app.db import get_db
from app.models import AuditDomain, AuditLog, User
from app.schemas import AuditLogList, AuditLogOut

router = APIRouter(prefix="/audit", tags=["audit"])


def _parse_bound(value: str, field: str, end_of_day: bool = False) -> datetime:
    """把查询串解析为时间边界；非法格式返回 400 而不是让 MySQL 去报错。

    原实现把 start/end 原样塞进 SQL 比较，MySQL 遇到 `abc` 这类值抛
    OperationalError，被全局处理器翻译成 **503「数据库暂时不可用，请稍后重试」**。
    这是两重误导：用户的输入错误被说成服务故障，只会让他反复重试甚至找运维；
    而日志与监控里会凭空出现"数据库不可用"，任何人打一个错日期就能伪造一次
    基础设施告警。输入错误必须回 400 并说清楚哪里错了。
    """
    v = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(v, fmt)
        except ValueError:
            continue
        if fmt == "%Y-%m-%d" and end_of_day:
            # 纯日期视为当日整天（含当天 23:59:59）
            return dt.replace(hour=23, minute=59, second=59)
        return dt
    raise HTTPException(status_code=400,
                        detail=f"{field} 格式不正确，应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS")


def _apply_filters(q, actor_id, actor, target, domain, start, end):
    """列表与导出共用同一套过滤：两边若各写一份，迟早会出现"导出的内容和屏幕上不一样"。"""
    if actor_id:
        q = q.filter(AuditLog.actor_id == actor_id)
    # autoescape：转义用户输入里的 % 与 _，否则它们会被当作 LIKE 通配符。
    # 实测未转义时搜 `%` 命中全部 2445 条、搜 `_` 命中 1549 条，
    # 而 `COO_01` 与 `COO-01` 返回同样的结果——审计检索是合规追溯的主要手段，
    # 搜索悄悄放大结果集会让"我查过了，就这些"这句话失去意义。
    if actor:
        q = q.filter(AuditLog.actor_name.contains(actor, autoescape=True))
    if target:
        q = q.filter(AuditLog.target.contains(target, autoescape=True))
    if domain:
        q = q.filter(AuditLog.event_domain == domain)
    if start:
        q = q.filter(AuditLog.created_at >= _parse_bound(start, "start"))
    if end:
        q = q.filter(AuditLog.created_at <= _parse_bound(end, "end", end_of_day=True))
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
    # 加唯一兜底列：这里虽无 offset，但 limit 截断处若有同秒并列，
    # **同一条查询重复执行可能返回不同的一批记录**——审计检索是合规追溯的主要手段，
    # "我查过了，就这些"必须可复现。
    items = q.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).all()
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
    rows = q.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).all()
    header = [t("time_site_tz"), t("domain"), t("action"), t("actor"),
              t("role"), t("ip"), t("target"), t("detail")]
    data = [[
        time_fmt(r.created_at),   # 站点时区 + 显式偏移，导出的证据必须自解释
        r.event_domain, r.action, r.actor_name, r.actor_role, r.ip, r.target, r.detail,
    ] for r in rows]
    content = build_xlsx(header, data, sheet_title=t("sheet_audit"))
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
