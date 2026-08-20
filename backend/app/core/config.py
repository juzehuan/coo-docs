"""应用配置（pydantic-settings）。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 基础
    APP_NAME: str = "COO 资料收集平台"
    API_PREFIX: str = "/api"
    DEBUG: bool = False

    # 数据库：默认 SQLite 便于本地开发；生产改为 MySQL
    # MySQL 示例: mysql+pymysql://coo:password@mysql:3306/coo?charset=utf8mb4
    DATABASE_URL: str = "sqlite:///./coo.db"

    # 安全
    SECRET_KEY: str = "change-me-in-production-please-use-a-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 会话超时 8h
    PASSWORD_SALT_ROUNDS: int = 12
    MAX_LOGIN_FAILURES: int = 5
    LOGIN_LOCK_MINUTES: int = 30

    # 文件存储
    UPLOAD_DIR: str = "./data/uploads"          # 云端主存储
    NAS_ROOT: str = "./data/nas"                # 工厂本地 NAS 挂载点（开发时用本地目录模拟）
    MAX_FILE_MB: int = 100
    ALLOWED_EXTENSIONS: str = ""                # 留空则用 constants 默认值

    # NAS 同步
    NAS_SYNC_TIME: str = "01:00"
    PROJECT_CODE: str = "Bintelli-US"

    # CORS（前端开发地址）
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
