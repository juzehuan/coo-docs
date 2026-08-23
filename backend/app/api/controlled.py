"""受控区：仅展示 COO 已终审放行的版本，并支持归档下载（F-09）。"""
import io
import os
import re
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.constants import AuditDomain, VersionStatus
from app.core.audit import client_ip, log_event
from app.core.config import settings
from app.core.i18n import local_name
from app.core.xlsx import build_xlsx
from app.core.http_headers import content_disposition
from app.services.nas_sync import archive_name, duplicate_names
from app.core.rbac import require_roles
from app.db import get_db
from app.models import Order, OrderPackage, Package, PackageVersion, User
from app.schemas import AttachmentOut, VersionOut

router = APIRouter(prefix="/controlled", tags=["controlled"])

# 受控区（F-09）为只读调阅区：部门审核人、COO 终审人、管理员，以及审计查看人。
# 规格书角色表明确「审计查看人：只读调阅已放行资料，导出清单」——受控区正是内审/
# 外部核查配合人员的主要工作面，此处若排除 auditor 会让该角色无法履行本职。
# 本模块只提供查看与归档下载，不含任何写入口，故对 auditor 开放不违反其只读约束。
controlled_access = require_roles("dept_reviewer", "coo_reviewer", "auditor", "admin")


def _visible_pkg_ids(db: Session, user: User) -> set:
    """受控区可见范围：部门审核人仅本部门包；COO/审计查看人/管理员可见全部。"""
    q = db.query(Package)
    if user.role == "dept_reviewer":
        q = q.filter(Package.dept_id == user.dept_id)
    return {p.id for p in q.all()}


def _visible_factory_ids(db: Session, user: User) -> set:
    """受控区订单线的工厂可见范围。

    工厂是本系统的数据隔离边界（规格 2.4）：受控区若不做同样的过滤，
    就会从这条旁路泄露未授权工厂的订单号与资料包内容（第 13 轮通知泄漏同源）。
    """
    from app.models import Factory
    if user.role == "admin":
        return {f.id for f in db.query(Factory).all()}
    return {f.id for f in user.factories}


@router.get("", response_model=list[dict])
def controlled_area(db: Session = Depends(get_db), user: User = Depends(controlled_access)):
    """受控区清单：COO 已终审放行的全部受控单元。

    此前只查 PackageVersion，**遗漏了订单资料包实例这条线**——而订单线才是
    日常主要工作流（客户订单 → 资料包实例 → 双级审核 → 放行锁定）。实测库中
    32 条已放行版本全部可见，而 31 条已放行且锁定的订单实例在受控区完全看不到。
    受控区是审计员与外部核查方调阅已放行资料的主要工作面，缺一半等于查不全。
    NAS 归档、ZIP 交付、工作台统计本就覆盖两条线，受控区是唯一的例外。
    """
    visible = _visible_pkg_ids(db, user)
    out = []

    # ---- 资料包版本线 ----
    released = (
        db.query(PackageVersion)
        .filter(PackageVersion.status == VersionStatus.RELEASED,
                PackageVersion.package_id.in_(visible))
        .order_by(PackageVersion.package_id, PackageVersion.version_no)
        .all()
    )
    pkgs = {p.id: p for p in db.query(Package).all()}
    for v in released:
        p = pkgs.get(v.package_id)
        if not p:
            continue
        out.append({
            "kind": "version",
            "key": f"v-{v.id}",
            "package_code": p.code,
            "package_name": local_name(p),
            "subject": v.version_no,
            "attachment_count": len(v.attachments),
            "locked": v.locked,
            "released_at": v.coo_reviewed_at.isoformat() if v.coo_reviewed_at else None,
            "ids": {"pkg_id": str(p.id), "version_id": str(v.id)},
            "attachments": [AttachmentOut.model_validate(a).model_dump() for a in v.attachments],
            # 兼容旧字段：前端历史实现读 version.version_no
            "version": VersionOut.model_validate(v).model_dump(),
        })

    # ---- 订单资料包实例线 ----
    fids = _visible_factory_ids(db, user)
    ops = (
        db.query(OrderPackage)
        .join(Order, OrderPackage.order_id == Order.id)
        .filter(OrderPackage.status == VersionStatus.RELEASED,
                OrderPackage.locked.is_(True),
                OrderPackage.package_id.in_(visible),
                Order.factory_id.in_(fids) if fids else False)
        .all()
    )
    orders = {o.id: o for o in db.query(Order).all()}
    for op in ops:
        p = pkgs.get(op.package_id)
        o = orders.get(op.order_id)
        if not p or not o:
            continue
        out.append({
            "kind": "order",
            "key": f"o-{op.id}",
            "package_code": p.code,
            "package_name": local_name(p),
            "subject": o.order_no,
            "attachment_count": len(op.attachments),
            "locked": op.locked,
            "released_at": op.coo_reviewed_at.isoformat() if op.coo_reviewed_at else None,
            "ids": {"order_id": str(o.id), "op_id": str(op.id)},
            "attachments": [AttachmentOut.model_validate(a).model_dump() for a in op.attachments],
        })

    out.sort(key=lambda r: (r["package_code"], r["subject"]))
    return out


@router.get("/orders/{order_id}/packages/{op_id}/export/zip")
def download_released_order_zip(order_id: int, op_id: int, request: Request,
                                db: Session = Depends(get_db),
                                user: User = Depends(controlled_access)):
    """受控区归档下载（订单线）：打包某已放行订单实例的附件为 ZIP。"""
    op = db.get(OrderPackage, op_id)
    o = db.get(Order, order_id)
    if not op or not o or op.order_id != o.id or op.status != VersionStatus.RELEASED or not op.locked:
        raise HTTPException(status_code=404, detail="受控内容不存在")
    if op.package_id not in _visible_pkg_ids(db, user) or o.factory_id not in _visible_factory_ids(db, user):
        raise HTTPException(status_code=404, detail="受控内容不存在")
    p = db.get(Package, op.package_id)

    buf = io.BytesIO()
    safe_code = re.sub(r"[^A-Za-z0-9_\-]", "_", (p.code if p else "pkg") or "pkg")
    safe_order = re.sub(r"[^A-Za-z0-9_\-]", "_", o.order_no or "order")
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = [["资料包", "订单号", "包内文件名", "附件原名", "存储文件名", "大小(字节)", "MD5"]]
        dup = duplicate_names(op.attachments)
        for att in op.attachments:
            src = os.path.join(settings.UPLOAD_DIR, att.file_name)
            if not os.path.exists(src):
                continue
            safe_name = archive_name(att, dup)
            zf.write(src, f"{safe_code}/{safe_order}/{safe_name}")
            manifest.append([p.code if p else "", o.order_no, safe_name, att.original_name,
                             att.file_name, str(att.file_size), att.md5 or ""])
        zf.writestr("_manifest.xlsx", build_xlsx(manifest[0], manifest[1:], sheet_title="交付清单"))
    buf.seek(0)
    log_event(db, AuditDomain.EXPORT, "controlled_export_zip", actor=user,
              ip=client_ip(request), target=f"{p.code if p else ''}/{o.order_no}")
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": content_disposition(f"controlled_{safe_code}_{safe_order}.zip")})


@router.get("/{pkg_id}/versions/{vid}/export/zip")
def download_released_zip(pkg_id: int, vid: int, request: Request,
                          db: Session = Depends(get_db),
                          user: User = Depends(controlled_access)):
    """受控区归档下载：打包某受控版本的已放行真实附件为 ZIP，供核查调阅/Form 28 回函。"""
    v = db.get(PackageVersion, vid)
    p = db.get(Package, pkg_id)
    if not v or v.package_id != pkg_id or v.status != VersionStatus.RELEASED:
        raise HTTPException(status_code=404, detail="受控版本不存在")
    if not p or p.id not in _visible_pkg_ids(db, user):
        raise HTTPException(status_code=404, detail="受控版本不存在")

    buf = io.BytesIO()
    safe_code = re.sub(r"[^A-Za-z0-9_\-]", "_", p.code or "pkg")
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = [["资料包", "版本", "包内文件名", "附件原名", "存储文件名", "大小(字节)", "MD5"]]
        # 同名附件若都用原文件名会在 ZIP 内生成同路径条目、解压时互相覆盖，
        # 导致交付给核查方的材料静默缺件；复用 NAS 归档命名规则保持三处一致。
        dup = duplicate_names(v.attachments)
        for att in v.attachments:
            src = os.path.join(settings.UPLOAD_DIR, att.file_name)
            if not os.path.exists(src):
                continue
            safe_name = archive_name(att, dup)
            arc = f"{safe_code}/{v.version_no}/{safe_name}"
            zf.write(src, arc)
            manifest.append([p.code, v.version_no, safe_name, att.original_name, att.file_name,
                             str(att.file_size), att.md5 or ""])
        zf.writestr("_manifest.xlsx", build_xlsx(manifest[0], manifest[1:], sheet_title="交付清单"))
    buf.seek(0)

    log_event(db, AuditDomain.EXPORT, "controlled_export_zip", actor=user,
              ip=client_ip(request), target=f"{p.code}/{v.version_no}")
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": content_disposition(f"controlled_{p.code}_{v.version_no}.zip")},
    )