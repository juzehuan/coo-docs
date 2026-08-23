"""待办任务队列（F-03 延伸）：按角色返回"待我处理"的可操作项，供工作台一键跳转。"""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants import VersionStatus
from app.core.overdue import is_overdue
from app.core.rbac import get_current_user
from app.db import get_db
from app.models import Attachment, Department, Factory, Order, OrderPackage, Package, PackageVersion, User


def _att_counts(db: Session, column, ids: list[int]) -> dict[int, int]:
    """批量统计附件数。

    逐条访问 xx.attachments 会对每个待办行各发一次 SQL（N+1），
    在两年规模数据下待办接口要发数百条查询；改为按 id 集合一次性聚合。
    """
    if not ids:
        return {}
    rows = (
        db.query(column, func.count(Attachment.id))
        .filter(column.in_(ids))
        .group_by(column)
        .all()
    )
    return {k: v for k, v in rows}

router = APIRouter(prefix="/todo", tags=["todo"])


def _latest_version(db: Session, pkg_id: int) -> PackageVersion | None:
    return (
        db.query(PackageVersion)
        .filter(PackageVersion.package_id == pkg_id)
        .order_by(PackageVersion.id.desc())   # 同 packages.py：按单调递增的雪花 ID 取最新
        .first()
    )


@router.get("", response_model=list[dict])
def todo_list(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """按角色返回待办：提交人看自己被退回需整改；部门审核人看待审；COO/管理员看待终审。

    同时覆盖资料包版本（PackageVersion）与订单资料包实例（OrderPackage）两条流程线。
    """
    pkgs = db.query(Package).order_by(Package.sort_order, Package.code).all()
    depts = {d.id: d for d in db.query(Department).all()}
    users = {u.id: u for u in db.query(User).all()}

    def name(u: User | None) -> str:
        return (u.display_name or u.username) if u else ""

    out = []
    # ---- 资料包版本待办 ----
    # 先筛出"待我处理"的版本，再批量统计附件数，避免逐行懒加载
    ver_hits: list[tuple] = []
    for p in pkgs:
        lv = _latest_version(db, p.id)
        if not lv:
            continue
        # 角色判定：当前资料包是否为"待我处理"
        if user.role == "submitter":
            mine = p.owner_user_id == user.id \
                and lv.status in (VersionStatus.REJECTED, VersionStatus.WITHDRAWN)
        elif user.role == "dept_reviewer":
            mine = p.dept_id == user.dept_id and lv.status == VersionStatus.PENDING_DEPT
        elif user.role in ("coo_reviewer", "admin"):
            mine = lv.status == VersionStatus.PENDING_COO
        else:  # auditor 只读，无待办
            mine = False
        if not mine:
            continue
        ver_hits.append((p, lv))

    ver_counts = _att_counts(db, Attachment.version_id, [lv.id for _p, lv in ver_hits])
    for p, lv in ver_hits:
        dept = depts.get(p.dept_id) if p.dept_id else None
        out.append({
            "kind": "package",
            "package_id": p.id,
            "package_code": p.code,
            "package_name": p.name_zh,
            "order_id": None,
            "version_id": lv.id,
            "version_no": lv.version_no,
            "status": lv.status,
            "dept_name": dept.name_zh if dept else "",
            "owner_name": name(users.get(p.owner_user_id)),
            "submitter_name": name(users.get(lv.submitted_by)),
            "submitted_at": lv.submitted_at,
            "reject_reason": lv.dept_reject_reason or lv.coo_reject_reason or "",
            "attachments": ver_counts.get(lv.id, 0),
            "review_focus": p.review_focus,
            "due_date": p.due_date,
            "overdue": is_overdue(p.due_date, lv.status),
        })

    # ---- 订单资料包实例待办 ----
    fids = ([f.id for f in db.query(Factory).filter(Factory.status == "active").all()]
            if user.role == "admin" else [f.id for f in user.factories])
    ops = (
        db.query(OrderPackage)
        .join(Order, OrderPackage.order_id == Order.id)
        .join(Package, OrderPackage.package_id == Package.id)
        .filter(Order.factory_id.in_(fids))  # 订单实例按工厂隔离
        .all()
    )
    orders = {o.id: o for o in db.query(Order).all()}
    op_hits: list[tuple] = []
    for op in ops:
        pkg = op.package
        order = orders.get(op.order_id)
        if not pkg or not order:
            continue
        if user.role == "submitter":
            mine = (op.owner_user_id == user.id or op.submitted_by == user.id) \
                and op.status in (VersionStatus.REJECTED, VersionStatus.WITHDRAWN)
        elif user.role == "dept_reviewer":
            mine = pkg.dept_id == user.dept_id and op.status == VersionStatus.PENDING_DEPT
        elif user.role in ("coo_reviewer", "admin"):
            mine = op.status == VersionStatus.PENDING_COO
        else:
            mine = False
        if not mine:
            continue
        op_hits.append((op, pkg, order))

    op_counts = _att_counts(db, Attachment.order_package_id, [o.id for o, _p, _r in op_hits])
    for op, pkg, order in op_hits:
        dept = depts.get(pkg.dept_id) if pkg.dept_id else None
        out.append({
            "kind": "order",
            "package_id": op.id,
            "package_code": pkg.code,
            "package_name": pkg.name_zh,
            "order_id": order.id,
            "version_id": None,
            "version_no": order.order_no,
            "status": op.status,
            "dept_name": dept.name_zh if dept else "",
            "owner_name": name(users.get(op.owner_user_id)),
            "submitter_name": name(users.get(op.submitted_by)),
            "submitted_at": op.submitted_at,
            "reject_reason": op.dept_reject_reason or op.coo_reject_reason or "",
            "attachments": op_counts.get(op.id, 0),
            "review_focus": pkg.review_focus,
            "due_date": op.due_date,
            "overdue": is_overdue(op.due_date, op.status),
        })

    # 按提交时间倒序，无提交时间的排最后
    out.sort(key=lambda x: str(x["submitted_at"]) if x["submitted_at"] else "", reverse=True)
    return out
