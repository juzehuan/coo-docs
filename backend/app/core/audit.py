"""审计日志写入辅助。"""
from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog


def client_ip(request: Request | None) -> str:
    """取客户端 IP，防伪造：

    - X-Real-IP 由本项目 nginx 用 $remote_addr 强制覆写（客户端伪造值会被替换），可信；
    - X-Forwarded-For 取最后一跳（$proxy_add_x_forwarded_for 由最近的代理追加，
      首段是客户端可自由伪造的，绝不能取首段）；
    - 都没有则为直连（dev / 本机调试），取 socket 对端地址。
    """
    if not request:
        return ""
    real = request.headers.get("X-Real-IP")
    if real:
        return real.strip()
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[-1].strip()
    return request.client.host if request.client else ""


# 审计各字段的列宽（与 models.AuditLog 一致）。
#
# **审计写入不得让业务操作失败。** 此前这里不做任何长度处理，而 `op_delete`
# 的 target 是 `订单号/实例ID/文件名` 三段拼接，最长可达 64+1+19+1+255 = 340 字符，
# 超出 target(255) 后 MySQL 抛 DataError，被全局处理器翻译成 400
# 「字段内容过长或格式不正确，请检查后重试」。
# 实测（第 60 轮）：上传一个 244 字符文件名（系统自己允许，safe_original_name 上限
# 就是 255），该附件随即**永远删不掉**——target 长 281，每次删除都 400，
# 而提示还在让用户"检查后重试"，可用户无论怎么改都不可能成功，附件也无法移除。
# 边界实测：文件名 215 → target 252 → 删除 200；文件名 244 → target 281 → 删除 400。
_LIMITS = {
    "event_domain": 64, "action": 64, "actor_role": 32,
    "actor_name": 128, "ip": 64, "target": 255,
}
# detail 是 TEXT（65535 **字节**）。按最坏情况每字符 4 字节留出余量，
# 避免罕见的超长说明重蹈上面的覆辙。
_DETAIL_LIMIT = 16000


def _clip(value, limit: int) -> str:
    """超长时截掉**尾部**并留下省略号标记。

    定位信息一律排在前面（订单号 / 资料包编号 / 版本号在最前，文件名在最后），
    所以截尾保住的是"这是哪个对象"，丢掉的只是文件名末尾；
    反过来截头会把最关键的定位信息丢掉，正好本末倒置。
    留标记是为了让人一眼看出内容被截断过，而不是误以为原文就这么长。
    """
    s = "" if value is None else str(value)
    return s if len(s) <= limit else s[: limit - 1] + "…"


def log_event(
    db: Session,
    domain: str,
    action: str,
    *,
    actor=None,
    ip: str = "",
    target: str = "",
    detail: str = "",
):
    """domain.action 形式记录审计事件。"""
    rec = AuditLog(
        event_domain=_clip(domain, _LIMITS["event_domain"]),
        action=_clip(action, _LIMITS["action"]),
        actor_id=actor.id if actor else None,
        actor_role=_clip(actor.role if actor else "", _LIMITS["actor_role"]),
        actor_name=_clip(actor.display_name if actor else "", _LIMITS["actor_name"]),
        ip=_clip(ip, _LIMITS["ip"]),
        target=_clip(target, _LIMITS["target"]),
        detail=_clip(detail, _DETAIL_LIMIT),
    )
    db.add(rec)
    db.commit()
