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
    NAS_ROOT: str = "./data/nas"                # 本地目录回退模式的目标（未配置 S3 时用）
    MAX_FILE_MB: int = 100
    ALLOWED_EXTENSIONS: str = ""                # 留空则用 constants 默认值

    # NAS 归档（S3 兼容接口，MinIO / 群晖 / 威联通 / 云对象存储）
    S3_ENDPOINT_URL: str = ""                   # 留空则退化为本地目录同步
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_BUCKET: str = "coo-nas"
    S3_REGION: str = "us-east-1"
    S3_USE_SSL: bool = False

    # NAS 同步
    NAS_SYNC_TIME: str = "01:00"
    PROJECT_CODE: str = "Bintelli-US"

    @property
    def S3_ENABLED(self) -> bool:
        return bool(self.S3_ENDPOINT_URL and self.S3_ACCESS_KEY and self.S3_SECRET_KEY)

    # CORS（前端开发地址）
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def model_post_init(self, __context) -> None:
        # 安全加固：SECRET_KEY 仍为默认占位值时给出告警，生产务必用环境变量覆盖
        if self.SECRET_KEY and self.SECRET_KEY.startswith("change-me"):
            import logging
            logging.getLogger("app.config").warning(
                "SECRET_KEY 仍为默认占位值，生产环境请务必通过环境变量 SECRET_KEY 覆盖")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
