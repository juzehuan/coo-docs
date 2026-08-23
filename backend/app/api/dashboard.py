"""工作概览看板（F-03）。"""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants import VersionStatus
from app.core.audit import client_ip, log_event
from app.core.csv_safe import csv_row
from app.core.overdue import is_overdue
from app.core.i18n import local_name
from app.core.rbac import can_view_package, export_viewer, get_current_user
from app.db import get_db
from app.models import Attachment, AuditDomain, Factory, Order, OrderPackage, Package, PackageVersion, User
from app.schemas import DashboardOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _factory_ids(user: User, db: Session) -> list[int]:
    """当前账号可见工厂 ID；admin 可见全部工厂。

    不按 status 过滤：停用工厂只应阻止新建订单。若在此过滤，
    停用当天工作台的完成率/统计与归档导出会静默少掉该厂全部数据，
    而报表看不出任何缺失迹象。
    """
    if user.role == "admin":
        return [f.id for f in db.query(Factory).all()]
    return [f.id for f in user.factories]


@router.get("", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    fids = _factory_ids(user, db)
    pkgs = db.query(Package).filter(Package.status == "active").all()
    versions = db.query(PackageVersion).all()
    # 构建 资料包 -> 最新版本状态
    latest = {}
    for v in versions:
        # 用 id 比较：created_at 秒级精度，同秒创建的版本比不出先后
        if v.package_id not in latest or v.id > latest[v.package_id].id:
            latest[v.package_id] = v

    # 仅统计可见资料包的完成度，避免向提交人泄露非本人资料包信息
    visible_pkgs = [p for p in pkgs if can_view_package(user, p)]
    released_count = sum(1 for p in visible_pkgs if p.id in latest and latest[p.id].status == VersionStatus.RELEASED)
    completion = round(released_count / len(visible_pkgs) * 100, 1) if visible_pkgs else 0.0

    # 附件总数：订单附件按工厂隔离，版本附件按资料包可见性过滤。
    # 二者都必须过滤 —— 看板的完成度/已放行/进度列表都按 can_view_package 收敛，
    # 若附件计数不收敛，看不到任何资料包的提交人仍会看到全部版本附件计入总数：
    # 既能借此推断无权查看的资料包上有多少活动，这个数字对他也毫无意义。
    # func.count 聚合，避免 Query.count() 的全字段子查询在万级附件下撑爆排序缓冲
    order_att = (
        db.query(func.count(Attachment.id))
        .join(OrderPackage, Attachment.order_package_id == OrderPackage.id)
        .join(Order, OrderPackage.order_id == Order.id)
        .filter(Order.factory_id.in_(fids))
        .scalar() or 0
    )
    visible_pkg_ids = [p.id for p in visible_pkgs]
    ver_att = (
        db.query(func.count(Attachment.id))
        .join(PackageVersion, Attachment.version_id == PackageVersion.id)
        .filter(PackageVersion.package_id.in_(visible_pkg_ids))
        .scalar() or 0
    ) if visible_pkg_ids else 0
    total_attachments = order_att + ver_att

    # 待我处理：提交人看自己被退回/撤回；部门审核人看待部门审核；COO 看待终审
    # （同时统计订单资料包实例流程线上的待办）
    pending_mine = 0
    for p in pkgs:
        v = latest.get(p.id)
        if not v:
            continue
        if user.role == "submitter" and p.owner_user_id == user.id \
                and v.status in (VersionStatus.REJECTED, VersionStatus.WITHDRAWN):
            pending_mine += 1
        elif user.role == "dept_reviewer" and p.dept_id == user.dept_id and v.status == VersionStatus.PENDING_DEPT:
            pending_mine += 1
        elif user.role in ("coo_reviewer", "admin") and v.status == VersionStatus.PENDING_COO:
            pending_mine += 1
    ops = (
        db.query(OrderPackage)
        .join(Order, OrderPackage.order_id == Order.id)
        .filter(Order.factory_id.in_(fids))
        .all()
    )
    for op in ops:
        pkg = db.get(Package, op.package_id)
        if not pkg:
            continue
        if user.role == "submitter":
            if (op.owner_user_id == user.id or op.submitted_by == user.id) \
                    and op.status in (VersionStatus.REJECTED, VersionStatus.WITHDRAWN):
                pending_mine += 1
        elif user.role == "dept_reviewer":
            if pkg.dept_id == user.dept_id and op.status == VersionStatus.PENDING_DEPT:
                pending_mine += 1
        elif user.role in ("coo_reviewer", "admin"):
            if op.status == VersionStatus.PENDING_COO:
                pending_mine += 1

    overdue = 0
    need_attention = []
    progress = []
    # 进度与需关注列表按可见性过滤，避免向提交人泄露非本人资料包信息
    for p in visible_pkgs:
        v = latest.get(p.id)
        st = v.status if v else "none"
        att_n = len(v.attachments) if v else 0
        # 超期 = 截止日期已过且未放行（F-03）
        od = is_overdue(p.due_date, st)
        if od:
            overdue += 1
        # 进度：已放行=100，待终审=80，待部门=50，退回/撤回=30，草稿=10，无=0
        pct = {"released": 100, "pending_coo": 80, "pending_dept": 50,
               "rejected": 30, "withdrawn": 30, "draft": 10, "none": 0}.get(st, 0)
        progress.append({"code": p.code, "name": local_name(p), "status": st, "percent": pct,
                         "attachments": att_n, "overdue": od})
        if od:
            need_attention.append({"code": p.code, "name": local_name(p),
                                   "issue_code": "overdue", "due_date": p.due_date or "",
                                   "reason": "", "overdue": True})
        if st == "rejected":
            need_attention.append({"code": p.code, "name": local_name(p), "issue_code": "rejected",
                                   "reason": v.dept_reject_reason or v.coo_reject_reason})
        elif st == "pending_coo":
            need_attention.append({"code": p.code, "name": local_name(p), "issue_code": "pending_coo", "reason": ""})
        elif st == "pending_dept":
            need_attention.append({"code": p.code, "name": local_name(p), "issue_code": "pending_dept", "reason": ""})
    # 订单资料包实例的超期（按可见工厂范围）
    for op in ops:
        if is_overdue(op.due_date, op.status):
            overdue += 1

    return DashboardOut(
        package_completion=completion,
        total_attachments=total_attachments,
        pending_mine=pending_mine,
        released=released_count,
        overdue=overdue,
        package_progress=sorted(progress, key=lambda x: -x["percent"]),
        need_attention=need_attention[:10],
    )


@router.get("/export")
def export_archive_list(request: Request, db: Session = Depends(get_db),
                        user: User = Depends(export_viewer)):
    """归档清单导出（CSV）。审计查看人/COO/管理员可用。"""
    versions = db.query(PackageVersion).all()
    pkgs = {p.id: p for p in db.query(Package).all()}
    header = ["资料包编号", "资料包名称", "版本", "状态", "责任人", "附件数", "已同步NAS"]
    lines = [",".join(header)]
    for v in versions:
        p = pkgs.get(v.package_id)
        synced = sum(1 for a in v.attachments if a.nas_synced)
        lines.append(csv_row([p.code if p else "", local_name(p), v.version_no, v.status,
                              str(v.submitted_by or ""), str(len(v.attachments)), f"{synced}/{len(v.attachments)}"]))
    csv = "\n".join(lines)
    log_event(db, AuditDomain.EXPORT, "archive_csv", actor=user, ip=client_ip(request))
    return Response(content="\ufeff" + csv, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=archive_list.csv"})
