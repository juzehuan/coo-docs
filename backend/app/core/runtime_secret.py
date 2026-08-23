"""运行时 JWT 密钥：存于数据库，首次启动自动随机生成，超管可在界面轮换。

背景：SECRET_KEY 曾以占位值硬编码在 docker-compose.yml 并提交仓库，任何能读到
仓库的人都可自签管理员令牌。改为：密钥不进仓库、不进环境变量，首次启动用
secrets.token_urlsafe(48) 生成后写入 system_settings 表；轮换后所有已签发令牌
立即失效（等效全员强制重新登录）。

进程内缓存避免每次请求查库；轮换通过 rotate_secret_key() 同步刷新缓存。
注意：当前部署为单进程 uvicorn，多进程/多实例部署时轮换后其余进程需重启
（或将缓存改为带 TTL）才能感知新密钥。
"""
import secrets
import threading

_KEY_NAME = "jwt_secret_key"
_cache: str | None = None
_lock = threading.Lock()


def _save(db, value: str) -> str:
    """唯一的落库路径：upsert system_settings 中的密钥行。"""
    from app.models import SystemSetting
    row = db.get(SystemSetting, _KEY_NAME)
    if row:
        row.value = value
    else:
        db.add(SystemSetting(key=_KEY_NAME, value=value))
    db.commit()
    return value


def _load_or_create(db) -> str:
    from app.models import SystemSetting
    row = db.get(SystemSetting, _KEY_NAME)
    if row and row.value:
        return row.value
    return _save(db, secrets.token_urlsafe(48))


def get_secret_key() -> str:
    """获取当前生效的 JWT 密钥（首次调用时生成并落库）。"""
    global _cache
    if _cache:
        return _cache
    with _lock:
        if _cache:
            return _cache
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            _cache = _load_or_create(db)
        finally:
            db.close()
        return _cache


def refresh_secret_key() -> str:
    """强制从数据库重读密钥并刷新缓存。

    供令牌解码失败时回源确认：多进程/多实例部署下，其他进程轮换密钥后，
    本进程借此收敛到新密钥（旧令牌仍会正确失效）。
    """
    global _cache
    with _lock:
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            _cache = _load_or_create(db)
        finally:
            db.close()
        return _cache


def rotate_secret_key(db, value: str | None = None) -> None:
    """轮换密钥（value 为空则随机生成）；所有已签发令牌随即失效。"""
    global _cache
    new_value = _save(db, value or secrets.token_urlsafe(48))
    with _lock:
        _cache = new_value
