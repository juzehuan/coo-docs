"""认证接口：登录、当前用户、改密。"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.audit import client_ip, log_event
from app.constants import ALLOWED_EXTENSIONS
from app.core.config import settings
from app.core.rbac import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db import get_db
from app.models import AuditDomain, User
from app.schemas import LoginRequest, Msg, PasswordChange, PasswordChangeOut, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


# 登录页「演示账号一键登录」的候选账号及其公开演示口令。
# 与 services/seed.py 的 ACCOUNTS 一一对应；前端 Login.tsx 持有同一份口令用于点击登录。
#
# 这里列全 15 个账号（此前只列了 5 个代表角色）：演示与验收时要按具体岗位走流程
# ——采购专员传料 → 工程采购经理初审 → COO 终审——只给"部门审核人"一个按钮，
# 演示者还得回去查哪个账号对应哪个部门。
#
# ⚠️ 这些是公开口令。按钮是否渲染由 /auth/demo-accounts 逐个校验口令后决定：
# 生产部署（SEED_DEMO_DATA=false）不会创建这些账号，口令一旦轮换该账号即自动摘掉，
# 全部摘掉后入口整体消失。正式交付前请轮换口令或停用这些账号（见风险记录 P0-1）。
DEMO_CREDENTIALS = {
    "admin": "admin123",
    "coo": "coo123",
    "auditor": "audit123",
    "dept_wai": "dept123",
    "dept_eng": "dept123",
    "dept_sal": "dept123",
    "dept_fin": "dept123",
    "dept_log": "dept123",
    "dept_prd": "dept123",
    "dept_qal": "dept123",
    "dept_adm": "dept123",
    # 停用状态的账号不会出现在按钮里（下面按 status == active 过滤），
    # 列在这里是为了与 seed 的 ACCOUNTS 保持一份完整对照
    "dept_eng2": "dept123",
    "submit_wai": "user123",
    "submit_eng": "user123",
    "submit_sal": "user123",
    "submit_fin": "user123",
    "submit_log": "user123",
    "submit_prd": "user123",
    "submit_qal": "user123",
    "submit_adm": "user123",
}


@router.get("/limits")
def upload_limits():
    """公开的上传限制，供前端做客户端预检。

    上限只写在后端：前端若自己写死一个数字，两边迟早会脱节——改了后端却忘了
    改前端，用户就会遇到"界面说可以传、传完却被拒"。而没有预检的代价很实在：
    实测上传一个 105MB 的文件（后端上限 100MB），客户端把 110MB 全部发完才收到
    400，工厂 2Mbps 的网络上等于白等 7 分钟。
    """
    return {
        "max_file_mb": settings.MAX_FILE_MB,
        "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
    }


@router.get("/demo-accounts")
def demo_accounts(db: Session = Depends(get_db)):
    """返回当前环境中演示快捷登录**确实可用**的账号（无需认证）。

    登录页此前无条件渲染演示按钮，而生产部署（SEED_DEMO_DATA=false）根本
    不会创建这些账号：用户点下去只会拿到 401，页面看起来像是坏了。

    判据是"口令是否仍为演示值"而非"账号是否存在"——因为 admin 在任何部署
    里都存在（生产实例的 admin 用的是随机初始口令），只按存在与否判断会让
    生产登录页重新冒出一个点了必然失败的管理员按钮。逐个校验口令之后，
    生产环境返回空数组、入口自然消失；口令被轮换过的演示账号也会自动摘掉。
    只返回用户名、姓名与角色，不返回口令。姓名是必需的——15 个账号里有 8 个
    都是"部门审核人"，只给角色名的话按钮上会出现 8 个一模一样的「部门审核人」。
    """
    rows = (db.query(User)
            .filter(User.username.in_(list(DEMO_CREDENTIALS)), User.status == "active").all())
    order = {u: i for i, u in enumerate(DEMO_CREDENTIALS)}
    out = [
        {"username": u.username, "display_name": u.display_name or u.username, "role": u.role}
        for u in rows
        if verify_password(DEMO_CREDENTIALS[u.username], u.password_hash)
    ]
    return sorted(out, key=lambda x: order.get(x["username"], 99))


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


@router.post("/change-password", response_model=PasswordChangeOut)
def change_password(payload: PasswordChange, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码错误")
    user.password_hash = hash_password(payload.new_password)
    # 作废所有旧令牌（其它设备/标签页上的会话），再给本人签一张新的
    user.password_changed_at = datetime.utcnow()
    db.commit()
    log_event(db, AuditDomain.AUTH, "change_password", actor=user, ip=client_ip(request))
    return PasswordChangeOut(msg="密码已更新", access_token=create_access_token(str(user.id), user.role))


@router.post("/logout", response_model=Msg)
def logout(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    log_event(db, AuditDomain.AUTH, "logout", actor=user, ip=client_ip(request))
    return Msg(msg="已登出")
