"""安全的 JSON 响应编码。

Snowflake 生成的 int64 主键远大于 JavaScript 的 MAX_SAFE_INTEGER（2^53-1），
若以数字下发会被前端截断从而丢失精度（列表点击进入详情、上传/审核等都会失效）。
这里将超过安全范围的大整数统一序列化为字符串，保证前端可精确回传 ID。
"""
import json
from typing import Any

from fastapi.responses import JSONResponse

MAX_SAFE_INTEGER = 2**53 - 1


def _safe_int(value: Any) -> Any:
    """递归地把超过 JS 安全整数范围的 int 转为 str，其余保持原样。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value) if value > MAX_SAFE_INTEGER else value
    if isinstance(value, (list, tuple)):
        return [_safe_int(v) for v in value]
    if isinstance(value, dict):
        return {k: _safe_int(v) for k, v in value.items()}
    return value


class SafeIntJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(
            _safe_int(content),
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")