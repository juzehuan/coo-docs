"""待办任务队列（F-03 延伸）：按角色返回"待我处理"的可操作项，供工作台一键跳转。"""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants import VersionStatus
from app.core.i18n import local_name
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


def _staffed_dept_ids(db: Session) -> set:
    """有至少一名在岗部门审核人的部门。"""
    rows = (db.query(User.dept_id)
            .filter(User.role == "dept_reviewer", User.status == "active",
                    User.dept_id.isnot(None))
            .distinct().all())
    return {r[0] for r in rows}


def _no_reviewer(status: str, dept_id, staffed: set) -> bool:
    """待部门审核，但责任部门没有任何在岗审核人（或压根没有责任部门）。

    这类条目会**落进所有人的待办之外**：部门审核人按 `dept_id` 匹配（匹配不上），
    而 COO/管理员的待办只筛 `pending_coo`。第 63 轮实测——把某部门唯一的审核人
    调岗后，一条已提交的 `pending_dept` 在 QAL 审核人、其他部门审核人、COO、
    管理员的待办中**全部为 0 条**。它没被删也没报错，只是谁都看不见了，
    提交人却在等一个永远不会被提示的审核。

    唯一审核人离职被停用、或调岗，都是再常规不过的人事变动。
    注意 `can_review_dept` 本来就允许 admin/coo_reviewer 审核任何部门——
    **能力一直在，缺的只是可见性**。因此这里把这类条目补进他们的待办，
    而不是放宽任何权限。只补"无人可审"的那些，避免把全部 pending_dept 灌给管理员。
    """
    return status == VersionStatus.PENDING_DEPT and (dept_id is None or dept_id not in staffed)


@router.get("", response_model=list[dict])
def todo_list(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """按角色返回待办：提交人看自己被退回需整改；部门审核人看待审；COO/管理员看待终审。

    同时覆盖资料包版本（PackageVersion）与订单资料包实例（OrderPackage）两条流程线。
    COO/管理员另外会看到「责任部门无在岗审核人」的待部门审核项（见 _no_reviewer）。
    """
    staffed = _staffed_dept_ids(db)
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
            mine = (lv.status == VersionStatus.PENDING_COO
                    or _no_reviewer(lv.status, p.dept_id, staffed))
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
            "package_name": local_name(p),
            "order_id": None,
            "version_id": lv.id,
            "version_no": lv.version_no,
            "status": lv.status,
            "dept_name": local_name(dept),
            "owner_name": name(users.get(p.owner_user_id)),
            "submitter_name": name(users.get(lv.submitted_by)),
            "submitted_at": lv.submitted_at,
            "reject_reason": lv.dept_reject_reason or lv.coo_reject_reason or "",
            "attachments": ver_counts.get(lv.id, 0),
            "review_focus": p.review_focus,
            "due_date": p.due_date,
            "overdue": is_overdue(p.due_date, lv.status),
            # 责任部门无在岗审核人：前端据此标注，避免它看起来像一条普通待审
            "no_reviewer": _no_reviewer(lv.status, p.dept_id, staffed),
        })

    # ---- 订单资料包实例待办 ----
    # 不按 status 过滤：工厂停用只阻止新建订单，不应让该厂在办事项从管理员待办里消失
    # （待办漏掉 = 无人跟进，比多显示几条严重得多）
    fids = ([f.id for f in db.query(Factory).all()]
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
            mine = (op.status == VersionStatus.PENDING_COO
                    or _no_reviewer(op.status, pkg.dept_id, staffed))
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
            "package_name": local_name(pkg),
            "order_id": order.id,
            "version_id": None,
            "version_no": order.order_no,
            "status": op.status,
            "dept_name": local_name(dept),
            "owner_name": name(users.get(op.owner_user_id)),
            "submitter_name": name(users.get(op.submitted_by)),
            "submitted_at": op.submitted_at,
            "reject_reason": op.dept_reject_reason or op.coo_reject_reason or "",
            "attachments": op_counts.get(op.id, 0),
            "review_focus": pkg.review_focus,
            "due_date": op.due_date,
            "overdue": is_overdue(op.due_date, op.status),
            "no_reviewer": _no_reviewer(op.status, pkg.dept_id, staffed),
        })

    # 按提交时间倒序，无提交时间的排最后
    out.sort(key=lambda x: str(x["submitted_at"]) if x["submitted_at"] else "", reverse=True)
    return out
