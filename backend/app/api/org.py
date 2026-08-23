"""组织管理：部门与用户（F-02）。"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import client_ip, log_event
from app.core.rbac import admin_only, get_current_user
from app.core.security import generate_temp_password, hash_password
from app.core.snowflake import next_id
from app.db import get_db
from app.models import AuditDomain, Department, Factory, User
from app.schemas import (
    DepartmentCreate, DepartmentOut, DepartmentUpdate, Msg, PasswordResetOut,
    SecretRotate, UserCreate, UserOut, UserUpdate,
)

router = APIRouter(prefix="/org", tags=["org"])


# ---------- 部门 ----------
@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """部门列表对所有已登录用户开放（新建/修改仍限管理员）。

    部门名只是组织结构标签，不含敏感信息；而资料包列表要展示「责任部门」列、
    并按部门筛选（F-04），限管理员会让其他角色的该列一直显示 "-"。
    """
    return db.query(Department).order_by(Department.code).all()


@router.post("/departments", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
def create_department(payload: DepartmentCreate, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(admin_only)):
    if db.query(Department).filter(Department.code == payload.code).first():
        raise HTTPException(status_code=400, detail="部门编码已存在")
    d = Department(**payload.model_dump())
    db.add(d)
    db.commit()
    db.refresh(d)
    log_event(db, AuditDomain.ORG, "dept_create", actor=user, ip=client_ip(request), target=payload.code)
    return d


@router.patch("/departments/{dept_id}", response_model=DepartmentOut)
def update_department(dept_id: int, payload: DepartmentUpdate, request: Request,
                      db: Session = Depends(get_db), user: User = Depends(admin_only)):
    d = db.get(Department, dept_id)
    if not d:
        raise HTTPException(status_code=404, detail="部门不存在")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(d, k, v)
    db.commit()
    db.refresh(d)
    log_event(db, AuditDomain.ORG, "dept_update", actor=user, ip=client_ip(request),
              target=d.code)
    return d


# ---------- 用户 ----------
@router.get("/users", response_model=list[UserOut])
def list_users(dept_id: int | None = Query(None), db: Session = Depends(get_db),
               _: User = Depends(admin_only)):
    q = db.query(User)
    if dept_id:
        q = q.filter(User.dept_id == dept_id)
    return q.order_by(User.id).all()


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, request: Request, db: Session = Depends(get_db),
                user: User = Depends(admin_only)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    u = User(
        id=next_id(),
        username=payload.username,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name or payload.username,
        email=payload.email,
        phone=payload.phone,
        dept_id=payload.dept_id,
        role=payload.role,
        status="active",
    )
    if payload.factory_ids:
        u.factories = db.query(Factory).filter(Factory.id.in_(payload.factory_ids)).all()
    db.add(u)
    db.commit()
    db.refresh(u)
    log_event(db, AuditDomain.ORG, "user_create", actor=user, ip=client_ip(request),
              target=u.username)
    return u


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, request: Request, db: Session = Depends(get_db),
                user: User = Depends(admin_only)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    data = payload.model_dump(exclude_unset=True)
    if "password" in data:  # 不允许通过此接口改密
        data.pop("password")
    # 防自锁：不能停用自己；不能停用/降级最后一个在用管理员，否则组织管理永久失联
    disabling = data.get("status") == "disabled"
    demoting = "role" in data and data["role"] != "admin" and u.role == "admin"
    if disabling and u.id == user.id:
        raise HTTPException(status_code=400, detail="不能停用当前登录账号")
    if (disabling or demoting) and u.role == "admin":
        others = db.query(func.count(User.id)).filter(
            User.role == "admin", User.status == "active", User.id != u.id).scalar() or 0
        if others == 0:
            raise HTTPException(status_code=400, detail="系统至少需保留一个启用状态的管理员")
    factory_ids = data.pop("factory_ids", None)
    for k, v in data.items():
        setattr(u, k, v)
    if "factory_ids" in payload.model_dump(exclude_unset=True) and factory_ids is not None:
        u.factories = db.query(Factory).filter(Factory.id.in_(factory_ids)).all()
    db.commit()
    db.refresh(u)
    log_event(db, AuditDomain.ORG, "user_update", actor=user, ip=client_ip(request),
              target=u.username)
    return u


# ---------- 安全设置 ----------
@router.post("/security/rotate-jwt-secret", response_model=Msg)
def rotate_jwt_secret(payload: SecretRotate, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(admin_only)):
    """超管轮换 JWT 签名密钥：留空随机生成；轮换后全员（含本人）需重新登录。"""
    from app.core.runtime_secret import rotate_secret_key
    custom = payload.custom_key.strip()
    if custom and len(custom) < 32:
        raise HTTPException(status_code=400, detail="自定义密钥至少 32 个字符，建议留空由系统随机生成")
    rotate_secret_key(db, custom or None)
    # 不记录密钥本身，仅记录轮换事件
    log_event(db, AuditDomain.ORG, "jwt_secret_rotate", actor=user, ip=client_ip(request),
              detail="custom" if custom else "random")
    return Msg(msg="密钥已更新，所有用户需重新登录")


@router.post("/users/{user_id}/reset-password", response_model=PasswordResetOut)
def reset_password(user_id: int, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(admin_only)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    tmp = generate_temp_password()
    u.password_hash = hash_password(tmp)
    db.commit()
    # 必须记录操作人：谁重置了谁的密码是账号接管风险的关键证据
    log_event(db, AuditDomain.ORG, "user_reset_pwd", actor=user, ip=client_ip(request), target=u.username)
    return PasswordResetOut(msg="密码已重置", password=tmp)
