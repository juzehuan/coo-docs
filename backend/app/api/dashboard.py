"""工作概览看板（F-03）。"""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants import VersionStatus
from app.core.heavy import heavy_slot
from app.services import exporter
from app.core.audit import client_ip, log_event
from app.core.overdue import is_overdue
from app.core.http_headers import content_disposition
from app.core.i18n import local_name, status_label, t
from app.core.xlsx import XLSX_MEDIA_TYPE, build_xlsx
from app.core.rbac import (can_view_package, export_viewer, factory_ids as _factory_ids,
                           get_current_user,
                           no_reviewer_for, staffed_dept_ids)
from app.db import get_db
from app.models import Attachment, AuditDomain, Factory, Order, OrderPackage, Package, PackageVersion, User
from app.schemas import DashboardOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


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

    # 待我处理：提交人看**已指派未提交**与被退回/撤回；部门审核人看待部门审核；
    # COO/管理员看待终审，外加「责任部门无在岗审核人」的兜底项。
    # 这里的判定必须与 /todo 列表逐条一致——两边各写一份，用户就会看到
    # "计数说有 3 条、列表只有 1 条"，而无从判断哪个是对的。
    staffed = staffed_dept_ids(db)
    pending_mine = 0
    # 候选集 = 每个资料包的最新版本 ∪ 所有在审版本，与 /todo 一致。
    # 只看"最新版本"会漏掉这种情况：一个已提交的 pending_dept 版本，
    # 只要有人在它之上再建一个新版本（草稿），最新版就变成那个草稿，
    # 这条正在等人审的版本会从待办与计数里一起消失（第 70 轮实测）。
    in_review: dict = {}
    for v in versions:
        if v.status in (VersionStatus.PENDING_DEPT, VersionStatus.PENDING_COO):
            in_review.setdefault(v.package_id, []).append(v)
    for p in pkgs:
        cands, seen = [], set()
        for v in [latest.get(p.id)] + in_review.get(p.id, []):
            if v is not None and v.id not in seen:
                seen.add(v.id)
                cands.append(v)
        for v in cands:
            if user.role == "submitter" and p.owner_user_id == user.id \
                    and v.status in (VersionStatus.DRAFT, VersionStatus.REJECTED,
                                     VersionStatus.WITHDRAWN):
                pending_mine += 1
            elif user.role == "dept_reviewer" and p.dept_id == user.dept_id and v.status == VersionStatus.PENDING_DEPT:
                pending_mine += 1
            elif user.role in ("coo_reviewer", "admin") and (
                    v.status == VersionStatus.PENDING_COO
                    or no_reviewer_for(v.status, p.dept_id, staffed)):
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
                    and op.status in (VersionStatus.DRAFT, VersionStatus.REJECTED,
                                      VersionStatus.WITHDRAWN):
                pending_mine += 1
        elif user.role == "dept_reviewer":
            if pkg.dept_id == user.dept_id and op.status == VersionStatus.PENDING_DEPT:
                pending_mine += 1
        elif user.role in ("coo_reviewer", "admin"):
            # 与待办列表保持同一套判定（第 63 轮只改了列表，计数漏改会两边对不上）
            if (op.status == VersionStatus.PENDING_COO
                    or no_reviewer_for(op.status, pkg.dept_id, staffed)):
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
                        user: User = Depends(export_viewer),
                        _heavy: None = Depends(heavy_slot)):
    """归档清单导出（Excel）。审计查看人/COO/管理员可用。

    覆盖**两条线**：资料包版本与订单资料包实例。此前只导出版本线，
    而订单线才是日常主要工作流——实测清单 32 行、遗漏 31 条已放行订单实例，
    交给核查方的"归档清单"少了一半内容却看不出任何缺失迹象。
    """
    # 生成逻辑在 services/exporter.py，与异步导出作业共用同一份实现
    fname, path, n = exporter.archive_xlsx(db, user, {})
    log_event(db, AuditDomain.EXPORT, "archive_xlsx", actor=user, ip=client_ip(request))
    return exporter.deliver(path, XLSX_MEDIA_TYPE, fname)
