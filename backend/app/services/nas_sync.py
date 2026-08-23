"""NAS 归档同步服务。

云端主存（UPLOAD_DIR）-> NAS 对象存储 / 本地目录：
- 生产：S3 兼容接口（MinIO / 群晖 / 威联通 / 云对象存储），对象键遵循受控目录规范
  {S3_BUCKET}/COO核查/{项目代号}/{资料包编号}_{简称}/{版本号}/{原文件名}
- 开发回退：未配置 S3 时同步到本地 NAS_ROOT 目录（模拟挂载点）

同步为单向（云端 -> NAS），只新增不删除；每次同步后为已放行版本写 manifest.txt。
"""
import hashlib
import logging
import os
import re
import shutil
from datetime import datetime

from sqlalchemy.orm import Session

from app.constants import NAS_BASE_DIRNAME
from app.core.config import settings
from app.core import nas_config
from app.models import Attachment, Order, OrderPackage, Package, PackageVersion, SyncRecord
from app.services import s3

logger = logging.getLogger("app.nas_sync")

# 单条同步记录里最多保存多少条失败明细（超出只记数量，完整内容进日志）
MAX_DETAIL_FAILURES = 50

CHUNK = 1024 * 1024


def _safe_segment(s: str, fallback: str = "_") -> str:
    """清洗单个路径/对象键片段：去除路径分隔符与控制字符，防目录穿越。"""
    if not s:
        return fallback
    s = re.sub(r"[\\/]", "_", s)          # 阻止 ../ 或 路径分隔符
    s = re.sub(r"[\x00-\x1f\x7f]", "", s)  # 去除控制字符
    s = s.strip(" .")                      # 去除首尾空格/点，避免 '.'/'..' 段
    return s or fallback


def file_md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _common_parts(ver: PackageVersion, pkg: Package) -> list[str]:
    return [
        NAS_BASE_DIRNAME,
        _safe_segment(ver.project_code or settings.PROJECT_CODE),
        _safe_segment(f"{pkg.code}_{pkg.name_zh}", pkg.code or "pkg"),
        _safe_segment(ver.version_no, "V"),
    ]


def _group_key(att: Attachment):
    """附件在归档目录中的归属组（同组即同一个 NAS 目录）。"""
    return ("v", att.version_id) if att.version_id is not None else ("o", att.order_package_id)


def archive_name(att: Attachment, dup_names: set[str]) -> str:
    """附件在 NAS 上的文件名。

    规格要求目录末级使用 {原文件名}，但同一资料包内同名文件（如多个供应商各自的
    "发票.pdf"，COO-05/06/07 明确要求逐份上传）会互相覆盖：NAS 只剩最后一份，
    而数据库与 manifest 仍显示多条 —— 静默丢件且审计核验必然对不上。
    因此仅在该目录内存在重名时，追加内容哈希前 8 位加以区分；不重名者保持原样。
    """
    base = _safe_segment(att.original_name or att.file_name)
    if base not in dup_names:
        return base
    stem, ext = os.path.splitext(base)
    return f"{stem}__{(att.md5 or '')[:8]}{ext}"


def duplicate_names(atts) -> set[str]:
    """返回同组内出现一次以上的安全文件名集合。"""
    seen, dup = set(), set()
    for a in atts:
        n = _safe_segment(a.original_name or a.file_name)
        if n in seen:
            dup.add(n)
        seen.add(n)
    return dup


def _order_parts(op: OrderPackage, pkg: Package, order_no: str) -> list[str]:
    return [
        NAS_BASE_DIRNAME,
        _safe_segment(op.project_code or settings.PROJECT_CODE),
        _safe_segment(f"{pkg.code}_{pkg.name_zh}", pkg.code or "pkg"),
        _safe_segment(order_no, "order"),
    ]


def _local_root() -> str:
    """本地挂载点：以数据库中的运行时配置为准（管理员可在界面修改）。"""
    return nas_config.get_config()["local_root"] or settings.NAS_ROOT


class _LocalBackend:
    """本地目录回退：挂载点模拟（开发环境 / 未配置 S3 时）。"""

    name = "local"

    def reachable(self) -> bool:
        root = _local_root()
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
        return os.path.join(_local_root(), *_common_parts(ver, pkg))

    def order_base(self, op: OrderPackage, pkg: Package, order_no: str) -> str:
        return os.path.join(_local_root(), *_order_parts(op, pkg, order_no))

    def version_target(self, att: Attachment, pkg: Package, ver: PackageVersion, name: str) -> str:
        return os.path.join(self.version_base(ver, pkg), name)

    def order_target(self, att: Attachment, op: OrderPackage, pkg: Package, order_no: str, name: str) -> str:
        return os.path.join(self.order_base(op, pkg, order_no), name)

    def sync_one(self, target: str, src: str, att: Attachment) -> bool:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(src, target)
        return os.path.getsize(target) == att.file_size and file_md5(target) == att.md5

    def write_manifest(self, base: str, lines: list[str]) -> None:
        os.makedirs(base, exist_ok=True)
        with open(os.path.join(base, "manifest.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def manifest_exists(self, base: str) -> bool:
        return os.path.exists(os.path.join(base, "manifest.txt"))

    def display(self) -> str:
        return _local_root()


class _S3Backend:
    """S3 兼容接口后端：MinIO / NAS S3 服务 / 云对象存储。"""

    name = "s3"

    def __init__(self):
        self.cli = s3.client()

    def reachable(self) -> bool:
        return s3.reachable(self.cli)

    def version_base(self, ver: PackageVersion, pkg: Package) -> str:
        return "/".join(_common_parts(ver, pkg))

    def order_base(self, op: OrderPackage, pkg: Package, order_no: str) -> str:
        return "/".join(_order_parts(op, pkg, order_no))

    def version_target(self, att: Attachment, pkg: Package, ver: PackageVersion, name: str) -> str:
        return f"{self.version_base(ver, pkg)}/{name}"

    def order_target(self, att: Attachment, op: OrderPackage, pkg: Package, order_no: str, name: str) -> str:
        return f"{self.order_base(op, pkg, order_no)}/{name}"

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

    def manifest_exists(self, base: str) -> bool:
        return bool(s3.head(self.cli, f"{base}/manifest.txt"))

    def display(self) -> str:
        cfg = nas_config.get_config()
        return f"s3://{cfg['bucket']}@{cfg['endpoint_url']}"


def _backend():
    return _S3Backend() if s3.enabled() else _LocalBackend()


def nas_reachable() -> bool:
    return _backend().reachable()


def nas_target_display() -> str:
    """NAS 目标展示（NAS 状态卡片）。"""
    return _backend().display()


def probe_config(cfg: dict) -> dict:
    """用给定参数试连一次，返回 {ok, detail}；**不修改运行中的配置**。

    保存前先试连，是为了避免"改错了地址却毫无察觉、当晚自动同步静默失败"——
    归档失败意味着该留存的核查证据没有留存，而这类问题往往几周后才被发现。
    错误信息原样带回给管理员：区分"地址不通""密钥不对""桶不存在"全靠它。
    """
    import boto3
    from botocore.config import Config as BotoConfig

    if cfg.get("mode") == "s3":
        if not (cfg.get("endpoint_url") and cfg.get("access_key") and cfg.get("secret_key")):
            return {"ok": False, "detail": "S3 模式需填写端点地址、Access Key 与 Secret Key"}
        try:
            cli = boto3.client(
                "s3",
                endpoint_url=cfg["endpoint_url"],
                aws_access_key_id=cfg["access_key"],
                aws_secret_access_key=cfg["secret_key"],
                region_name=cfg.get("region") or None,
                use_ssl=bool(cfg.get("use_ssl")),
                config=BotoConfig(
                    s3={"addressing_style": "path"},
                    # 试连不重试：管理员在等结果，连不通就该立刻回答，而不是卡十几秒
                    retries={"max_attempts": 1, "mode": "standard"},
                    connect_timeout=5, read_timeout=8,
                ),
            )
            cli.list_buckets()
            bucket = (cfg.get("bucket") or "").strip()
            if not bucket:
                return {"ok": False, "detail": "连接成功，但未填写存储桶名称"}
            try:
                cli.head_bucket(Bucket=bucket)
                return {"ok": True, "detail": f"连接成功，存储桶 {bucket} 可用"}
            except Exception:  # noqa: BLE001
                # 桶不存在不算失败：首次同步时 ensure_bucket 会创建
                return {"ok": True, "detail": f"连接成功；存储桶 {bucket} 尚不存在，首次同步时将自动创建"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "detail": f"连接失败：{e}"}

    root = (cfg.get("local_root") or "").strip()
    if not root:
        return {"ok": False, "detail": "本地模式需填写挂载目录"}
    try:
        os.makedirs(root, exist_ok=True)
        probe = os.path.join(root, ".probe")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return {"ok": True, "detail": f"目录可读写：{root}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"目录不可写：{e}"}


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
    # 重名判定必须基于目录内的全部附件（含此前已同步的），否则新上传的同名文件
    # 会以"看起来不重名"的方式覆盖掉早先归档的那一份
    dup_cache: dict = {}

    def dups_for(att: Attachment) -> set[str]:
        key = _group_key(att)
        if key not in dup_cache:
            col = Attachment.version_id if key[0] == "v" else Attachment.order_package_id
            dup_cache[key] = duplicate_names(db.query(Attachment).filter(col == key[1]).all())
        return dup_cache[key]

    for att in pending:
        try:
            src = os.path.join(settings.UPLOAD_DIR, att.file_name)
            if not os.path.exists(src):
                failures.append({"attachment_id": att.id, "reason": "源文件缺失"})
                continue
            if att.version_id is not None:
                ver = db.get(PackageVersion, att.version_id)
                pkg = db.get(Package, ver.package_id) if ver else None
                if not ver or not pkg:
                    failures.append({"attachment_id": att.id, "reason": "版本/资料包不存在"})
                    continue
                target = backend.version_target(att, pkg, ver, archive_name(att, dups_for(att)))
            elif att.order_package_id is not None:
                op = db.get(OrderPackage, att.order_package_id)
                o = db.get(Order, op.order_id) if op else None
                pkg = db.get(Package, op.package_id) if op else None
                if not op or not o or not pkg:
                    failures.append({"attachment_id": att.id, "reason": "订单/资料包不存在"})
                    continue
                target = backend.order_target(att, op, pkg, o.order_no, archive_name(att, dups_for(att)))
            else:
                failures.append({"attachment_id": att.id, "reason": "无归属版本/订单"})
                continue
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
    # 失败明细只留前 MAX_DETAIL_FAILURES 条：一次大规模失败会产生上万条记录，
    # 整表写入近 1MB JSON 后，sync_records 的 ORDER BY 排序会因行宽过大直接报
    # 1038 Out of sort memory —— 让运维恰好在同步失败时打不开 NAS 状态页。完整明细见日志。
    kept = failures[:MAX_DETAIL_FAILURES]
    details = {"backend": backend.name, "tunnel_ok": True, "failures": kept}
    if len(failures) > MAX_DETAIL_FAILURES:
        details["failures_truncated"] = len(failures) - MAX_DETAIL_FAILURES
        logger.warning("NAS 同步失败 %s 条，详情仅保留前 %s 条：%s",
                       len(failures), MAX_DETAIL_FAILURES, failures[MAX_DETAIL_FAILURES:])
    rec.details = details
    rec.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(rec)
    return rec


def _blank_manifest(backend, base: str, header: str) -> None:
    """把一份"列着文件却没有文件"的旧清单改写为真实内容。

    只在目标上确实已存在清单时才写——避免在全新 NAS 上凭空造出空清单。
    不删除任何东西（同步始终是只增不删），但也绝不让清单继续说谎：
    一个列着 MD5 却没有对应文件的目录，对核查方比空目录更具误导性。
    """
    if not backend.manifest_exists(base):
        return
    backend.write_manifest(base, [
        header,
        f"# generated {datetime.utcnow().isoformat()}",
        "# 本目录当前无已归档文件（原始记录已删除或尚未同步）",
    ])


def _write_manifests(db: Session, backend):
    """为每个已放行版本/订单实例的目录/前缀写 manifest.txt（清单/大小/MD5）。

    只列出**确已归档到当前目标**的附件（nas_synced=True），并且该组一个文件都
    没归档时不写清单。否则会出现"清单列着文件、目录里却没有"的目录——换归档
    目标或上传失败时都会踩到，而这种目录对核查方而言比空目录更糟：它看起来
    完整，只有逐个核对 MD5 时才会发现文件根本不存在。
    """
    released = db.query(PackageVersion).filter(PackageVersion.status == "released").all()
    for ver in released:
        pkg = db.get(Package, ver.package_id)
        if not pkg:
            continue
        base = backend.version_base(ver, pkg)
        # 列出的必须是 NAS 上的实际文件名，否则重名被区分后清单与目录对不上，审计核验会失败
        archived = [a for a in ver.attachments if a.nas_synced]
        if not archived:
            _blank_manifest(backend, base, f"# {pkg.code} {pkg.name_zh} {ver.version_no}")
            continue
        # 重名判定仍基于全部附件：区分后缀必须与 sync 时算出的一致
        dup = duplicate_names(ver.attachments)
        lines = [f"# {pkg.code} {pkg.name_zh} {ver.version_no}",
                 f"# generated {datetime.utcnow().isoformat()}",
                 "# 归档文件名\t字节数\tMD5\t上传原名"]
        for att in archived:
            an = archive_name(att, dup)
            lines.append(f"{an}\t{att.file_size}\t{att.md5}\t{att.original_name}")
        backend.write_manifest(base, lines)

    released_ops = db.query(OrderPackage).filter(
        OrderPackage.status == "released", OrderPackage.locked.is_(True)).all()
    for op in released_ops:
        o = db.get(Order, op.order_id)
        pkg = db.get(Package, op.package_id)
        if not o or not pkg:
            continue
        base = backend.order_base(op, pkg, o.order_no)
        archived = [a for a in op.attachments if a.nas_synced]
        if not archived:
            _blank_manifest(backend, base, f"# {pkg.code} {pkg.name_zh} {o.order_no}")
            continue
        dup = duplicate_names(op.attachments)
        lines = [f"# {pkg.code} {pkg.name_zh} {o.order_no}",
                 f"# generated {datetime.utcnow().isoformat()}",
                 "# 归档文件名\t字节数\tMD5\t上传原名"]
        for att in archived:
            an = archive_name(att, dup)
            lines.append(f"{an}\t{att.file_size}\t{att.md5}\t{att.original_name}")
        backend.write_manifest(base, lines)
