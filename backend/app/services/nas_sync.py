"""NAS 归档同步服务。

云端主存（UPLOAD_DIR）-> NAS 对象存储 / 本地目录：
- 生产：S3 兼容接口（MinIO / 群晖 / 威联通 / 云对象存储），对象键遵循受控目录规范
  {S3_BUCKET}/COO核查/{项目代号}/{资料包编号}_{简称}/{版本号}/{原文件名}
- 开发回退：未配置 S3 时同步到本地 NAS_ROOT 目录（模拟挂载点）

同步为单向（云端 -> NAS），只新增不删除；每次同步后为已放行版本写 manifest.txt。
"""
import hashlib
import os
import shutil
from datetime import datetime

from sqlalchemy.orm import Session

from app.constants import NAS_BASE_DIRNAME
from app.core.config import settings
from app.models import Attachment, Package, PackageVersion, SyncRecord
from app.services import s3

CHUNK = 1024 * 1024


def file_md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _common_parts(ver: PackageVersion, pkg: Package) -> list[str]:
    return [
        NAS_BASE_DIRNAME,
        ver.project_code or settings.PROJECT_CODE,
        f"{pkg.code}_{pkg.name_zh}",
        ver.version_no,
    ]


class _LocalBackend:
    """本地目录回退：NAS_ROOT 模拟挂载点（开发环境 / 未配置 S3 时）。"""

    name = "local"

    def reachable(self) -> bool:
        root = settings.NAS_ROOT
        try:
            os.makedirs(root, exist_ok=True)
            probe = os.path.join(root, ".probe")
            with open(probe, "w") as f:
                f.write("ok")
            os.remove(probe)
            return True
        except Exception:  # noqa: BLE001
            return False

    def version_base(self, ver: PackageVersion, pkg: Package) -> str:
        return os.path.join(settings.NAS_ROOT, *_common_parts(ver, pkg))

    def target(self, att: Attachment, pkg: Package, ver: PackageVersion) -> str:
        return os.path.join(self.version_base(ver, pkg), att.original_name or att.file_name)

    def sync_one(self, target: str, src: str, att: Attachment) -> bool:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(src, target)
        return os.path.getsize(target) == att.file_size and file_md5(target) == att.md5

    def write_manifest(self, base: str, lines: list[str]) -> None:
        os.makedirs(base, exist_ok=True)
        with open(os.path.join(base, "manifest.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def display(self) -> str:
        return settings.NAS_ROOT


class _S3Backend:
    """S3 兼容接口后端：MinIO / NAS S3 服务 / 云对象存储。"""

    name = "s3"

    def __init__(self):
        self.cli = s3.client()

    def reachable(self) -> bool:
        return s3.reachable(self.cli)

    def version_base(self, ver: PackageVersion, pkg: Package) -> str:
        return "/".join(_common_parts(ver, pkg))

    def target(self, att: Attachment, pkg: Package, ver: PackageVersion) -> str:
        name = att.original_name or att.file_name
        return f"{self.version_base(ver, pkg)}/{name}"

    def sync_one(self, key: str, src: str, att: Attachment) -> bool:
        if not s3.put_file(self.cli, key, src):
            return False
        meta = s3.head(self.cli, key)
        if not meta:
            return False
        etag = (meta.get("ETag") or "").strip('"')
        return int(meta.get("ContentLength") or -1) == att.file_size and etag == att.md5

    def write_manifest(self, base: str, lines: list[str]) -> None:
        s3.put_bytes(self.cli, f"{base}/manifest.txt", ("\n".join(lines) + "\n").encode("utf-8"))

    def display(self) -> str:
        return f"s3://{settings.S3_BUCKET}@{settings.S3_ENDPOINT_URL}"


def _backend():
    return _S3Backend() if s3.enabled() else _LocalBackend()


def nas_reachable() -> bool:
    return _backend().reachable()


def nas_target_display() -> str:
    """NAS 目标展示（NAS 状态卡片）。"""
    return _backend().display()


def run_sync(db: Session, run_type: str = "auto", triggered_by: int | None = None) -> SyncRecord:
    rec = SyncRecord(run_type=run_type, triggered_by=triggered_by, status="running")
    db.add(rec)
    db.commit()
    db.refresh(rec)

    backend = _backend()
    failures = []
    if not backend.reachable():
        rec.status = "failed"
        rec.details = {"backend": backend.name, "tunnel_ok": False,
                       "failures": ["NAS 不可达或 S3/MinIO 未连通"]}
        rec.finished_at = datetime.utcnow()
        db.commit()
        return rec

    if backend.name == "s3":
        s3.ensure_bucket(backend.cli)

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
            target = backend.target(att, pkg, ver)
            if not backend.sync_one(target, src, att):
                failures.append({"attachment_id": att.id, "reason": "上传或校验不一致"})
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
        _write_manifests(db, backend)
    except Exception:  # noqa: BLE001
        pass
    rec.details = {"backend": backend.name, "tunnel_ok": True, "failures": failures}
    rec.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(rec)
    return rec


def _write_manifests(db: Session, backend):
    """为每个已放行版本的目录/前缀写 manifest.txt（清单/大小/MD5）。"""
    released = db.query(PackageVersion).filter(PackageVersion.status == "released").all()
    for ver in released:
        pkg = db.get(Package, ver.package_id)
        if not pkg:
            continue
        base = backend.version_base(ver, pkg)
        lines = [f"# {pkg.code} {pkg.name_zh} {ver.version_no}",
                 f"# generated {datetime.utcnow().isoformat()}"]
        for att in ver.attachments:
            lines.append(f"{att.original_name}\t{att.file_size}\t{att.md5}")
        backend.write_manifest(base, lines)
