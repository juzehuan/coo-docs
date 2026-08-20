"""FastAPI 应用入口。"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db import SessionLocal, init_db
from app.api import audit, auth, controlled, dashboard, nas, org, packages


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 确保存储目录存在
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.NAS_ROOT, exist_ok=True)

    for m in (auth, org, packages, dashboard, audit, nas, controlled):
        app.include_router(m.router, prefix=settings.API_PREFIX)

    @app.get("/health")
    def health():
        return {"status": "ok", "app": settings.APP_NAME}

    @app.on_event("startup")
    def _startup():
        init_db()
        db = SessionLocal()
        try:
            from app.services.seed import seed
            seed(db)
        finally:
            db.close()

    return app


app = create_app()
