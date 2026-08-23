"""FastAPI 应用入口。"""
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import DataError, OperationalError

from app.core.config import settings
from app.core.i18n import LangMiddleware
from app.core.json import SafeIntJSONResponse
from app.core.ratelimit import RateLimitMiddleware
from app.core.reqlog import RequestLogMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.db import SessionLocal, engine, init_db
from app.api import audit, auth, controlled, dashboard, factories, nas, notifications, orders, org, packages, todo


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

    for m in (auth, org, packages, orders, factories, dashboard, audit, nas, controlled, todo, notifications):
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
        # 每日定时自动同步 NAS（此前 NAS_SYNC_TIME 无调度器引用，auto 同步从不执行）
        from app.services.scheduler import start_nas_sync_scheduler
        start_nas_sync_scheduler()

    return app


app = create_app()
