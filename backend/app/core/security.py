"""密码哈希与 JWT 工具。"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings
from app.core.runtime_secret import get_secret_key, refresh_secret_key
from app.core.snowflake import next_id


def hash_password(password: str) -> str:
    pw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt(rounds=settings.PASSWORD_SALT_ROUNDS)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, role: str, extra: Optional[dict] = None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "role": role, "iat": int(now.timestamp()), "exp": int(expire.timestamp())}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, get_secret_key(), algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, get_secret_key(), algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        # 解码失败时回源刷新一次再试：多进程/多实例下其他进程轮换密钥后，
        # 本进程缓存过期，这里收敛到数据库中的新密钥；真正的无效/过期令牌仍返回 None。
        fresh = refresh_secret_key()
        try:
            return jwt.decode(token, fresh, algorithms=[settings.JWT_ALGORITHM])
        except JWTError:
            return None


def generate_temp_password(length: int = 12) -> str:
    """生成一次性临时密码（管理员重置 / 首次初始化 admin 共用，避免策略漂移）。"""
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def new_api_key(tenant_prefix: str = "coo", key_prefix: str = "sk") -> tuple[str, str]:
    """生成 API Key：明文一次性返回，存储 SHA-256 哈希。

    格式：sk-{tenant_prefix}_{key_prefix}_{random}
    """
    import hashlib, secrets
    rand = secrets.token_urlsafe(24).replace("-", "").replace("_", "")[:32]
    raw = f"sk-{tenant_prefix}_{key_prefix}_{rand}"
    hashed = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, hashed
