"""FastAPI 应用入口。"""
import logging
import os
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import DataError, IntegrityError, OperationalError, TimeoutError as SATimeoutError

from app.core.config import settings
from app.core.i18n import LangMiddleware
from app.core.json import SafeIntJSONResponse
from app.core.ratelimit import RateLimitMiddleware
from app.core.reqlog import RequestLogMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.db import SessionLocal, engine, init_db
from app.api import audit, auth, controlled, dashboard, exports, factories, nas, notifications, orders, org, packages, todo


def _setup_logging() -> None:
    """统一日志格式：带时间戳、级别与来源。

    默认配置下应用日志既无时间也无来源，导出或聚合后无法定位事件发生时刻。
    """
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )


def create_app() -> FastAPI:
    _setup_logging()
    # 用安全编码器避免 Snowflake 大整数在序列化时经 JS 精度丢失
    app = FastAPI(title=settings.APP_NAME, version="1.0.0",
                  default_response_class=SafeIntJSONResponse)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    # 语言上下文需在业务代码取名之前就绪
    app.add_middleware(LangMiddleware)
    app.add_middleware(RateLimitMiddleware)
    # 最后添加即最外层：限流拒绝(429)与所有异常响应同样会被记录
    app.add_middleware(RequestLogMiddleware)

    # 兜底：字段超出数据库列宽等数据类错误应回 400 而非 500。
    # schemas 已对各字段声明 max_length 做精确校验，此处覆盖遗漏与未来新增字段。
    @app.exception_handler(DataError)
    def _data_error(request, exc: DataError):
        logging.getLogger("app").warning("数据校验失败 %s: %s", request.url.path, exc)
        return SafeIntJSONResponse(status_code=400, content={"detail": "字段内容过长或格式不正确，请检查后重试"})

    # 唯一约束冲突应回 400 而非 500。
    #
    # 各创建接口都做了"先查存在再插入"的预检并回 400（订单号已存在 / 用户名已存在 …），
    # 但检查与插入之间存在时间窗，并发请求会双双通过预检、由数据库的唯一索引兜住，
    # 而 IntegrityError 此前**没有任何处理器**，直接变成裸 500 "Internal Server Error"。
    #
    # 第 67 轮实测（8 个并发请求用同一个唯一键创建）：
    #   订单   1×201 · 6×400 · **1×500**
    #   资料包 1×201 · 2×400 · **5×500**
    #   用户   1×201 · **7×500**  ← 8 个里 7 个是 500
    # 用户创建最严重，因为预检之后要跑一次 bcrypt 哈希（约 200ms），
    # 这段耗时把时间窗撑到几乎必然命中。
    #
    # 真实触发场景不必是攻击：慢网下重复点一次提交、超时后重试（见第 65 轮）、
    # 两个管理员同时建同一个部门，都会走到这里。而用户看到的是"Internal Server Error"
    # ——一个让人以为系统坏了的提示，正确答案其实只是"这个编号已经有了"。
    #
    # 关键是**用户不应该能分辨自己走的是预检还是竞态**：因此这里回同样的 400、
    # 同样的文案。MySQL 的 1062 报错里带唯一键名（形如 `users.ix_users_username`），
    # 据此映射到与预检一致的措辞；认不出来时给通用文案，不回显数据库原文
    # （原文含冲突的具体取值，不必要地暴露给调用方）。
    _UNIQUE_HINTS = {
        "users": "用户名已存在",
        "orders": "订单号已存在",
        "packages": "资料包编号已存在",
        "factories": "工厂编码已存在",
        "departments": "部门编码已存在",
    }

    @app.exception_handler(IntegrityError)
    def _integrity_error(request, exc: IntegrityError):
        raw = str(getattr(exc, "orig", None) or exc)
        # 外键失败（MySQL 1452）与唯一冲突（1062）是两回事：第 97 轮实测
        # owner_user_id=-1 被报成"已存在相同的记录"，用户会去找根本不存在的重复项
        if "1452" in raw or "foreign key constraint fails" in raw.lower():
            logging.getLogger("app").warning("外键约束失败 %s: %s", request.url.path, raw)
            return SafeIntJSONResponse(status_code=400, content={
                "detail": "所引用的记录不存在或已被删除（如负责人、工厂、部门），请刷新后重新选择"})
        logging.getLogger("app").warning("唯一约束冲突 %s: %s", request.url.path, raw)
        m = re.search(r"for key '([^']+)'", raw)
        key = (m.group(1) if m else "").lower()
        head = key.split(".")[0]
        detail = "已存在相同的记录，请刷新后确认"
        for table, msg in _UNIQUE_HINTS.items():
            if head == table or key.startswith(f"ix_{table}_") or f".ix_{table}_" in key:
                detail = msg
                break
        return SafeIntJSONResponse(status_code=400, content={"detail": detail})

    # 连接池耗尽同样是"暂时性、可重试"，也应回 503。
    #
    # 关键在于 **`sqlalchemy.exc.TimeoutError` 不是 `OperationalError` 的子类**
    # （第 78 轮实测确认，它直接继承 SQLAlchemyError），因此下面那个 503 处理器
    # 接不住它——池一旦耗尽，用户拿到的是**裸 500 "Internal Server Error"**。
    # 而第 23 轮设立那个处理器的理由恰恰适用于此：500 会把运维引向"代码有 bug"
    # 的排查方向，且裸 500 无结构、前端取不到 detail，用户只看到笼统报错。
    @app.exception_handler(SATimeoutError)
    def _pool_exhausted(request, exc: SATimeoutError):
        logging.getLogger("app").error("数据库连接池耗尽 %s: %s", request.url.path, exc)
        return SafeIntJSONResponse(
            status_code=503,
            content={"detail": "服务繁忙，请稍后重试"},
        )

    # 数据库暂时不可用（重启、网络抖动）应回 503 而非 500：
    # 503 表示"暂时性、可重试"，500 会把运维引向"代码有 bug"的排查方向；
    # 且裸 500 返回的是无结构文本，前端取不到 detail，用户只看到笼统报错。
    @app.exception_handler(OperationalError)
    def _db_unavailable(request, exc: OperationalError):
        logging.getLogger("app").error("数据库不可用 %s: %s", request.url.path, exc)
        return SafeIntJSONResponse(
            status_code=503,
            content={"detail": "数据库暂时不可用，请稍后重试"},
        )

    # 确保存储目录存在
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.NAS_ROOT, exist_ok=True)

    for m in (auth, org, packages, orders, factories, dashboard, audit, nas, controlled, todo, notifications, exports):
        app.include_router(m.router, prefix=settings.API_PREFIX)

    @app.get("/health")
    def health():
        """健康检查：必须真正探测数据库。

        只返回静态字符串的健康检查是无效的 —— 数据库宕机时全部业务接口 500，
        它却仍报告 200，监控不告警、编排不重启、负载均衡继续打流量进来。
        用最轻量的 SELECT 1 探活，不可用时返回 503 让外部能据此判断。
        """
        from sqlalchemy import text
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as e:  # noqa: BLE001
            logging.getLogger("app").warning("健康检查失败：数据库不可达 %s", e)
            return SafeIntJSONResponse(
                status_code=503,
                content={"status": "unavailable", "app": settings.APP_NAME, "db": "down"},
            )
        return {"status": "ok", "app": settings.APP_NAME, "db": "up"}

    @app.on_event("startup")
    def _startup():
        init_db()
        # 预热运行时 JWT 密钥：首次启动生成随机密钥并落库（不再依赖仓库/环境变量中的固定值）
        from app.core.runtime_secret import get_secret_key
        get_secret_key()
        db = SessionLocal()
        try:
            from app.services.seed import seed
            seed(db)
        finally:
            db.close()
        # NAS 归档后端：启用 S3 时确保存储桶存在
        from app.services import s3
        if s3.enabled():
            s3.ensure_bucket()
        # 这两个后台线程是"全系统只该跑一份"的：多进程部署下每个进程各起一份，
        # 会把当日 NAS 同步跑 N 遍、让 N 个 worker 争抢同一批导出作业。
        # 用数据库命名锁选出主进程；非主进程只记录告警、不启动它们。
        from app.core.singleton import is_primary
        if is_primary():
            # 每日定时自动同步 NAS（此前 NAS_SYNC_TIME 无调度器引用，auto 同步从不执行）
            from app.services.scheduler import start_nas_sync_scheduler
            start_nas_sync_scheduler()
            # 异步导出作业 worker。放在路由注册之后启动，确保各 api 模块已把
            # 自己的导出类型注册进来（注册发生在模块导入时）。
            from app.services.export_jobs import start_worker
            start_worker()
        else:
            logging.getLogger("app").warning(
                "非主进程：已跳过 NAS 定时同步与导出 worker 的启动")

    return app


app = create_app()
