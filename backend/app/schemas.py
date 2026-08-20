"""Pydantic 请求/响应模型。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------- 通用 ----------
class Msg(BaseModel):
    msg: str


# ---------- 认证 ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6)


# ---------- 部门 ----------
class DepartmentCreate(BaseModel):
    code: str
    name_zh: str
    name_en: str = ""
    name_th: str = ""


class DepartmentUpdate(BaseModel):
    name_zh: Optional[str] = None
    name_en: Optional[str] = None
    name_th: Optional[str] = None


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name_zh: str
    name_en: str = ""
    name_th: str = ""
    created_at: Optional[datetime] = None


# ---------- 用户 ----------
class UserCreate(BaseModel):
    username: str
    password: str = Field(min_length=6)
    display_name: str = ""
    email: str = ""
    phone: str = ""
    dept_id: Optional[int] = None
    role: str = "submitter"


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    dept_id: Optional[int] = None
    role: Optional[str] = None
    status: Optional[str] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str = ""
    email: str = ""
    phone: str = ""
    dept_id: Optional[int] = None
    role: str
    status: str
    last_login_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


# ---------- 资料包 ----------
class PackageCreate(BaseModel):
    code: str
    name_zh: str
    name_en: str = ""
    name_th: str = ""
    dept_id: Optional[int] = None
    owner_user_id: Optional[int] = None
    review_focus: str = ""
    due_date: str = ""
    required: bool = True


class PackageUpdate(BaseModel):
    name_zh: Optional[str] = None
    name_en: Optional[str] = None
    name_th: Optional[str] = None
    dept_id: Optional[int] = None
    owner_user_id: Optional[int] = None
    review_focus: Optional[str] = None
    due_date: Optional[str] = None
    required: Optional[bool] = None
    status: Optional[str] = None
    sort_order: Optional[int] = None


class PackageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name_zh: str
    name_en: str = ""
    name_th: str = ""
    dept_id: Optional[int] = None
    owner_user_id: Optional[int] = None
    review_focus: str = ""
    due_date: str = ""
    required: bool = True
    status: str
    sort_order: int = 0
    created_at: Optional[datetime] = None


# ---------- 附件 ----------
class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    version_id: int
    file_name: str
    original_name: str
    file_size: int = 0
    md5: str = ""
    mime_type: str = ""
    order_no: str = ""
    batch_no: str = ""
    uploaded_by: Optional[int] = None
    uploaded_at: Optional[datetime] = None
    nas_synced: bool = False
    nas_synced_at: Optional[datetime] = None


# ---------- 版本 ----------
class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    package_id: int
    project_code: str
    version_no: str
    status: str
    change_note: str = ""
    locked: bool = False
    submitted_by: Optional[int] = None
    submitted_at: Optional[datetime] = None
    dept_reviewer_id: Optional[int] = None
    dept_reviewed_at: Optional[datetime] = None
    dept_reject_reason: str = ""
    coo_reviewer_id: Optional[int] = None
    coo_reviewed_at: Optional[datetime] = None
    coo_reject_reason: str = ""
    created_at: Optional[datetime] = None
    attachments: list[AttachmentOut] = []


class VersionCreate(BaseModel):
    change_note: str = ""
    project_code: str = ""


# ---------- 审核 ----------
class ReviewRequest(BaseModel):
    decision: str   # approve / reject
    level: str      # dept / coo
    reason: str = ""


# ---------- 审计 ----------
class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_domain: str
    action: str
    actor_id: Optional[int] = None
    actor_role: str = ""
    actor_name: str = ""
    ip: str = ""
    target: str = ""
    detail: str = ""
    created_at: Optional[datetime] = None


# ---------- NAS ----------
class SyncRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    run_type: str
    triggered_by: Optional[int] = None
    total: int = 0
    success: int = 0
    failed: int = 0
    status: str = ""
    details: dict = {}
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class NasStatusOut(BaseModel):
    nas_root: str
    nas_reachable: bool
    last_sync: Optional[SyncRecordOut] = None
    pending_count: int = 0


# ---------- 看板 ----------
class DashboardOut(BaseModel):
    package_completion: float = 0.0      # 资料包完成度 %
    total_attachments: int = 0
    pending_mine: int = 0
    released: int = 0
    overdue: int = 0
    package_progress: list[dict] = []
    need_attention: list[dict] = []


# 解决前向引用
TokenResponse.model_rebuild()
