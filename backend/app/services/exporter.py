"""导出生成器：同步端点与异步作业 worker **共用同一份实现**。

为什么要抽出来：第 71/72 轮连着两次因为"同一段逻辑复制多份、修的时候漏掉其中
一份"出问题（引用计数三份拷贝、状态词条四份拷贝）。导出既要能同步下发、又要能
被作业 worker 调用，如果各写一遍，两条路迟早给出不一样的文件——而这些文件是
交给外部核查方的证据。

统一产出形态：**所有生成器都落到临时文件并返回 (下发文件名, 磁盘路径)**。
- 同步端点用 FileResponse 下发，响应结束后由后台任务删除；
- 作业 worker 保留文件供用户稍后下载。
xlsx 也走文件而不是内存字节：与 ZIP 保持同一条路径，调用方不必分两种情况处理
（第 54 轮已经把 ZIP 从内存构建改成临时文件，理由是内存占用等于产物体积）。

审计留痕不在这里做：同步请求要记真实客户端 IP，作业则要记提交时的 IP，
两者不同，交给各自的调用方。
"""
import os
import tempfile

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.i18n import local_name, status_label, t
from app.core.queries import latest_version  # noqa: F401  （供后续导出类型使用）
from app.core.rbac import factory_ids
from app.core.timefmt import fmt as time_fmt
from app.core.xlsx import build_xlsx
from app.models import (
    AuditLog, Order, OrderPackage, Package, PackageVersion, User,
)

# 单次审计导出的行数上限。超过要求用户缩小范围而不是硬扛：
# 第 55 轮实测 10 万行需要 36 秒 CPU、49MB 内存。
MAX_EXPORT_ROWS = 100000


def _tmp_path(suffix: str) -> str:
    """产出文件的落盘位置。与 ZIP 用同一个临时目录，便于统一巡检与清理。"""
    d = os.path.join(settings.UPLOAD_DIR, ".export-tmp")
    os.makedirs(d, exist_ok=True)
    fd, path = tempfile.mkstemp(dir=d, prefix="exp-", suffix=suffix)
    os.close(fd)
    return path


def _write(path: str, content: bytes) -> str:
    with open(path, "wb") as f:
        f.write(content)
    return path


def deliver(path: str, media_type: str, filename: str):
    """同步端点的统一下发：FileResponse + 响应结束后删除临时文件。

    与 ZIP 走同一条路（第 54 轮）：内存占用与产物体积无关，并顺带获得 Range 支持。
    """
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask

    from app.core.http_headers import content_disposition

    def _unlink():
        try:
            os.unlink(path)
        except OSError:
            pass

    return FileResponse(path, media_type=media_type,
                        headers={"Content-Disposition": content_disposition(filename)},
                        background=BackgroundTask(_unlink))


def audit_filters(q, actor_id=None, actor=None, target=None, domain=None, start=None, end=None,
                  parse_bound=None):
    """审计筛选。解析边界的函数由调用方传入，避免这里再抄一份日期解析。"""
    if actor_id:
        q = q.filter(AuditLog.actor_id == actor_id)
    if actor:
        q = q.filter(AuditLog.actor_name.contains(actor, autoescape=True))
    if target:
        q = q.filter(AuditLog.target.contains(target, autoescape=True))
    if domain:
        q = q.filter(AuditLog.event_domain == domain)
    if start and parse_bound:
        q = q.filter(AuditLog.created_at >= parse_bound(start, "start"))
    if end and parse_bound:
        q = q.filter(AuditLog.created_at <= parse_bound(end, "end", True))
    return q


class ExportTooLarge(Exception):
    """命中行数超出单次导出上限；调用方翻译为 400 或作业失败原因。"""


def audit_xlsx(db: Session, user: User, params: dict, filter_fn) -> tuple[str, str]:
    """操作日志导出。filter_fn 由 api/audit.py 传入，保证与列表用的是同一套筛选。"""
    q = filter_fn(db.query(AuditLog))
    total = q.with_entities(func.count(AuditLog.id)).scalar() or 0
    if total > MAX_EXPORT_ROWS:
        raise ExportTooLarge(
            f"符合条件的记录有 {total} 条，超过单次导出上限 {MAX_EXPORT_ROWS} 条，"
            f"请缩小时间范围后重试")
    rows = q.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).all()
    header = [t("time_site_tz"), t("domain"), t("action"), t("actor"),
              t("role"), t("ip"), t("target"), t("detail")]
    data = [[
        time_fmt(r.created_at),   # 站点时区 + 显式偏移，导出的证据必须自解释
        r.event_domain, r.action, r.actor_name, r.actor_role, r.ip, r.target, r.detail,
    ] for r in rows]
    content = build_xlsx(header, data, sheet_title=t("sheet_audit"))
    return "audit_logs.xlsx", _write(_tmp_path(".xlsx"), content), len(rows)


def archive_xlsx(db: Session, user: User, params: dict) -> tuple[str, str, int]:
    """归档清单导出。覆盖资料包版本与订单实例**两条线**（第 43 轮：只导一条等于少一半）。"""
    pkgs = {p.id: p for p in db.query(Package).all()}
    header = [t("kind"), t("pkg_code"), t("pkg_name"), t("ver_or_order"), t("status"),
              t("owner"), t("attachments"), t("nas_synced")]
    unames = {u.id: (u.display_name or u.username) for u in db.query(User).all()}
    data = []
    for v in db.query(PackageVersion).all():
        p = pkgs.get(v.package_id)
        synced = sum(1 for a in v.attachments if a.nas_synced)
        data.append([t("kind_version"), p.code if p else "", local_name(p), v.version_no,
                     status_label(v.status), unames.get(v.submitted_by, ""),
                     str(len(v.attachments)), f"{synced}/{len(v.attachments)}"])
    # 订单线按可见工厂过滤，避免受控内容跨工厂泄漏
    fids = factory_ids(user, db)
    ops = (db.query(OrderPackage).join(Order, OrderPackage.order_id == Order.id)
           .filter(Order.factory_id.in_(fids)).all()) if fids else []
    orders = {o.id: o for o in db.query(Order).all()}
    for op in ops:
        p = pkgs.get(op.package_id)
        o = orders.get(op.order_id)
        synced = sum(1 for a in op.effective_attachments if a.nas_synced)
        data.append([t("kind_order"), p.code if p else "", local_name(p),
                     o.order_no if o else "", status_label(op.status),
                     unames.get(op.owner_user_id, ""), str(len(op.effective_attachments)),
                     f"{synced}/{len(op.effective_attachments)}"])
    content = build_xlsx(header, data, sheet_title=t("sheet_archive_list"))
    return "archive_list.xlsx", _write(_tmp_path(".xlsx"), content), len(data)

class ExportGone(Exception):
    """导出目标已不存在（如订单在作业排队期间被删）。调用方翻译为 404 或作业失败原因。"""


def order_xlsx(db: Session, user: User, params: dict, visible_ids) -> tuple[str, str, int]:
    """按订单导出资料清单（Excel）。

    `visible_ids(db, user)` 由调用方提供可见订单 ID 集合——可见性规则留在
    api/orders.py，这里不复制一份（第 72 轮：同一份判定复制多份必然跑偏）。
    """
    from app.models import Factory
    order_id = int(params.get("order_id") or 0)
    o = db.get(Order, order_id)
    if not o or o.id not in visible_ids(db, user):
        raise ExportGone("订单不存在或已被删除")
    fac = db.get(Factory, o.factory_id) if o.factory_id else None
    header = [t("factory"), t("order_no"), t("pkg_code"), t("pkg_name"), t("status"),
              t("owner"), t("attachments"), t("locked"), t("due_date")]
    unames = {u.id: (u.display_name or u.username) for u in db.query(User).all()}
    data = []
    for op in sorted(o.packages, key=lambda x: x.package.code if x.package else ""):
        pkg = op.package
        data.append([
            fac.code if fac else "", o.order_no, pkg.code if pkg else "",
            local_name(pkg), status_label(op.status), unames.get(op.owner_user_id, ""),
            str(len(op.effective_attachments)), t("yes") if op.locked else t("no"), op.due_date,
        ])
    content = build_xlsx(header, data, sheet_title=t("sheet_order_list"))
    return f"order_{o.order_no}.xlsx", _write(_tmp_path(".xlsx"), content), len(data)


def order_zip(db: Session, user: User, params: dict, visible_ids) -> tuple[str, str, int]:
    """按订单打包全部真实附件（ZIP），供核查调阅 / Form 28 回函使用。"""
    import re

    from app.core.zipout import compression_for, zip_builder
    from app.models import Factory
    from app.services.nas_sync import archive_name, duplicate_names

    order_id = int(params.get("order_id") or 0)
    o = db.get(Order, order_id)
    if not o or o.id not in visible_ids(db, user):
        raise ExportGone("订单不存在或已被删除")
    fac = db.get(Factory, o.factory_id) if o.factory_id else None
    fac_code = re.sub(r"[^A-Za-z0-9_\-]", "_", fac.code) if fac else "NA"
    safe_order = re.sub(r"[^A-Za-z0-9_\-]", "_", o.order_no or "order")

    n = 0
    with zip_builder() as (zf, zpath):
        manifest = [[t("factory"), t("order_no"), t("pkg_code"), t("file_in_zip"),
                     t("orig_name"), t("stored_name"), t("size_bytes"), t("md5")]]
        for op in sorted(o.packages, key=lambda x: (x.package.code if x.package else "", x.id)):
            pkg_code = op.package.code if op.package else "NA"
            # 同一资料包内的同名附件（如多个供应商各自的"发票.pdf"）若都用原文件名，
            # 在 ZIP 里会生成路径完全相同的条目，解压时互相覆盖——交付给核查方的
            # 材料静默缺件，而清单仍列出全部。复用 NAS 归档的命名规则以保持一致。
            dup = duplicate_names(op.effective_attachments)
            for att in op.effective_attachments:
                src = os.path.join(settings.UPLOAD_DIR, att.file_name)
                if not os.path.exists(src):
                    continue
                # 安全化归档目录名与文件名，防路径穿越（ZIP Slip）
                safe_code = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]", "_", pkg_code)
                safe_name = archive_name(att, dup)
                zf.write(src, f"{fac_code}/{safe_order}/{safe_code}/{safe_name}",
                         compress_type=compression_for(safe_name))
                manifest.append([fac_code, o.order_no, pkg_code, safe_name, att.original_name,
                                 att.file_name, str(att.file_size), att.md5 or ""])
                n += 1
        # 交付给核查方的清单同样用 Excel：MD5 与订单号是纯数字/长串时，
        # CSV 会被 Excel 改写成科学计数法，清单便与实际文件对不上
        zf.writestr("_manifest.xlsx",
                    build_xlsx(manifest[0], manifest[1:], sheet_title=t("sheet_manifest")))
    return f"order_{o.order_no}_archive.zip", zpath, n

def _zip_attachments(zf, atts, arc_prefix: str, manifest, row_fn) -> int:
    """把一批附件写进 ZIP 并追加清单行。三处 ZIP 导出共用，避免各写一遍。

    同名附件若都用原文件名，会在 ZIP 内生成同路径条目、解压时互相覆盖，
    交付给核查方的材料静默缺件而清单仍列出全部；复用 NAS 归档的命名规则
    (`archive_name`) 保持三处一致。路径同时做安全化，防 ZIP Slip。
    """
    from app.core.zipout import compression_for
    from app.services.nas_sync import archive_name, duplicate_names

    dup = duplicate_names(atts)
    n = 0
    for att in atts:
        src = os.path.join(settings.UPLOAD_DIR, att.file_name)
        if not os.path.exists(src):
            continue
        safe_name = archive_name(att, dup)
        zf.write(src, f"{arc_prefix}/{safe_name}", compress_type=compression_for(safe_name))
        manifest.append(row_fn(att, safe_name))
        n += 1
    return n


def controlled_order_zip(db: Session, user: User, params: dict, check) -> tuple[str, str, int]:
    """受控区归档下载（订单线）：打包某已放行订单实例的附件。"""
    import re

    from app.core.zipout import zip_builder

    o, op, p = check(db, user, params)          # 可见性与受控状态判定留在 api 层
    safe_code = re.sub(r"[^A-Za-z0-9_\-]", "_", (p.code if p else "pkg") or "pkg")
    safe_order = re.sub(r"[^A-Za-z0-9_\-]", "_", o.order_no or "order")
    with zip_builder() as (zf, zpath):
        manifest = [[t("package"), t("order_no"), t("file_in_zip"), t("orig_name"),
                     t("stored_name"), t("size_bytes"), t("md5")]]
        n = _zip_attachments(
            zf, op.effective_attachments, f"{safe_code}/{safe_order}", manifest,
            lambda att, sn: [p.code if p else "", o.order_no, sn, att.original_name,
                             att.file_name, str(att.file_size), att.md5 or ""])
        zf.writestr("_manifest.xlsx",
                    build_xlsx(manifest[0], manifest[1:], sheet_title=t("sheet_manifest")))
    return f"controlled_{safe_code}_{safe_order}.zip", zpath, n


def controlled_version_zip(db: Session, user: User, params: dict, check) -> tuple[str, str, int]:
    """受控区归档下载（版本线）：打包某受控版本的已放行附件。"""
    import re

    from app.core.zipout import zip_builder

    p, v = check(db, user, params)
    safe_code = re.sub(r"[^A-Za-z0-9_\-]", "_", p.code or "pkg")
    with zip_builder() as (zf, zpath):
        manifest = [[t("package"), t("version"), t("file_in_zip"), t("orig_name"),
                     t("stored_name"), t("size_bytes"), t("md5")]]
        n = _zip_attachments(
            zf, v.attachments, f"{safe_code}/{v.version_no}", manifest,
            lambda att, sn: [p.code, v.version_no, sn, att.original_name, att.file_name,
                             str(att.file_size), att.md5 or ""])
        zf.writestr("_manifest.xlsx",
                    build_xlsx(manifest[0], manifest[1:], sheet_title=t("sheet_manifest")))
    return f"controlled_{safe_code}_{v.version_no}.zip", zpath, n
