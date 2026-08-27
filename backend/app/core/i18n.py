"""请求级语言上下文与多语字段取值。

系统的核心业务对象（18 类资料包、部门、工厂）在库里都存了 zh/en/th 三份名称，
但接口下发的扁平化展示字段一律取 name_zh，导致英文/泰文界面下资料包清单、
部门名、工厂名全是中文——而泰国工厂的提交人正是主要用户，那份"该传什么材料"
的清单恰恰是他们最需要读懂的内容。

这里用 ContextVar 承载语言，而不是给每个函数加 lang 参数：取名发生在
_order_row / todo 行组装这类深层辅助函数里，逐个改签名会波及大量调用点，
且以后新增字段又会漏。中间件在请求入口设置一次，取值处直接读。

注：Starlette 把同步端点放进线程池执行时会复制上下文，ContextVar 在
sync def 端点内同样可读。
"""
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware

SUPPORTED = ("zh", "en", "th")
DEFAULT_LANG = "zh"

_lang: ContextVar[str] = ContextVar("lang", default=DEFAULT_LANG)


def current_lang() -> str:
    return _lang.get()


def local_name(obj, default: str = "") -> str:
    """按当前请求语言取对象名称，缺译时回退中文。

    回退到中文而非留空：宁可显示一个看得懂却语言不对的名字，
    也不能让资料包名变成空白——那会让清单无法辨认。
    """
    if obj is None:
        return default
    lang = current_lang()
    val = getattr(obj, f"name_{lang}", None)
    if val and val.strip():
        return val
    return getattr(obj, "name_zh", None) or default


class LangMiddleware(BaseHTTPMiddleware):
    """从 X-Lang 请求头读取界面语言（前端 axios 拦截器统一带上）。"""

    async def dispatch(self, request, call_next):
        raw = (request.headers.get("X-Lang") or "").lower()
        token = _lang.set(raw if raw in SUPPORTED else DEFAULT_LANG)
        try:
            return await call_next(request)
        finally:
            _lang.reset(token)

# ---------------------------------------------------------------------------
# 导出文件的词条
#
# 导出的 Excel 与 ZIP 内清单是**交给外部核查方**的产物（本项目正是美国出口审查），
# 而此前表头一律硬编码中文、状态直接写枚举原值、布尔写中文"是"、类型写中文
# "资料包版本"。第 68 轮实测英文导出的实际内容：
#   表头 = 中文；资料包名称 = 已本地化；状态 = `released`（原始枚举）；
#   已放行锁定 = `是`；类型 = `资料包版本`；而"责任人"列填的是 19 位雪花 ID。
# 一份给美国审查方的清单长成这样，既读不懂也不像正式交付物。
#
# 措辞与界面保持一致（取自前端 i18n/messages.ts 的同名词条与 statusLabels），
# 否则同一个状态在界面和导出里叫两个名字，核对时会被当成两回事。
# 缺译回退中文，理由同 local_name：宁可语言不对，也不能让表头变空白。
_MESSAGES: dict[str, dict[str, str]] = {
    # —— 表头 ——
    "factory":      {"zh": "工厂", "en": "Factory", "th": "โรงงาน"},
    "order_no":     {"zh": "订单号", "en": "Order No.", "th": "เลขคำสั่งซื้อ"},
    "pkg_code":     {"zh": "资料包编号", "en": "Package Code", "th": "รหัสแพ็กเกจ"},
    "pkg_name":     {"zh": "资料包名称", "en": "Package Name", "th": "ชื่อแพ็กเกจ"},
    "package":      {"zh": "资料包", "en": "Package", "th": "แพ็กเกจข้อมูล"},
    "status":       {"zh": "状态", "en": "Status", "th": "สถานะ"},
    "owner":        {"zh": "责任人", "en": "Owner", "th": "ผู้รับผิดชอบ"},
    "attachments":  {"zh": "附件数", "en": "Attachments", "th": "จำนวนไฟล์แนบ"},
    "locked":       {"zh": "已放行锁定", "en": "Released & Locked", "th": "อนุมัติและล็อก"},
    "due_date":     {"zh": "截止日期", "en": "Due Date", "th": "วันครบกำหนด"},
    "kind":         {"zh": "类型", "en": "Type", "th": "ประเภท"},
    "ver_or_order": {"zh": "版本/订单号", "en": "Version / Order No.", "th": "เวอร์ชัน / เลขคำสั่งซื้อ"},
    "version":      {"zh": "版本", "en": "Version", "th": "เวอร์ชัน"},
    "nas_synced":   {"zh": "已同步NAS", "en": "Synced to NAS", "th": "ซิงก์ไป NAS แล้ว"},
    "time_site_tz": {"zh": "时间（站点时区）", "en": "Time (site timezone)", "th": "เวลา (เขตเวลาไซต์)"},
    "domain":       {"zh": "域", "en": "Domain", "th": "โดเมน"},
    "action":       {"zh": "动作", "en": "Action", "th": "การกระทำ"},
    "actor":        {"zh": "操作人", "en": "Actor", "th": "ผู้ดำเนินการ"},
    "role":         {"zh": "角色", "en": "Role", "th": "บทบาท"},
    "ip":           {"zh": "IP", "en": "IP", "th": "IP"},
    "target":       {"zh": "目标", "en": "Target", "th": "เป้าหมาย"},
    "detail":       {"zh": "说明", "en": "Detail", "th": "รายละเอียด"},
    "file_in_zip":  {"zh": "包内文件名", "en": "File Name in ZIP", "th": "ชื่อไฟล์ใน ZIP"},
    "orig_name":    {"zh": "附件原名", "en": "Original File Name", "th": "ชื่อไฟล์เดิม"},
    "stored_name":  {"zh": "存储文件名", "en": "Stored File Name", "th": "ชื่อไฟล์ที่จัดเก็บ"},
    "size_bytes":   {"zh": "大小(字节)", "en": "Size (bytes)", "th": "ขนาด (ไบต์)"},
    "md5":          {"zh": "MD5", "en": "MD5", "th": "MD5"},
    # —— 取值 ——
    "yes":          {"zh": "是", "en": "Yes", "th": "ใช่"},
    "no":           {"zh": "否", "en": "No", "th": "ไม่ใช่"},
    "kind_version": {"zh": "资料包版本", "en": "Package Version", "th": "เวอร์ชันแพ็กเกจ"},
    "kind_order":   {"zh": "订单实例", "en": "Order Instance", "th": "อินสแตนซ์คำสั่งซื้อ"},
    # 状态措辞与前端 statusLabels 完全一致
    "st_draft":        {"zh": "草稿", "en": "Draft", "th": "ร่าง"},
    "st_pending_dept": {"zh": "待部门审核", "en": "Pending Dept", "th": "รอแผนก"},
    "st_pending_coo":  {"zh": "待COO终审", "en": "Pending COO", "th": "รอ COO"},
    "st_released":     {"zh": "已放行", "en": "Released", "th": "อนุมัติ"},
    "st_rejected":     {"zh": "已退回", "en": "Rejected", "th": "ถูกตีกลับ"},
    "st_withdrawn":    {"zh": "已撤回", "en": "Withdrawn", "th": "ถูกถอน"},
    # —— 工作表名 ——
    "sheet_order_list":   {"zh": "订单资料清单", "en": "Order Document List", "th": "รายการเอกสารคำสั่งซื้อ"},
    "sheet_archive_list": {"zh": "归档清单", "en": "Archive List", "th": "รายการจัดเก็บ"},
    "sheet_audit":        {"zh": "操作日志", "en": "Audit Log", "th": "บันทึกการดำเนินการ"},
    "sheet_manifest":     {"zh": "交付清单", "en": "Delivery Manifest", "th": "รายการส่งมอบ"},
}


def t(key: str, default: str = "") -> str:
    """按当前请求语言取词条；缺译回退中文，再缺回退 key 本身。"""
    m = _MESSAGES.get(key)
    if not m:
        return default or key
    return m.get(current_lang()) or m.get("zh") or default or key


def status_label(status: str | None) -> str:
    """状态枚举 → 当前语言的可读名称。

    导出里此前直接写 `released` 这类枚举原值——它既不是中文也不是给人看的英文，
    而界面上写的是"已放行"，同一个状态两个说法，核对时会被当成两回事。
    未知状态原样返回，不要吞掉信息。
    """
    if not status:
        return ""
    return t(f"st_{status}", status)
