"""数据库引擎、会话与基础模型。"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# 连接池：此前完全用 SQLAlchemy 的默认值（pool_size=5 / max_overflow=10 = 上限 15），
# 也就是没人选过这个数。这里显式选定，并写清依据。
#
# **第 78 轮先把它提到 20+20=40「与 uvicorn 线程池对齐」，第二次压测把这个理由证伪了，
# 现已改回 15 并保留显式声明。** 逐级加压实测（审计导出，单请求基线 1.8s）：
#
#   并发   墙钟    旁观者的普通请求    coo 库连接数
#     1    1.8s    0.3s               3
#     5   18.9s    1.2s               5
#    10   40.0s    1.2s              10
#    20   全部超时  12.9s             23
#    40   全部超时  旁观者也超时        40
#
# 关键读数：**并发 10 时只用了 10 个连接，却已经耗时 40 秒**——瓶颈是 CPU
# （单进程、xlsx 生成 CPU 密集），根本不是连接数。把池放大到 40 的后果是
# 让 40 个请求全部挤进来抢同一个 CPU，一起垮；而池小反而是**天然的准入阀门**：
# 多余请求在池上排队、超时后拿到 503「服务繁忙」（见 main.py 的处理器），
# 已经进来的那批还能按时做完。**放大池子让过载表现更糟，不是更好。**
#
# 因此维持 5+10=15：对日常流量（实测峰值 5 个连接）绰绰有余，
# 又能在过载时尽早把多余请求挡在外面。
# 真正要解决"并发重导出"需要给导出类端点单独限并发或改异步任务，见 P2。
engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    # 导入模型以确保注册到 Base.metadata
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    _ensure_indexes()


def _ensure_columns() -> None:
    """为已存在的表补建后加的列。

    create_all 只建表不改表：历史库不会自动获得新增字段，而代码一旦引用就会
    直接 500。与补索引同理，逐条尝试、已存在则跳过。
    """
    import logging
    from sqlalchemy import inspect, text

    # (表, 列, DDL 类型)
    wanted = [
        ("notifications", "params", "TEXT"),
        # 随单/公司级标记：历史库一律按"随单"处理，与改动前行为一致
        ("packages", "per_order", "TINYINT(1) NOT NULL DEFAULT 1"),
        # 引用型订单实例指向的资料包版本
        ("order_packages", "source_version_id", "BIGINT NULL"),
        # 密码变更时刻，用于作废此前签发的令牌
        ("users", "password_changed_at", "DATETIME NULL"),
    ]
    insp = inspect(engine)
    with engine.connect() as conn:
        for table, column, ddl in wanted:
            try:
                if table not in insp.get_table_names():
                    continue
                if any(c["name"] == column for c in insp.get_columns(table)):
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                conn.commit()
                logging.getLogger("app.db").info("已补建列 %s.%s", table, column)
            except Exception:  # noqa: BLE001
                logging.getLogger("app.db").warning("补列 %s.%s 失败", table, column, exc_info=True)


def _ensure_indexes() -> None:
    """为已存在的表补建后加的索引。

    create_all 只建表不改表，历史库不会自动获得新增的 index=True。
    这里逐条尝试创建，已存在则忽略（各数据库报错码不同，统一吞掉）。
    """
    import logging
    from sqlalchemy import inspect, text

    # (表, 列, 索引名)。历史库靠这里补齐 create_all 不会追加的索引。
    wanted = [
        ("sync_records", "started_at", "ix_sync_records_started_at"),
        # 订单列表按 created_at DESC 排序+分页：缺索引时每次翻页都对全量可见订单 filesort
        ("orders", "created_at", "ix_orders_created_at"),
        # 受控区/工作台/待办按状态过滤：缺索引时是全表扫描
        ("order_packages", "status", "ix_order_packages_status"),
        ("package_versions", "status", "ix_package_versions_status"),
        # NAS 待同步计数：/nas/status 每次打开都要数一遍，两年 1.2 万附件下为全表扫描
        ("attachments", "nas_synced", "ix_attachments_nas_synced"),
    ]
    # 复合索引：单列索引无法同时服务"按 factory_id 过滤 + 按 created_at 排序"，
    # MySQL 只会用其一，另一半仍要 filesort（实测订单列表补了 created_at 单列索引后
    # 执行计划依旧是 Using filesort）。列顺序须与查询一致：先等值/范围过滤列，后排序列。
    composite = [("orders", "factory_id, created_at", "ix_orders_factory_created")]

    log = logging.getLogger("app.db")
    insp = inspect(engine)
    with engine.connect() as conn:
        for table, column, idx in wanted + composite:
            try:
                if table not in insp.get_table_names():
                    continue
                if any(i["name"] == idx for i in insp.get_indexes(table)):
                    continue
                conn.execute(text(f"CREATE INDEX {idx} ON {table} ({column})"))
                conn.commit()
                log.info("已补建索引 %s", idx)
            except Exception:  # noqa: BLE001
                # 这里保持 debug：各数据库对"索引已存在"的报错码不同，
                # 按异常分类必然误报。真正的判定放在下面的收尾校验里。
                log.debug("索引 %s 创建异常（可能已存在）", idx, exc_info=True)

    # 收尾校验：不去猜异常的含义，直接看**最终有没有**。
    #
    # 此前建索引失败一律记在 debug，而默认日志级别是 INFO——第 75 轮实测：
    # 用一个必然失败的索引定义跑一遍，**INFO 级别下零输出**，服务照常启动、
    # 照常提供服务，只是从此少了一个索引。症状要等规模上来才显现（变慢），
    # 而那时没有任何线索指向"某个索引当初没建成"。
    # 同一文件里的 _ensure_columns 对同类失败记的是 WARNING，两者本就不该不一致。
    #
    # 第 74 轮已实测这些索引在真实规模下的作用：5 万订单时它们让订单列表从
    # 全表扫描+filesort 变成只扫 62 行的反向索引扫描；30 万审计日志同理。
    # 也就是说"少一个索引"不是无关痛痒，而是把一个已验证的优化悄悄拿掉。
    insp2 = inspect(engine)
    missing = []
    for table, column, idx in wanted + composite:
        if table not in insp2.get_table_names():
            continue
        if not any(i["name"] == idx for i in insp2.get_indexes(table)):
            missing.append(f"{idx}({table}.{column})")
    if missing:
        log.warning("以下索引未建成，规模上来后相关查询会退化为全表扫描/文件排序，"
                    "请人工建索引或检查数据库权限：%s", "、".join(missing))
    else:
        log.info("索引核对通过：%d 个应有索引全部就位", len(wanted) + len(composite))
