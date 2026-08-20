"""全局安全响应头中间件。

对应落地方案的「八、风险控制与保障」：即使未做应用内防护，
也先保证响应层基础安全头（防点击劫持 / MIME 嗅探 / 信息泄露等），
并收敛浏览器端跨源能力与打开器隔离，降低 XSS / 数据外带风险。
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """为所有 API 响应注入基础安全响应头（缺失时才补，不覆盖显式设置）。"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "no-referrer-when-downgrade")
        response.headers.setdefault("X-XSS-Protection", "1; mode=block")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        return response