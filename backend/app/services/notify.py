"""站内通知服务：关键业务事件按用户生成通知。"""
from sqlalchemy.orm import Session

from app.models import Notification, User


def notify_users(db: Session, user_ids: list[int], title: str, body: str = "",
                 ntype: str = "", link: str = "", exclude: int | None = None) -> None:
    """为指定用户批量写入通知；exclude 排除操作者本人。"""
    seen = set()
    for uid in user_ids:
        if uid is None or uid in seen:
            continue
        if exclude is not None and uid == exclude:
            continue
        seen.add(uid)
        db.add(Notification(user_id=uid, title=title, body=body, type=ntype, link=link))
    db.flush()


def dept_reviewer_ids(db: Session, dept_id) -> list[int]:
    """责任部门的部门审核人（启用状态）。"""
    if not dept_id:
        return []
    rows = db.query(User.id).filter(
        User.role == "dept_reviewer", User.dept_id == dept_id, User.status == "active").all()
    return [r[0] for r in rows]


def coo_reviewer_ids(db: Session) -> list[int]:
    """COO 终审人 + 管理员（启用状态）。"""
    rows = db.query(User.id).filter(
        User.role.in_(["coo_reviewer", "admin"]), User.status == "active").all()
    return [r[0] for r in rows]
