"""应用配置（pydantic-settings）。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 基础
    APP_NAME: str = "COO 资料收集平台"
    API_PREFIX: str = "/api"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"      # 日志级别；DEBUG 会同时打开健康检查等噪音日志

    # 数据库：默认 SQLite 便于本地开发；生产改为 MySQL
    # MySQL 示例: mysql+pymysql://coo:password@mysql:3306/coo?charset=utf8mb4
    DATABASE_URL: str = "sqlite:///./coo.db"

    # 安全
    # 注意：JWT 密钥不在配置中——存于数据库（system_settings 表），首次启动自动随机生成，
    # 超管可在「组织管理 → 安全设置」界面轮换。见 core/runtime_secret.py。设置 SECRET_KEY 环境变量无任何效果。
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
    NAS_SYNC_TIME: str = "01:00"       # 站点本地时间（TIMEZONE），非容器 UTC 时钟
    PROJECT_CODE: str = "Bintelli-US"

    # 站点时区：NAS 定时同步与超期判断按此时区计算（部署于曼谷/工厂在泰国）
    TIMEZONE: str = "Asia/Bangkok"

    # 种子数据：演示账号（公开已知口令）与示例订单必须**显式开启**。
    # 默认 false 是安全默认值：忘记配置的部署不会平白多出一批公开口令的账号，
    # 而是只创建 admin 并把随机初始口令打印到启动日志（仅一次）。
    # 开发/验收环境显式设置 SEED_DEMO_DATA=true 即可恢复演示数据。
    SEED_DEMO_DATA: bool = False

    @property
    def S3_ENABLED(self) -> bool:
        return bool(self.S3_ENDPOINT_URL and self.S3_ACCESS_KEY and self.S3_SECRET_KEY)

    # CORS（前端开发地址）
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
