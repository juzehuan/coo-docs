#!/usr/bin/env python3
"""附件存储一致性巡检（容器内执行）。

附件按内容 sha256 命名落盘，数据库记录与物理文件应当一一对应。两类偏差：

1. **悬空记录**（库有记录、磁盘无文件）——证据丢失，审计调阅会 404。属紧急问题，
   必须人工核查（通常需从 NAS 副本或备份恢复）。NAS 同步也会把它报为「源文件缺失」。
2. **孤儿文件**（磁盘有文件、库无记录）——不影响正确性，但会静默占用数据盘。
   常见来源：数据库回滚/恢复到较早快照、直接用 SQL 清理记录、写库失败的残留。

用法（默认只报告，不删除）：
    docker compose exec backend python scripts/storage_check.py
    docker compose exec backend python scripts/storage_check.py --purge-orphans   # 确认后回收
"""
import argparse
import os
import sys

sys.path.insert(0, "/app")

from app.core.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Attachment  # noqa: E402


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--purge-orphans", action="store_true", help="删除孤儿文件（默认仅报告）")
    args = ap.parse_args()

    updir = settings.UPLOAD_DIR
    if not os.path.isdir(updir):
        print(f"[ERROR] 上传目录不存在：{updir}")
        return 2
    on_disk = {f for f in os.listdir(updir) if os.path.isfile(os.path.join(updir, f))}

    db = SessionLocal()
    try:
        rows = db.query(Attachment.id, Attachment.file_name, Attachment.original_name).all()
    finally:
        db.close()
    referenced = {r[1] for r in rows}

    dangling = [r for r in rows if r[1] not in on_disk]
    orphans = sorted(on_disk - referenced)
    orphan_bytes = sum(os.path.getsize(os.path.join(updir, f)) for f in orphans)

    print(f"上传目录：{updir}")
    print(f"  磁盘文件 {len(on_disk)} 个 · 数据库引用 {len(referenced)} 个（附件记录 {len(rows)} 条）")

    print(f"\n悬空记录（证据丢失，需人工恢复）：{len(dangling)}")
    for aid, fn, orig in dangling[:20]:
        print(f"  附件 {aid}  {orig}  ->  缺失文件 {fn}")
    if len(dangling) > 20:
        print(f"  …另有 {len(dangling) - 20} 条")

    print(f"\n孤儿文件（可回收）：{len(orphans)}，合计 {human(orphan_bytes)}")
    for f in orphans[:20]:
        print(f"  {f}")
    if len(orphans) > 20:
        print(f"  …另有 {len(orphans) - 20} 个")

    if args.purge_orphans and orphans:
        removed = 0
        for f in orphans:
            try:
                os.remove(os.path.join(updir, f))
                removed += 1
            except OSError as e:
                print(f"  [WARN] 删除失败 {f}: {e}")
        print(f"\n已回收 {removed} 个孤儿文件，释放 {human(orphan_bytes)}")
    elif orphans:
        print("\n（如需回收，加 --purge-orphans 重新执行）")

    # 悬空记录属数据完整性问题，用非零退出码让巡检/告警能捕获
    return 1 if dangling else 0


if __name__ == "__main__":
    raise SystemExit(main())
