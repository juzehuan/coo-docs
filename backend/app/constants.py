"""平台全局常量：角色、状态、审计事件域等。"""
from enum import Enum


class Role(str, Enum):
    SUBMITTER = "submitter"          # 提交人
    DEPT_REVIEWER = "dept_reviewer"  # 部门审核人
    COO_REVIEWER = "coo_reviewer"    # COO 终审人
    AUDITOR = "auditor"              # 审计查看人
    ADMIN = "admin"                  # 系统管理员


ROLE_LABELS = {
    Role.SUBMITTER: {"zh": "提交人", "en": "Submitter", "th": "ผู้ส่ง"},
    Role.DEPT_REVIEWER: {"zh": "部门审核人", "en": "Dept Reviewer", "th": "ผู้ตรวจสอบแผนก"},
    Role.COO_REVIEWER: {"zh": "COO 终审人", "en": "COO Reviewer", "th": "ผู้ตรวจสอบ COO"},
    Role.AUDITOR: {"zh": "审计查看人", "en": "Auditor", "th": "ผู้ตรวจสอบ"},
    Role.ADMIN: {"zh": "系统管理员", "en": "Admin", "th": "ผู้ดูแลระบบ"},
}


class UserStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class PackageStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class VersionStatus(str, Enum):
    DRAFT = "draft"              # 草稿
    PENDING_DEPT = "pending_dept"  # 待部门审核
    PENDING_COO = "pending_coo"    # 待COO终审
    RELEASED = "released"          # 已放行
    REJECTED = "rejected"          # 已退回


VERSION_STATUS_LABELS = {
    VersionStatus.DRAFT: {"zh": "草稿", "en": "Draft", "th": "ร่าง"},
    VersionStatus.PENDING_DEPT: {"zh": "待部门审核", "en": "Pending Dept", "th": "รอแผนก"},
    VersionStatus.PENDING_COO: {"zh": "待COO终审", "en": "Pending COO", "th": "รอ COO"},
    VersionStatus.RELEASED: {"zh": "已放行", "en": "Released", "th": "อนุมัติ"},
    VersionStatus.REJECTED: {"zh": "已退回", "en": "Rejected", "th": "ถูกตีกลับ"},
}


class ReviewLevel(str, Enum):
    DEPT = "dept"
    COO = "coo"


class ReviewDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


# 审计事件域（{domain}.{action}）
class AuditDomain:
    AUTH = "auth"
    PACKAGE = "package"
    ATTACHMENT = "attachment"
    REVIEW = "review"
    VERSION = "version"
    NAS = "nas"
    EXPORT = "export"
    ORG = "org"


# 允许上传的文件扩展名（白名单）
ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff",
    ".zip", ".rar", ".7z", ".txt", ".csv",
}

DEFAULT_MAX_FILE_MB = 100
PROJECT_CODE_DEFAULT = "Bintelli-US"
NAS_BASE_DIRNAME = "COO核查"
