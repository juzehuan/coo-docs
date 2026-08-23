"""认证接口：登录、当前用户、改密。"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.audit import client_ip, log_event
from app.core.config import settings
from app.core.rbac import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db import get_db
from app.models import AuditDomain, User
from app.schemas import LoginRequest, Msg, PasswordChange, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


# 登录页「演示账号一键登录」的候选账号（口令固定且公开，仅用于演示环境）。
# 该列表与 services/seed.py 的 ACCOUNTS 对应，前端据此渲染按钮。
DEMO_USERNAMES = ["coo", "dept_wai", "submit_eng", "auditor"]


@router.get("/demo-accounts")
def demo_accounts(db: Session = Depends(get_db)):
    """返回当前环境中真实存在且可用的演示账号（无需认证）。

    登录页此前无条件渲染演示快捷登录按钮，而生产部署（SEED_DEMO_DATA=false）
    根本不会创建这些账号：用户点下去只会拿到 401，页面看起来像是坏了。
    由后端据实回答"这些账号在不在"，前端按结果决定是否显示入口——
    生产环境返回空数组，入口自然消失；演示环境不受影响。
    只暴露用户名与角色，不返回口令（口令本就是公开的演示值，写在前端）。
    """
    if not DEMO_USERNAMES:
        return []
    rows = (db.query(User.username, User.role)
            .filter(User.username.in_(DEMO_USERNAMES), User.status == "active").all())
    order = {u: i for i, u in enumerate(DEMO_USERNAMES)}
    return sorted(
        [{"username": r.username, "role": r.role} for r in rows],
        key=lambda x: order.get(x["username"], 99),
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    # 锁定期间直接拒绝，不再累计失败次数、也不延长锁定期
    if user and user.locked_until and user.locked_until > datetime.utcnow():
        log_event(db, AuditDomain.AUTH, "login_blocked", ip=client_ip(request),
                  target=payload.username, detail="账号处于锁定期")
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="账号已锁定，请稍后重试")

    # 统一错误，避免用户名枚举
    if not user or not verify_password(payload.password, user.password_hash):
        # 记录失败次数（仅当账号存在）
        if user:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= settings.MAX_LOGIN_FAILURES:
                user.locked_until = datetime.utcnow() + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
            db.commit()
        log_event(db, AuditDomain.AUTH, "login_failed", ip=client_ip(request),
                  target=payload.username, detail="用户名或密码错误")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    if user.status == "disabled":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已停用")

    # 登录成功：重置失败计数与锁定状态
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.utcnow()
    db.commit()

    token = create_access_token(str(user.id), user.role)
    log_event(db, AuditDomain.AUTH, "login", actor=user, ip=client_ip(request))
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


# 兼容 OAuth2 表单登录（便于 Swagger 调试）
@router.post("/login/form", response_model=TokenResponse)
def login_form(form: OAuth2PasswordRequestForm = Depends(), request: Request = None,
               db: Session = Depends(get_db)):
    return login(LoginRequest(username=form.username, password=form.password), request, db)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/change-password", response_model=Msg)
def change_password(payload: PasswordChange, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码错误")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    log_event(db, AuditDomain.AUTH, "change_password", actor=user, ip=client_ip(request))
    return Msg(msg="密码已更新")


@router.post("/logout", response_model=Msg)
def logout(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    log_event(db, AuditDomain.AUTH, "logout", actor=user, ip=client_ip(request))
    return Msg(msg="已登出")
