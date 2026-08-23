"""数据库引擎、会话与基础模型。"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
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
    wanted = [("notifications", "params", "TEXT")]
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
                logging.getLogger("app.db").info("已补建索引 %s", idx)
            except Exception:  # noqa: BLE001
                logging.getLogger("app.db").debug("索引 %s 跳过", idx, exc_info=True)
