"""NAS 归档同步服务。

云端主存（UPLOAD_DIR）-> 工厂本地 NAS（NAS_ROOT），经加密隧道挂载。
目录规范：{NAS_ROOT}/COO核查/{项目代号}/{资料包编号}_{简称}/{版本号}/{原文件名}
同步为单向（云端 -> NAS），只新增不删除；每次同步后写 manifest.txt。
"""
import hashlib
import os
import shutil
from datetime import datetime

from sqlalchemy.orm import Session

from app.constants import NAS_BASE_DIRNAME
from app.core.config import settings
from app.models import Attachment, Package, PackageVersion, SyncRecord

CHUNK = 1024 * 1024


def file_md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def nas_reachable() -> bool:
    root = settings.NAS_ROOT
    try:
        os.makedirs(root, exist_ok=True)
        # 尝试写入探测文件
        probe = os.path.join(root, ".probe")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except Exception:
        return False


def _nas_target_path(att: Attachment, pkg: Package, ver: PackageVersion) -> str:
    base = os.path.join(
        settings.NAS_ROOT, NAS_BASE_DIRNAME,
        ver.project_code or settings.PROJECT_CODE,
        f"{pkg.code}_{pkg.name_zh}",
        ver.version_no,
    )
    return os.path.join(base, att.original_name)


def run_sync(db: Session, run_type: str = "auto", triggered_by: int | None = None) -> SyncRecord:
    rec = SyncRecord(run_type=run_type, triggered_by=triggered_by, status="running")
    db.add(rec)
    db.commit()
    db.refresh(rec)

    reachable = nas_reachable()
    failures = []
    if not reachable:
        rec.status = "failed"
        rec.details = {"tunnel_ok": False, "failures": ["NAS 不可达或隧道未连通"]}
        rec.finished_at = datetime.utcnow()
        db.commit()
        return rec

    pending = db.query(Attachment).filter(Attachment.nas_synced.is_(False)).all()
    rec.total = len(pending)
    success = 0
    for att in pending:
        try:
            src = os.path.join(settings.UPLOAD_DIR, att.file_name)
            if not os.path.exists(src):
                failures.append({"attachment_id": att.id, "reason": "源文件缺失"})
                continue
            ver = db.get(PackageVersion, att.version_id)
            pkg = db.get(Package, ver.package_id) if ver else None
            if not ver or not pkg:
                failures.append({"attachment_id": att.id, "reason": "版本/资料包不存在"})
                continue
            dst = _nas_target_path(att, pkg, ver)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            # 校验大小与 MD5
            if os.path.getsize(dst) != att.file_size or file_md5(dst) != att.md5:
                failures.append({"attachment_id": att.id, "reason": "校验不一致"})
                continue
            att.nas_synced = True
            att.nas_synced_at = datetime.utcnow()
            success += 1
        except Exception as e:  # noqa: BLE001
            failures.append({"attachment_id": att.id, "reason": str(e)})

    rec.success = success
    rec.failed = len(failures)
    rec.status = "success" if rec.failed == 0 else ("partial" if success else "failed")
    # 写 manifest
    try:
        _write_manifests(db)
    except Exception:  # noqa: BLE001
        pass
    rec.details = {"tunnel_ok": True, "failures": failures}
    rec.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(rec)
    return rec


def _write_manifests(db: Session):
    """为每个已放行版本的目录写 manifest.txt（清单/大小/MD5）。"""
    released = db.query(PackageVersion).filter(PackageVersion.status == "released").all()
    for ver in released:
        pkg = db.get(Package, ver.package_id)
        if not pkg:
            continue
        base = os.path.join(
            settings.NAS_ROOT, NAS_BASE_DIRNAME,
            ver.project_code or settings.PROJECT_CODE,
            f"{pkg.code}_{pkg.name_zh}", ver.version_no,
        )
        manifest = os.path.join(base, "manifest.txt")
        lines = [f"# {pkg.code} {pkg.name_zh} {ver.version_no}", f"# generated {datetime.utcnow().isoformat()}"]
        for att in ver.attachments:
            lines.append(f"{att.original_name}\t{att.file_size}\t{att.md5}")
        os.makedirs(base, exist_ok=True)
        with open(manifest, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
