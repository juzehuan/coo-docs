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


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    # 统一错误，避免用户名枚举
    if not user or not verify_password(payload.password, user.password_hash):
        # 记录失败次数（仅当账号存在）
        if user and user.status == "active":
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= settings.MAX_LOGIN_FAILURES:
                user.locked_until = datetime.utcnow() + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
            db.commit()
        log_event(db, AuditDomain.AUTH, "login_failed", ip=client_ip(request),
                  target=payload.username, detail="用户名或密码错误")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    if user.status == "disabled":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已停用")
    if user.locked_until and user.locked_until > datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="账号已锁定，请稍后重试")

    # 重置失败计数
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
