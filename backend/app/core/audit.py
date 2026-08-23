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
        event_domain=domain,
        action=action,
        actor_id=actor.id if actor else None,
        actor_role=actor.role if actor else "",
        actor_name=actor.display_name if actor else "",
        ip=ip,
        target=target,
        detail=detail,
    )
    db.add(rec)
    db.commit()
