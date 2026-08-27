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
    ap.add_argument("--check-nas", action="store_true",
                    help="核对 NAS 归档：清单列出的文件是否真的存在")
    ap.add_argument("--fix-nas-manifests", action="store_true",
                    help="把「列着文件却没有文件」的清单改写为真实内容（需配合 --check-nas）")
    ap.add_argument("--verify", action="store_true",
                    help="逐个重算文件 sha256 并与存储名比对，发现内容损坏/篡改")
    args = ap.parse_args()

    updir = settings.UPLOAD_DIR
    if not os.path.isdir(updir):
        print(f"[ERROR] 上传目录不存在：{updir}")
        return 2
    on_disk = {f for f in os.listdir(updir) if os.path.isfile(os.path.join(updir, f))}
    # 剩余空间（第 100 轮）：磁盘写满时上传 507、整套系统随后一起停；巡检该在逼近时就说
    st = os.statvfs(updir)
    free, total = st.f_bavail * st.f_frsize, st.f_blocks * st.f_frsize
    pct = (free / total * 100) if total else 0
    flag = "  [WARN] 剩余不足 10%，请尽快清理或扩容" if pct < 10 else ""
    print(f"  磁盘剩余：{human(free)} / {human(total)}（{pct:.0f}%）{flag}")

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

    # ---- 内容完整性（可选，需读全部文件）----
    # 存储名就是内容的 sha256，因此"内容还对不对"是可以零依赖地验出来的。
    # 第 83 轮实测：把一个证据文件的最后 4 字节改掉（长度不变）——本脚本默认
    # 报"悬空 0 / 孤儿 0"，下载以 200 返回篡改后的内容且无任何提示，
    # 只有 NAS 同步会在**尚未同步**的附件上发现不一致；已同步过的文件以后被
    # 改动就再也没人查了。对一个以"证据完整"为全部价值的系统，这是必须补的一环。
    # 做成可选：生产上可能有数 GB 附件，逐个读一遍不该发生在每次随手执行时；
    # 由 install.sh 装的每周 cron 定期跑，见运维手册 §9。
    if args.verify:
        import hashlib
        import time
        t0 = time.time()
        # 按**物理文件**算一次，而不是按附件行：内容寻址下一个文件可被几十条记录
        # 引用（本库 131 条记录只对应 6 个文件），按行算等于把同一文件哈希几十遍
        bad_files, checked, nbytes = set(), 0, 0
        for fn in sorted(referenced & on_disk):
            path = os.path.join(updir, fn)
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            checked += 1
            nbytes += os.path.getsize(path)
            if h.hexdigest() != os.path.splitext(fn)[0]:
                bad_files.add(fn)
        corrupted = [(aid, fn, orig) for aid, fn, orig in rows if fn in bad_files]
        print(f"\n内容完整性：核对 {checked} 个物理文件 / {human(nbytes)} / {time.time() - t0:.1f}s")
        if bad_files:
            print(f"  损坏的物理文件 {len(bad_files)} 个，波及附件记录 {len(corrupted)} 条")
        print(f"  内容与哈希不符（已损坏或被篡改，证据不可信）：{len(corrupted)}")
        for aid, fn, orig in corrupted[:20]:
            print(f"  附件 {aid}  {orig}  ->  {fn}")
        if len(corrupted) > 20:
            print(f"  …另有 {len(corrupted) - 20} 条")
        if corrupted:
            print("  处理：该文件的每个引用附件都受影响；从 NAS 副本或备份取回同名文件后重跑本检查。")
            return 1

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

    nas_bad = 0
    if args.check_nas:
        nas_bad = check_nas(args.fix_nas_manifests)

    # 悬空记录与归档缺件都属数据完整性问题，用非零退出码让巡检/告警能捕获
    return 1 if (dangling or nas_bad) else 0


def check_nas(fix: bool = False) -> int:
    """核对 NAS 归档：每份 manifest 列出的文件是否真的存在于归档目标。

    代码路径永远发现不了这类问题：订单/版本一旦从库里删除，_write_manifests
    就再也不会访问那个目录，而 NAS 同步是只增不删——留在那里的清单会继续
    逐条列出文件名与 MD5，核查方看到的是一个"看起来完整"的目录。
    因此只能靠巡检从归档侧反向核对。
    """
    import posixpath

    from app.core import nas_config
    from app.services import s3

    cfg = nas_config.get_config()
    print(f"\n=== NAS 归档核对（{nas_config.target_fingerprint(cfg)}）===")
    if cfg["mode"] != "s3":
        root = cfg["local_root"]
        manifests = []
        for dirpath, _dirs, files in os.walk(root):
            if "manifest.txt" in files:
                manifests.append(dirpath)
        listed_total = missing_total = empty_dirs = 0
        for d in manifests:
            with open(os.path.join(d, "manifest.txt"), encoding="utf-8") as f:
                names = [ln.split("\t")[0] for ln in f.read().splitlines()
                         if ln and not ln.startswith("#")]
            miss = [n for n in names if not os.path.exists(os.path.join(d, n))]
            listed_total += len(names)
            missing_total += len(miss)
            if names and len(miss) == len(names):
                empty_dirs += 1
                if fix:
                    with open(os.path.join(d, "manifest.txt"), "w", encoding="utf-8") as f:
                        f.write("# 本目录当前无已归档文件（原始记录已删除或尚未同步）\n")
        print(f"清单 {len(manifests)} 份，列出 {listed_total} 份文件，实际缺失 {missing_total} 份")
        print(f"只有清单、没有任何文件的目录：{empty_dirs} 个")
        return missing_total

    cli = s3.client()
    if not cli:
        print("S3 未启用，跳过")
        return 0
    bucket = cfg["bucket"]
    keys, token = [], None
    while True:
        r = cli.list_objects_v2(Bucket=bucket, **({"ContinuationToken": token} if token else {}))
        keys += [o["Key"] for o in r.get("Contents", [])]
        if not r.get("IsTruncated"):
            break
        token = r["NextContinuationToken"]
    kset = set(keys)
    manifests = [k for k in keys if k.endswith("manifest.txt")]
    listed_total = missing_total = empty_dirs = fixed = 0
    for k in manifests:
        d = posixpath.dirname(k)
        body = cli.get_object(Bucket=bucket, Key=k)["Body"].read().decode("utf-8", "replace")
        names = [ln.split("\t")[0] for ln in body.splitlines() if ln and not ln.startswith("#")]
        miss = [n for n in names if f"{d}/{n}" not in kset]
        listed_total += len(names)
        missing_total += len(miss)
        if names and len(miss) == len(names):
            empty_dirs += 1
            if fix:
                cli.put_object(Bucket=bucket, Key=k,
                               Body="# 本目录当前无已归档文件（原始记录已删除或尚未同步）\n".encode("utf-8"))
                fixed += 1
    print(f"清单 {len(manifests)} 份，列出 {listed_total} 份文件，实际缺失 {missing_total} 份")
    print(f"只有清单、没有任何文件的目录：{empty_dirs} 个")
    if fixed:
        print(f"已改写 {fixed} 份不实清单（未删除任何归档文件）")
    elif empty_dirs:
        print("（如需改写为真实内容，加 --fix-nas-manifests 重新执行）")
    return missing_total


if __name__ == "__main__":
    raise SystemExit(main())
