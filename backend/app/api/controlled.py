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
from app.core.rbac import require_roles
from app.db import get_db
from app.models import Package, PackageVersion, User
from app.schemas import VersionOut

router = APIRouter(prefix="/controlled", tags=["controlled"])

# 受控区（F-09）仅审核/管理员可访问：部门审核人、COO 终审人、管理员
controlled_access = require_roles("dept_reviewer", "coo_reviewer", "admin")


def _visible_pkg_ids(db: Session, user: User) -> set:
    """受控区可见范围：部门审核人仅本部门包；COO/管理员可见全部。"""
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
        manifest = [["资料包", "版本", "附件原名", "存储文件名", "大小(字节)"]]
        for att in v.attachments:
            src = os.path.join(settings.UPLOAD_DIR, att.file_name)
            if not os.path.exists(src):
                continue
            safe_name = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]", "_", att.original_name or att.file_name)
            arc = f"{safe_code}/{v.version_no}/{safe_name}"
            zf.write(src, arc)
            manifest.append([p.code, v.version_no, att.original_name, att.file_name, str(att.file_size)])
        _q = lambda c: c.replace(chr(34), chr(34) * 2)
        zf.writestr("_manifest.csv", "\ufeff" + "\n".join(",".join(f'"{_q(c)}"' for c in row) for row in manifest))
    buf.seek(0)

    log_event(db, AuditDomain.EXPORT, "controlled_export_zip", actor=user,
              ip=client_ip(request), target=f"{p.code}/{v.version_no}")
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=controlled_{safe_code}_{v.version_no}.zip"},
    )