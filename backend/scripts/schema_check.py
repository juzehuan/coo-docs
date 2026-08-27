# -*- coding: utf-8 -*-
"""数据库结构自检：应有的索引与后加的列是否都在位。

为什么需要它：`_ensure_indexes` 在启动时尽力补建，但历史库、权限不足、
锁等待等情况都可能让某个索引建不出来。第 75 轮之前，这类失败**在默认日志
级别下零输出**——服务照常启动、照常提供服务，只是从此少了一个索引，
症状要等规模上来才显现（变慢），而那时没有任何线索指向真正的原因。

第 74 轮已实测这些索引在真实规模下的作用：5 万订单时它们让订单列表从
全表扫描 + filesort 变成只扫 62 行的反向索引扫描；30 万条审计日志同理。

用法（与 storage_check.py 同：**按退出码接监控**）：
    docker compose exec -T backend python /app/scripts/schema_check.py
    退出码 0 = 全部就位；1 = 有缺失（输出列出具体是哪些）
"""
import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import inspect  # noqa: E402

from app.db import engine, _ensure_columns, _ensure_indexes  # noqa: E402


def _expected():
    """从 db.py 的定义里取应有清单，避免这里再抄一份而两处跑偏（第 72 轮的教训）。"""
    import inspect as pyi
    idx_src = pyi.getsource(_ensure_indexes)
    col_src = pyi.getsource(_ensure_columns)
    idxs = re.findall(r'\("(\w+)",\s*"([^"]+)",\s*"(\w+)"\)', idx_src)
    cols = re.findall(r'\("(\w+)",\s*"(\w+)",\s*"(\w+)"\)', col_src)
    return idxs, cols


def main() -> int:
    idxs, cols = _expected()
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    bad = []

    print(f"索引：应有 {len(idxs)} 个")
    for table, column, idx in idxs:
        if table not in tables:
            print(f"  ✗ {idx:<32} 表 {table} 不存在"); bad.append(idx); continue
        ok = any(i["name"] == idx for i in insp.get_indexes(table))
        print(f"  {'✓' if ok else '✗'} {idx:<32} {table}.{column}")
        if not ok:
            bad.append(idx)

    print(f"\n后加的列：应有 {len(cols)} 个")
    for table, column, _ddl in cols:
        if table not in tables:
            print(f"  ✗ {table}.{column:<24} 表不存在"); bad.append(f"{table}.{column}"); continue
        ok = any(c["name"] == column for c in insp.get_columns(table))
        print(f"  {'✓' if ok else '✗'} {table}.{column}")
        if not ok:
            bad.append(f"{table}.{column}")

    print()
    if bad:
        print(f"[FAIL] {len(bad)} 项缺失：{'、'.join(bad)}")
        print("       索引缺失会让规模上来后的查询退化为全表扫描/文件排序；")
        print("       请检查数据库账号是否有 INDEX 权限，或人工补建后重跑本脚本。")
        return 1
    print("[OK] 数据库结构自检通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
