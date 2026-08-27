"""Pydantic 请求/响应模型。"""
from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field

from app.core.overdue import parse_due


def _normalize_due(v):
    """校验并规范化截止日期。

    此前 due_date 只受 `max_length=32` 约束，任何文本都能存进去，而超期判断用的
    `parse_due` 只认**年在前**的写法（`YYYY-MM-DD` / `YYYY/M/D`）。两者一对不上，
    后果是**静默的**：解析不了就当作"没有期限"，界面还照原样把用户输入显示回来，
    于是用户以为期限已设好，而超期永远不会标红。

    第 62 轮实测（同一个日历日 2020-01-15，只是写法不同）：
      `2020-01-15` → 计入超期；`01/15/2020` → **不计**；`2026-13-45` → **不计**。
    工作台 overdue 计数因此从 2 变成 1。**本系统正是做美国出口合规的**，
    录入者写出 `01/15/2020` 这种美式日期毫不意外，而它会悄悄把期限取消掉。

    做法是**拒绝而不是猜**：`01/02/2020` 究竟是 1 月 2 日还是 2 月 1 日无法判定，
    猜错得到一个错误的期限，比没有期限更糟——错误的期限看起来是可信的。
    因此不可解析一律 422 并说清期望格式；可解析的一律规范化为 ISO，
    使入库、导出与 manifest 中的写法保持一致。
    """
    if v is None:
        return v
    s = str(v).strip()
    if not s:
        return ""
    d = parse_due(s)
    if d is None:
        raise ValueError("截止日期格式不正确，请用 YYYY-MM-DD（如 2026-10-15）")
    return d.isoformat()


# 输入用的截止日期类型：留空表示无期限，其余必须可解析
DueDate = Annotated[str, AfterValidator(_normalize_due)]


def _strip(v):
    return v.strip() if isinstance(v, str) else v


# 首尾空白一律去掉。第 96 轮实测：订单号 " WS96-A " 与 "WS96-A" 并存（实质重复，
# 唯一约束拦不住）、纯空白订单号能建成、用户名 " ws96 " 入库后只能带空格登录、
# 部门编码 " D96 "。这些值会进 NAS 目录名、审计 target 与唯一约束。
# 密码字段**不**用它：密码里的空格是内容的一部分。
Stripped = Annotated[str, BeforeValidator(_strip)]


# ---------- 通用 ----------
class Msg(BaseModel):
    msg: str


class PasswordResetOut(BaseModel):
    """管理员重置密码返回：msg 描述 + 一次性展示的临时密码。"""
    msg: str
    password: str


# ---------- 认证 ----------
class LoginRequest(BaseModel):
    username: Stripped
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6)


class PasswordChangeOut(Msg):
    """改密成功：旧令牌已全部作废，附带一张新令牌让本人当前会话不中断。"""
    access_token: str


class SecretRotate(BaseModel):
    """超管轮换 JWT 密钥：custom_key 留空则随机生成（推荐）。"""
    custom_key: str = ""


# ---------- 部门 ----------
class DepartmentCreate(BaseModel):
    code: Stripped = Field(min_length=1, pattern=r"^\S+$", max_length=32)
    name_zh: Stripped = Field(min_length=1, max_length=128)
    name_en: Stripped = Field("", max_length=128)
    name_th: Stripped = Field("", max_length=128)


class DepartmentUpdate(BaseModel):
    name_zh: Optional[Stripped] = Field(None, min_length=1, max_length=128)
    name_en: Optional[Stripped] = Field(None, max_length=128)
    name_th: Optional[Stripped] = Field(None, max_length=128)


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name_zh: str
    name_en: str = ""
    name_th: str = ""
    created_at: Optional[datetime] = None


# ---------- 用户 ----------
RoleName = Literal["submitter", "dept_reviewer", "coo_reviewer", "auditor", "admin"]


class UserCreate(BaseModel):
    username: Stripped = Field(min_length=1, pattern=r"^\S+$", max_length=64)
    # 留空则服务端生成一次性临时密码并在响应里返回一次（与「重置密码」同一套流程）。
    # 界面此前把密码预填为 user123：交付后管理员建的每个账号都会是这个演示密码（第 90 轮）
    password: Optional[str] = Field(None, min_length=6)
    display_name: Stripped = Field("", max_length=128)
    email: Stripped = Field("", max_length=128)
    phone: Stripped = Field("", max_length=32)
    dept_id: Optional[int] = None
    # 角色必须是已知值：此前是自由字符串，实测 role="coo" 也能建成，登录后侧栏全空、正文 403（第 92 轮）
    role: RoleName = "submitter"
    factory_ids: list[int] = []   # 授权工厂


class UserUpdate(BaseModel):
    display_name: Optional[Stripped] = Field(None, max_length=128)
    email: Optional[Stripped] = Field(None, max_length=128)
    phone: Optional[Stripped] = Field(None, max_length=32)
    dept_id: Optional[int] = None
    role: Optional[RoleName] = None
    status: Optional[Literal["active", "disabled"]] = None
    factory_ids: Optional[list[int]] = None


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
    factory_ids: list[int] = []
    must_change_password: bool = False
    last_login_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


# ---------- 工厂 ----------
class UserCreateOut(UserOut):
    """建用户返回：未指定密码时附带一次性临时密码，只在这一次响应里出现。"""
    temp_password: str = ""


class FactoryCreate(BaseModel):
    code: Stripped = Field(min_length=1, pattern=r"^\S+$", max_length=32)
    name_zh: Stripped = Field(min_length=1, max_length=128)
    name_en: Stripped = Field("", max_length=128)
    name_th: Stripped = Field("", max_length=128)
    sort_order: int = Field(0, ge=0, le=2**31 - 1)


class FactoryUpdate(BaseModel):
    name_zh: Optional[Stripped] = Field(None, min_length=1, max_length=128)
    name_en: Optional[Stripped] = Field(None, max_length=128)
    name_th: Optional[Stripped] = Field(None, max_length=128)
    status: Optional[Stripped] = Field(None, max_length=16)
    sort_order: Optional[int] = Field(None, ge=0, le=2**31 - 1)


class FactoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name_zh: str
    name_en: str = ""
    name_th: str = ""
    status: str
    sort_order: int = 0
    created_at: Optional[datetime] = None


# ---------- 订单 ----------
class OrderCreate(BaseModel):
    factory_id: int
    order_no: Stripped = Field(min_length=1, max_length=64)
    customer: Stripped = Field("", max_length=255)
    product: Stripped = Field("", max_length=255)
    # 数量不能为负；上限取 INT 列范围，超出会被 DataError 处理器挡成 400 但提示不具体（第 97 轮）
    quantity: int = Field(0, ge=0, le=2**31 - 1)
    export_date: DueDate = Field("", max_length=32)
    status: Stripped = Field("active", max_length=16)
    note: Stripped = ""
    owner_user_id: Optional[int] = None


# 订单状态只有这三种；此前 status 是任意 ≤16 字符的字符串，第 84 轮实测 PATCH
# status='banana' 返回 200，界面上会渲染出一个谁也不认识的状态
ORDER_STATUSES = ("active", "completed", "closed")


class OrderUpdate(BaseModel):
    factory_id: Optional[int] = None
    customer: Optional[Stripped] = Field(None, max_length=255)
    product: Optional[Stripped] = Field(None, max_length=255)
    quantity: Optional[int] = Field(None, ge=0, le=2**31 - 1)
    # 出口日期与截止日期同构（第 62 轮）：不校验就会存进"明年"这类文本。
    # 它目前只用于展示，但导出清单是交给核查方的，日期写法必须可解析、统一为 ISO
    export_date: Optional[DueDate] = Field(None, max_length=32)
    status: Optional[Literal["active", "completed", "closed"]] = None
    note: Optional[Stripped] = None
    owner_user_id: Optional[int] = None


class OrderPackageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    order_id: int
    package_id: int
    project_code: str
    status: str
    owner_user_id: Optional[int] = None
    required: bool = True
    due_date: str = ""
    locked: bool = False
    # 引用型实例：附件来自资料包线的某个已放行版本，订单里只读
    source_version_id: Optional[int] = None
    submitted_by: Optional[int] = None
    submitted_at: Optional[datetime] = None
    dept_reviewer_id: Optional[int] = None
    dept_reviewed_at: Optional[datetime] = None
    dept_reject_reason: str = ""
    coo_reviewer_id: Optional[int] = None
    coo_reviewed_at: Optional[datetime] = None
    coo_reject_reason: str = ""
    created_at: Optional[datetime] = None
    # 冗余展示字段
    package_code: str = ""
    package_name: str = ""
    package_dept_id: Optional[int] = None
    attachment_count: int = 0
    # 是否可进行部门审核（含职责分离判定，需查库，故由后端下发）
    reviewable_dept: bool = True
    attachments: list["AttachmentOut"] = []


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    factory_id: int
    factory_code: str = ""
    factory_name: str = ""
    order_no: str
    customer: str = ""
    product: str = ""
    quantity: int = 0
    export_date: str = ""
    status: str
    note: str = ""
    owner_user_id: Optional[int] = None
    created_at: Optional[datetime] = None
    package_count: int = 0
    released_count: int = 0
    completion: float = 0.0


class OrderList(BaseModel):
    """带命中总数的订单列表（服务端搜索+分页）。"""
    total: int = 0
    items: list[OrderOut] = []


class OrderDetailOut(OrderOut):
    packages: list[OrderPackageOut] = []


class OrderInstanceCreate(BaseModel):
    """为订单按所选模板实例化订单-资料包。"""
    package_id: int
    owner_user_id: Optional[int] = None
    required: bool = True
    due_date: DueDate = Field("", max_length=32)


# ---------- 资料包 ----------
class PackageCreate(BaseModel):
    # 资料包编号会成为 NAS 归档目录名的一段（`{code}_{名称}`）。
    # 编号是标识符，路径分隔符在其中没有任何含义，却会让两个不同资料包
    # 归档到同一目录并互相覆盖（同 order_no 的问题，见 nas_sync._unique_segment）。
    # 现有 18 个编号均已符合本约束，加此限制不影响任何存量数据。
    code: Stripped = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9._-]+$")
    name_zh: Stripped = Field(min_length=1, max_length=255)
    name_en: Stripped = Field("", max_length=255)
    name_th: Stripped = Field("", max_length=255)
    dept_id: Optional[int] = None
    owner_user_id: Optional[int] = None
    review_focus: Stripped = ""
    due_date: DueDate = Field("", max_length=32)
    required: bool = True
    per_order: bool = True        # 随单（默认）/ 公司级


class PackageUpdate(BaseModel):
    name_zh: Optional[Stripped] = Field(None, min_length=1, max_length=255)
    name_en: Optional[Stripped] = Field(None, max_length=255)
    name_th: Optional[Stripped] = Field(None, max_length=255)
    dept_id: Optional[int] = None
    owner_user_id: Optional[int] = None
    review_focus: Optional[Stripped] = None
    due_date: Optional[DueDate] = Field(None, max_length=32)
    required: Optional[bool] = None
    per_order: Optional[bool] = None
    status: Optional[Stripped] = Field(None, max_length=16)
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
    per_order: bool = True
    status: str
    sort_order: int = 0
    created_at: Optional[datetime] = None


# ---------- 附件 ----------
class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    version_id: Optional[int] = None   # 订单附件无版本绑定
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
    change_note: Stripped = ""
    # 同样参与 NAS 归档路径（项目代号段），限定为标识符字符；留空则取默认值
    project_code: Stripped = Field("", max_length=64, pattern=r"^[A-Za-z0-9._-]*$")


# ---------- 审核 ----------
class ReviewRequest(BaseModel):
    decision: Stripped   # approve / reject
    level: Stripped   # dept / coo
    reason: Stripped = ""


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


class AuditLogList(BaseModel):
    """带命中总数的日志列表。

    只返回一页数据时，界面无从区分"确实没有更多记录"与"被 limit 截断了"，
    而审计场景里这两者的结论完全相反。total 让界面能如实说明。
    """
    total: int = 0
    items: list[AuditLogOut] = []


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


class NasConfigOut(BaseModel):
    """NAS 归档配置（secret_key 以掩码返回，不回显明文）。"""
    mode: str = "local"
    endpoint_url: str = ""
    access_key: str = ""
    secret_key: str = ""
    bucket: str = ""
    region: str = ""
    use_ssl: bool = False
    local_root: str = ""
    sync_time: str = "01:00"
    auto_sync: bool = True
    # 换归档目标时被重新标记为待归档的附件数（仅保存接口返回，用于提示管理员）
    requeued: int = 0


class NasConfigIn(BaseModel):
    # 长度上限与 system_settings.value 及常见 S3 实现的限制对齐，避免超长内容写库失败
    mode: str = Field("local", pattern="^(s3|local)$")
    endpoint_url: str = Field("", max_length=255)
    access_key: str = Field("", max_length=128)
    # 留空表示"保持不变"：接口从不回显密钥明文，前端也就无从原样回传
    secret_key: str = Field("", max_length=256)
    bucket: str = Field("", max_length=128)
    region: str = Field("", max_length=64)
    use_ssl: bool = False
    local_root: str = Field("", max_length=255)
    # HH:MM，两位小时 + 两位分钟
    sync_time: str = Field("01:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    auto_sync: bool = True


class NasTestResult(BaseModel):
    ok: bool
    detail: str = ""


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
OrderPackageOut.model_rebuild()
