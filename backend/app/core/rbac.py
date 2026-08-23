"""认证依赖与基于角色+部门的权限控制。"""
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db import get_db
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=True)


def get_current_user(request: Request, token: str = Depends(oauth2_scheme),
                     db: Session = Depends(get_db)) -> User:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效或过期的凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise cred_exc
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise cred_exc
    if user.status == "disabled":
        # 用 401 而非 403：账号停用意味着这张令牌不再是有效凭证（认证失效），
        # 403 表示"已认证但无权限"，前端不会据此登出，用户会卡在数据全空却无提示的界面里。
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号已停用，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # 供请求日志中间件标注操作人：否则日志里的 4xx/5xx 无法回答"是谁触发的"
    request.state.log_user = f"{user.username}({user.role})"
    return user


# 可选 Bearer：下载端点允许"票据"或"Bearer"二选一，缺少 Authorization 头时
# 不能直接 401，否则带票据的原生下载会被挡在门外。
_optional_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def optional_current_user(request: Request, token: str | None = Depends(_optional_oauth2),
                          db: Session = Depends(get_db)) -> User | None:
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None
    user = db.get(User, int(payload["sub"]))
    if not user or user.status == "disabled":
        return None
    request.state.log_user = f"{user.username}({user.role})"
    return user


def user_from_download_ticket(request: Request, aid: int, ticket: str | None,
                              db: Session) -> User | None:
    """下载票据换取用户；无票据返回 None（调用方回退常规 Bearer）。

    票据只解决"浏览器原生下载带不了 Authorization 头"这一个问题，
    换出用户后**仍走与常规请求完全相同的权限判定**，不是绕过权限的旁路。
    """
    if not ticket:
        return None
    from app.core import dl_ticket
    uid = dl_ticket.verify(ticket, aid)
    if uid is None:
        raise HTTPException(status_code=403, detail="下载凭据无效或已过期，请重新发起下载")
    u = db.get(User, uid)
    if not u or u.status == "disabled":
        raise HTTPException(status_code=403, detail="下载凭据无效或已过期，请重新发起下载")
    request.state.log_user = f"{u.username}({u.role})"
    return u


def require_roles(*roles: str):
    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return user
    return _dep


# 角色快捷依赖
admin_only = require_roles("admin")
coo_or_admin = require_roles("coo_reviewer", "admin")
reviewer_or_above = require_roles("dept_reviewer", "coo_reviewer", "admin")
audit_viewer = require_roles("auditor", "admin")          # 审计日志仅审计员/管理员可读
export_viewer = require_roles("coo_reviewer", "auditor", "admin")  # 归档导出角色
nas_viewer = require_roles("coo_reviewer", "auditor", "admin")     # NAS 归档查看角色
any_staff = require_roles("submitter", "dept_reviewer", "coo_reviewer", "auditor", "admin")


def is_admin(u: User) -> bool:
    return u.role == "admin"


def is_coo(u: User) -> bool:
    return u.role in ("coo_reviewer", "admin")


def dept_review_block_reason(u: User, package_dept_id, submitted_by=None, db=None) -> str | None:
    """不能进行部门审核的**具体原因**；可审则返回 None。

    此前只有一个布尔返回，两种截然不同的情形共用同一句「非本部门审核人」：
    实测本部门审核人审自己提交的内容时也收到这句话——他明明就是本部门审核人，
    管理员照着这句去查部门配置只会白费功夫，审核人则会以为账号配错了。
    """
    if u.role in ("admin", "coo_reviewer"):
        return None
    if u.role != "dept_reviewer":
        return "非本部门审核人"
    if package_dept_id is None or package_dept_id != u.dept_id:
        return "非本部门审核人"
    if submitted_by is not None and submitted_by == u.id and db is not None:
        others = db.query(func.count(User.id)).filter(
            User.role == "dept_reviewer",
            User.dept_id == u.dept_id,
            User.id != u.id,
            User.status == "active",
        ).scalar() or 0
        if others > 0:
            return "职责分离：不能审核本人提交的内容，请由本部门其他审核人处理"
    return None


def can_review_dept(u: User, package_dept_id, submitted_by=None, db=None) -> bool:
    """部门审核人仅能审核本人责任部门范围内的资料包。

    职责分离：当本部门存在其他部门审核人（可履行审核职责）时，
    禁止审核人审核本人提交的内容；若本部门仅一名审核人（无替代者），
    为保持流程可闭环，允许其审核本人提交的内容。
    """
    if u.role == "admin" or u.role == "coo_reviewer":
        return True
    if u.role == "dept_reviewer":
        if package_dept_id is None or package_dept_id != u.dept_id:
            return False
        if submitted_by is not None and submitted_by == u.id and db is not None:
            others = db.query(func.count(User.id)).filter(
                User.role == "dept_reviewer",
                User.dept_id == u.dept_id,
                User.id != u.id,
                User.status == "active",
            ).scalar() or 0
            if others > 0:
                return False
        return True
    return False


def can_view_package(u: User, package) -> bool:
    """资料包/附件可见性：提交人仅本人负责包，部门审核人仅本部门包，
    COO/审计员/管理员可见全部。"""
    if u.role in ("admin", "coo_reviewer", "auditor"):
        return True
    if u.role == "dept_reviewer":
        return package.dept_id is not None and package.dept_id == u.dept_id
    if u.role == "submitter":
        return package.owner_user_id == u.id
    return False


def can_edit_package(u: User, package) -> bool:
    """编辑/提交权限：提交人仅本人负责包；部门审核人仅本部门包；COO/管理员任意。"""
    if u.role in ("admin", "coo_reviewer"):
        return True
    if u.role == "dept_reviewer":
        return package.dept_id is not None and package.dept_id == u.dept_id
    if u.role == "submitter":
        return package.owner_user_id == u.id
    return False


def can_edit_order(u: User, order) -> bool:
    """订单级增删改：COO/管理员任意；提交人仅本人负责的订单。"""
    if u.role in ("admin", "coo_reviewer"):
        return True
    if u.role == "submitter":
        return order.owner_user_id == u.id
    return False


def can_edit_order_package(u: User, op) -> bool:
    """订单实例的上传/删除附件、提交审核：COO/管理员任意；
    部门审核人仅本部门实例；提交人仅本人负责的实例。"""
    if u.role in ("admin", "coo_reviewer"):
        return True
    if u.role == "dept_reviewer":
        pkg = op.package if op.package is not None else None
        return pkg is not None and pkg.dept_id is not None and pkg.dept_id == u.dept_id
    if u.role == "submitter":
        return op.owner_user_id == u.id
    return False
