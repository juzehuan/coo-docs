"""认证依赖与基于角色+部门的权限控制。"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db import get_db
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=True)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已停用")
    return user


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
any_staff = require_roles("submitter", "dept_reviewer", "coo_reviewer", "auditor", "admin")


def is_admin(u: User) -> bool:
    return u.role == "admin"


def is_coo(u: User) -> bool:
    return u.role in ("coo_reviewer", "admin")


def can_review_dept(u: User, package_dept_id) -> bool:
    """部门审核人仅能审核本人责任部门范围内的资料包。"""
    if u.role == "admin" or u.role == "coo_reviewer":
        return True
    if u.role == "dept_reviewer":
        return package_dept_id is not None and package_dept_id == u.dept_id
    return False


def can_edit_package(u: User, package) -> bool:
    """提交人仅能编辑本人负责的资料包。"""
    if u.role in ("admin", "dept_reviewer", "coo_reviewer"):
        return True
    if u.role == "submitter":
        return package.owner_user_id == u.id
    return False
