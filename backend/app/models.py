"""SQLAlchemy 模型定义（snake_case 字段）。"""
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Table, Text,
)
from sqlalchemy.orm import relationship

from app.constants import AuditDomain
from app.core.snowflake import next_id
from app.db import Base


def _id() -> int:
    return next_id()


# 账号-工厂 多对多授权：一个账号可访问多个工厂
user_factories = Table(
    "user_factories",
    Base.metadata,
    Column("user_id", BigInteger, ForeignKey("users.id"), primary_key=True),
    Column("factory_id", BigInteger, ForeignKey("factories.id"), primary_key=True),
)


class Factory(Base):
    """工厂（数据隔离边界），如 RMA / WEV。"""
    __tablename__ = "factories"

    id = Column(BigInteger, primary_key=True, default=_id)
    code = Column(String(32), unique=True, nullable=False, index=True)   # RMA / WEV
    name_zh = Column(String(128), nullable=False)
    name_en = Column(String(128), nullable=False, default="")
    name_th = Column(String(128), nullable=False, default="")
    status = Column(String(16), nullable=False, default="active")        # active/disabled
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("User", secondary=user_factories, back_populates="factories")
    orders = relationship("Order", back_populates="factory")


class Department(Base):
    __tablename__ = "departments"

    id = Column(BigInteger, primary_key=True, default=_id)
    code = Column(String(32), unique=True, nullable=False)
    name_zh = Column(String(128), nullable=False)
    name_en = Column(String(128), nullable=False, default="")
    name_th = Column(String(128), nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("User", back_populates="department")


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, default=_id)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(128), nullable=False, default="")
    email = Column(String(128), default="")
    phone = Column(String(32), default="")
    dept_id = Column(BigInteger, ForeignKey("departments.id"), nullable=True, index=True)
    role = Column(String(32), nullable=False, default="submitter")
    status = Column(String(16), nullable=False, default="active")  # active/disabled
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    department = relationship("Department", back_populates="users")
    factories = relationship("Factory", secondary=user_factories, back_populates="users")

    @property
    def factory_ids(self) -> list:
        return [f.id for f in self.factories]


class Package(Base):
    """资料包配置（COO-01 ~ COO-18 等）。"""
    __tablename__ = "packages"

    id = Column(BigInteger, primary_key=True, default=_id)
    code = Column(String(32), unique=True, nullable=False, index=True)  # COO-01
    name_zh = Column(String(255), nullable=False)
    name_en = Column(String(255), nullable=False, default="")
    name_th = Column(String(255), nullable=False, default="")
    dept_id = Column(BigInteger, ForeignKey("departments.id"), nullable=True, index=True)  # 责任部门
    owner_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True, index=True)   # 责任人
    review_focus = Column(Text, default="")       # 核查重点
    due_date = Column(String(32), default="")     # 截止日期（文本，宽松）
    required = Column(Boolean, default=True)      # 是否必需
    status = Column(String(16), nullable=False, default="active")  # active/disabled
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    versions = relationship("PackageVersion", back_populates="package", cascade="all, delete-orphan")


class Order(Base):
    """客户订单（数据模型以订单为中心组织资料收集）。"""
    __tablename__ = "orders"

    id = Column(BigInteger, primary_key=True, default=_id)
    factory_id = Column(BigInteger, ForeignKey("factories.id"), nullable=False, index=True)
    order_no = Column(String(64), unique=True, nullable=False, index=True)      # 订单号（PO）
    customer = Column(String(255), nullable=False, default="")                  # 客户
    product = Column(String(255), nullable=False, default="")                   # 产品
    quantity = Column(Integer, default=0)                                       # 数量
    export_date = Column(String(32), default="")                                # 预计/实际出口日期（宽松文本）
    status = Column(String(16), nullable=False, default="active")               # active/completed/closed
    note = Column(Text, default="")
    owner_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True, index=True)  # 责任人
    created_at = Column(DateTime, default=datetime.utcnow)

    factory = relationship("Factory", back_populates="orders")
    packages = relationship("OrderPackage", back_populates="order", cascade="all, delete-orphan")


class OrderPackage(Base):
    """订单-资料包实例：一个订单按资料包模板实例化一份资料，承载提交-审核-放行流程。"""
    __tablename__ = "order_packages"

    id = Column(BigInteger, primary_key=True, default=_id)
    order_id = Column(BigInteger, ForeignKey("orders.id"), nullable=False, index=True)
    package_id = Column(BigInteger, ForeignKey("packages.id"), nullable=False, index=True)  # 模板
    project_code = Column(String(64), nullable=False, default="Bintelli-US")
    status = Column(String(16), nullable=False, default="draft")
    owner_user_id = Column(BigInteger, nullable=True)   # 责任人（继承模板，可覆盖）
    required = Column(Boolean, default=True)
    due_date = Column(String(32), default="")
    submitted_by = Column(BigInteger, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    dept_reviewer_id = Column(BigInteger, nullable=True)
    dept_reviewed_at = Column(DateTime, nullable=True)
    dept_reject_reason = Column(Text, default="")
    coo_reviewer_id = Column(BigInteger, nullable=True)
    coo_reviewed_at = Column(DateTime, nullable=True)
    coo_reject_reason = Column(Text, default="")
    locked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("Order", back_populates="packages")
    package = relationship("Package")
    attachments = relationship("Attachment", back_populates="order_package", cascade="all, delete-orphan")


class PackageVersion(Base):
    """资料包的一个版本（V1.0 / V1.1 ...），承载一次提交-审核-放行流程。"""
    __tablename__ = "package_versions"

    id = Column(BigInteger, primary_key=True, default=_id)
    package_id = Column(BigInteger, ForeignKey("packages.id"), nullable=False, index=True)
    project_code = Column(String(64), nullable=False, default="Bintelli-US")
    version_no = Column(String(16), nullable=False, default="V1.0")
    status = Column(String(16), nullable=False, default="draft")  # draft/pending_dept/pending_coo/released/rejected
    change_note = Column(Text, default="")          # 变更说明
    locked = Column(Boolean, default=False)         # 已放行锁定
    submitted_by = Column(BigInteger, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    dept_reviewer_id = Column(BigInteger, nullable=True)
    dept_reviewed_at = Column(DateTime, nullable=True)
    dept_reject_reason = Column(Text, default="")
    coo_reviewer_id = Column(BigInteger, nullable=True)
    coo_reviewed_at = Column(DateTime, nullable=True)
    coo_reject_reason = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    package = relationship("Package", back_populates="versions")
    attachments = relationship("Attachment", back_populates="version", cascade="all, delete-orphan")


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(BigInteger, primary_key=True, default=_id)
    version_id = Column(BigInteger, ForeignKey("package_versions.id"), nullable=True, index=True)
    order_package_id = Column(BigInteger, ForeignKey("order_packages.id"), nullable=True, index=True)
    file_name = Column(String(255), nullable=False)     # 存储文件名（含扩展名）
    original_name = Column(String(255), nullable=False)  # 用户上传原名
    file_size = Column(BigInteger, default=0)
    md5 = Column(String(64), default="")
    mime_type = Column(String(128), default="")
    order_no = Column(String(128), default="")   # 订单号
    batch_no = Column(String(128), default="")   # 批次号
    uploaded_by = Column(BigInteger, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    nas_synced = Column(Boolean, default=False)
    nas_synced_at = Column(DateTime, nullable=True)

    version = relationship("PackageVersion", back_populates="attachments")
    order_package = relationship("OrderPackage", back_populates="attachments")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(BigInteger, primary_key=True, default=_id)
    event_domain = Column(String(64), nullable=False)   # auth/package/attachment/...
    action = Column(String(64), nullable=False)         # 具体动作
    actor_id = Column(BigInteger, nullable=True)
    actor_role = Column(String(32), default="")
    actor_name = Column(String(128), default="")
    ip = Column(String(64), default="")
    target = Column(String(255), default="")            # 目标对象描述
    detail = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class Notification(Base):
    """站内通知：提交/审核/放行等关键事件按用户推送。"""
    __tablename__ = "notifications"

    id = Column(BigInteger, primary_key=True, default=_id)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    body = Column(Text, default="")
    type = Column(String(32), default="")        # submit/dept_review/coo_review/released/rejected/withdrawn
    link = Column(String(255), default="")       # 前端跳转路径
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class SyncRecord(Base):
    """NAS 同步批次记录。"""
    __tablename__ = "sync_records"

    id = Column(BigInteger, primary_key=True, default=_id)
    run_type = Column(String(16), nullable=False, default="auto")  # auto/manual
    triggered_by = Column(BigInteger, nullable=True)
    total = Column(Integer, default=0)
    success = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    status = Column(String(16), default="running")      # running/success/partial/failed
    details = Column(JSON, default=dict)                # {failures:[...], tunnel_ok:bool}
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
