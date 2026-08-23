"""请求级语言上下文与多语字段取值。

系统的核心业务对象（18 类资料包、部门、工厂）在库里都存了 zh/en/th 三份名称，
但接口下发的扁平化展示字段一律取 name_zh，导致英文/泰文界面下资料包清单、
部门名、工厂名全是中文——而泰国工厂的提交人正是主要用户，那份"该传什么材料"
的清单恰恰是他们最需要读懂的内容。

这里用 ContextVar 承载语言，而不是给每个函数加 lang 参数：取名发生在
_order_row / todo 行组装这类深层辅助函数里，逐个改签名会波及大量调用点，
且以后新增字段又会漏。中间件在请求入口设置一次，取值处直接读。

注：Starlette 把同步端点放进线程池执行时会复制上下文，ContextVar 在
sync def 端点内同样可读。
"""
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware

SUPPORTED = ("zh", "en", "th")
DEFAULT_LANG = "zh"

_lang: ContextVar[str] = ContextVar("lang", default=DEFAULT_LANG)


def current_lang() -> str:
    return _lang.get()


def local_name(obj, default: str = "") -> str:
    """按当前请求语言取对象名称，缺译时回退中文。

    回退到中文而非留空：宁可显示一个看得懂却语言不对的名字，
    也不能让资料包名变成空白——那会让清单无法辨认。
    """
    if obj is None:
        return default
    lang = current_lang()
    val = getattr(obj, f"name_{lang}", None)
    if val and val.strip():
        return val
    return getattr(obj, "name_zh", None) or default


class LangMiddleware(BaseHTTPMiddleware):
    """从 X-Lang 请求头读取界面语言（前端 axios 拦截器统一带上）。"""

    async def dispatch(self, request, call_next):
        raw = (request.headers.get("X-Lang") or "").lower()
        token = _lang.set(raw if raw in SUPPORTED else DEFAULT_LANG)
        try:
            return await call_next(request)
        finally:
            _lang.reset(token)
