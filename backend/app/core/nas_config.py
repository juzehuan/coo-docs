"""NAS 归档配置：存于数据库，管理员在界面维护，环境变量作为初始默认值。

背景：NAS 的接入方式（S3 端点、密钥、桶名、本地挂载点、每日同步时间）此前只能
改 docker-compose 的环境变量并重启整套服务。而这些恰恰是**交付现场才知道**的信息
——客户的群晖/威联通地址、访问密钥、桶名，换一台 NAS 或轮换密钥都要运维介入改文件、
重启容器。管理员在界面上改不了自己系统的归档目标，这条路本身就不合理。

改为：配置以 JSON 存 system_settings 表（键 nas_config），进程内缓存避免每次查库；
库里没有记录时回退到环境变量（老部署原样工作，升级不需要任何操作）。

密钥的处理：`secret_key` 只写不读——接口返回的是掩码，前端提交时留空表示"保持不变"。
这样密钥不会因为一次页面加载就被回显到浏览器，也不会出现在前端的网络面板里。
"""
import json
import logging
import threading

from app.core.config import settings

logger = logging.getLogger(__name__)

_KEY_NAME = "nas_config"
_cache: dict | None = None
_lock = threading.Lock()

# 掩码占位：前端展示用，提交时若原样回传则视为"未修改"
MASK = "********"

FIELDS = (
    "mode", "endpoint_url", "access_key", "secret_key", "bucket", "region",
    "use_ssl", "local_root", "sync_time", "auto_sync",
)


def _from_env() -> dict:
    """环境变量默认值：库中无记录时使用，保持老部署行为不变。"""
    return {
        "mode": "s3" if settings.S3_ENABLED else "local",
        "endpoint_url": settings.S3_ENDPOINT_URL,
        "access_key": settings.S3_ACCESS_KEY,
        "secret_key": settings.S3_SECRET_KEY,
        "bucket": settings.S3_BUCKET,
        "region": settings.S3_REGION,
        "use_ssl": settings.S3_USE_SSL,
        "local_root": settings.NAS_ROOT,
        "sync_time": settings.NAS_SYNC_TIME,
        "auto_sync": True,
    }


def _normalize(raw: dict) -> dict:
    cfg = _from_env()
    for k in FIELDS:
        if k in raw and raw[k] is not None:
            cfg[k] = raw[k]
    cfg["mode"] = "s3" if cfg.get("mode") == "s3" else "local"
    cfg["use_ssl"] = bool(cfg.get("use_ssl"))
    cfg["auto_sync"] = bool(cfg.get("auto_sync"))
    for k in ("endpoint_url", "access_key", "secret_key", "bucket", "region", "local_root", "sync_time"):
        cfg[k] = (cfg.get(k) or "").strip()
    return cfg


def _load(db) -> dict:
    from app.models import SystemSetting
    row = db.get(SystemSetting, _KEY_NAME)
    if not row or not row.value:
        return _from_env()
    try:
        return _normalize(json.loads(row.value))
    except (ValueError, TypeError):
        logger.warning("nas_config 内容非法，回退环境变量默认值")
        return _from_env()


def get_config() -> dict:
    """读取当前配置（带进程内缓存）。

    调用方可能处在无 db 会话的上下文（如调度线程、s3 客户端构建），
    这里自行开一个短会话读取，读到后缓存。
    """
    global _cache
    if _cache is not None:
        return _cache
    with _lock:
        if _cache is None:
            from app.db import SessionLocal
            db = SessionLocal()
            try:
                _cache = _load(db)
            finally:
                db.close()
    return _cache


def save_config(db, patch: dict) -> dict:
    """写入配置并刷新缓存；secret_key 为空或仍是掩码时保留原值。"""
    from app.models import SystemSetting
    global _cache
    cur = _load(db)
    new = dict(cur)
    for k in FIELDS:
        if k in patch and patch[k] is not None:
            new[k] = patch[k]
    incoming = (patch.get("secret_key") or "").strip()
    if not incoming or incoming == MASK:
        new["secret_key"] = cur["secret_key"]   # 未填写 = 保持不变，避免把密钥清空
    new = _normalize(new)

    row = db.get(SystemSetting, _KEY_NAME)
    payload = json.dumps(new, ensure_ascii=False)
    if row:
        row.value = payload
    else:
        db.add(SystemSetting(key=_KEY_NAME, value=payload))
    db.commit()
    with _lock:
        _cache = new
    return new


def masked(cfg: dict) -> dict:
    """对外输出：密钥以掩码代替，只告知"是否已设置"。"""
    out = {k: cfg.get(k) for k in FIELDS}
    out["secret_key"] = MASK if cfg.get("secret_key") else ""
    return out


def s3_enabled(cfg: dict | None = None) -> bool:
    c = cfg or get_config()
    return c["mode"] == "s3" and bool(c["endpoint_url"] and c["access_key"] and c["secret_key"])
