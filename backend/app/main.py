"""FastAPI 应用入口。"""
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import DataError

from app.core.config import settings
from app.core.json import SafeIntJSONResponse
from app.core.ratelimit import RateLimitMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.db import SessionLocal, init_db
from app.api import audit, auth, controlled, dashboard, factories, nas, notifications, orders, org, packages, todo


def create_app() -> FastAPI:
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
    app.add_middleware(RateLimitMiddleware)

    # 兜底：字段超出数据库列宽等数据类错误应回 400 而非 500。
    # schemas 已对各字段声明 max_length 做精确校验，此处覆盖遗漏与未来新增字段。
    @app.exception_handler(DataError)
    def _data_error(request, exc: DataError):
        logging.getLogger("app").warning("数据校验失败 %s: %s", request.url.path, exc)
        return SafeIntJSONResponse(status_code=400, content={"detail": "字段内容过长或格式不正确，请检查后重试"})

    # 确保存储目录存在
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.NAS_ROOT, exist_ok=True)

    for m in (auth, org, packages, orders, factories, dashboard, audit, nas, controlled, todo, notifications):
        app.include_router(m.router, prefix=settings.API_PREFIX)

    @app.get("/health")
    def health():
        return {"status": "ok", "app": settings.APP_NAME}

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
