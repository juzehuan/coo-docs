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
from app.core.csv_safe import csv_row
from app.core.http_headers import content_disposition
from app.services.nas_sync import archive_name, duplicate_names
from app.core.rbac import require_roles
from app.db import get_db
from app.models import Package, PackageVersion, User
from app.schemas import VersionOut

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


@router.get("", response_model=list[dict])
def controlled_area(db: Session = Depends(get_db), user: User = Depends(controlled_access)):
    # 仅展示当前账号可见范围内已放行的版本
    visible = _visible_pkg_ids(db, user)
    released = (
        db.query(PackageVersion)
        .filter(PackageVersion.status == VersionStatus.RELEASED,
                PackageVersion.package_id.in_(visible))
        .order_by(PackageVersion.package_id, PackageVersion.version_no)
        .all()
    )
    pkgs = {p.id: p for p in db.query(Package).all()}
    out = []
    for v in released:
        p = pkgs.get(v.package_id)
        if not p:
            continue
        out.append({
            "package_code": p.code,
            "package_name": p.name_zh,
            "version": VersionOut.model_validate(v).model_dump(),
            "attachment_count": len(v.attachments),
            "locked": v.locked,
        })
    return out


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
        zf.writestr("_manifest.csv", "\ufeff" + "\n".join(csv_row(row) for row in manifest))
    buf.seek(0)

    log_event(db, AuditDomain.EXPORT, "controlled_export_zip", actor=user,
              ip=client_ip(request), target=f"{p.code}/{v.version_no}")
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": content_disposition(f"controlled_{p.code}_{v.version_no}.zip")},
    )