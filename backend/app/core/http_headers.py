"""下载响应头辅助。

Content-Disposition 里直接拼接用户可控的订单号/资料包编号会出问题：
- 含中文或空格 → HTTP 头只能是 latin-1，编码失败直接 500（中文订单号很常见）；
- 含换行 → 协议层拒绝，整个响应失败（502）；
- 含引号 → 生成畸形头部，浏览器解析出错误的文件名。
按 RFC 6266 同时给出 ASCII 回退的 filename 与 UTF-8 的 filename*。
"""
import re
from urllib.parse import quote

_UNSAFE = re.compile(r'[^A-Za-z0-9._\-]')


def content_disposition(filename: str) -> str:
    """构造安全的 attachment 头，兼容中文与特殊字符文件名。"""
    name = (filename or "download").strip() or "download"
    ascii_fallback = _UNSAFE.sub("_", name) or "download"
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(name, safe='')}"
