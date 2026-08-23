"""站内通知服务：关键业务事件按用户生成通知。"""
import json
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Notification, User, user_factories


def notify_params(subject: str, pkg) -> str:
    """通知的结构化参数：主体标识 + 资料包三语名称。

    title/body 一直是中文成品串，泰国工厂的提交人把界面切到泰文也没用——
    通知早在创建时就被写死成中文了。通知该按**收件人**的语言渲染而不是
    创建者的，所以这里只存参数，由前端按当前语言拼装。
    三语名称在创建时快照下来：资料包改名后旧通知仍显示当时的名称，这对
    审计追溯反而是正确的。
    """
    return json.dumps({
        "subject": subject,
        "name_zh": getattr(pkg, "name_zh", "") or "",
        "name_en": getattr(pkg, "name_en", "") or "",
        "name_th": getattr(pkg, "name_th", "") or "",
    }, ensure_ascii=False)


def notify_users(db: Session, user_ids: list[int], title: str, body: str = "",
                 ntype: str = "", link: str = "", exclude: int | None = None,
                 params: str = "") -> None:
    """为指定用户批量写入通知；exclude 排除操作者本人。

    title/body 保留为中文回退：旧客户端与无 params 的历史记录仍能正常显示。
    """
    seen = set()
    for uid in user_ids:
        if uid is None or uid in seen:
            continue
        if exclude is not None and uid == exclude:
            continue
        seen.add(uid)
        db.add(Notification(user_id=uid, title=title, body=body, type=ntype,
                            link=link, params=params))
    db.flush()


def _authorized_for(db: Session, user_ids: list[int], factory_id) -> list[int]:
    """按工厂授权过滤收件人。

    工厂是本系统的数据隔离边界：未授权该工厂的人看不到对应订单。若通知不做同样的
    过滤，就会从旁路泄露订单号与资料包名（订单号本身是客户 PO 等敏感信息），
    而且收件人点开通知只会得到 404。管理员对全部激活工厂可见，不参与过滤。
    """
    if not factory_id or not user_ids:
        return user_ids
    rows = (
        db.query(User.id)
        .outerjoin(user_factories, user_factories.c.user_id == User.id)
        .filter(
            User.id.in_(user_ids),
            or_(User.role == "admin", user_factories.c.factory_id == factory_id),
        )
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


def dept_reviewer_ids(db: Session, dept_id, factory_id=None) -> list[int]:
    """责任部门的部门审核人（启用状态）；传 factory_id 时仅保留有该工厂权限的人。"""
    if not dept_id:
        return []
    rows = db.query(User.id).filter(
        User.role == "dept_reviewer", User.dept_id == dept_id, User.status == "active").all()
    return _authorized_for(db, [r[0] for r in rows], factory_id)


def coo_reviewer_ids(db: Session, factory_id=None) -> list[int]:
    """COO 终审人 + 管理员（启用状态）；传 factory_id 时按工厂授权过滤（管理员不受限）。"""
    rows = db.query(User.id).filter(
        User.role.in_(["coo_reviewer", "admin"]), User.status == "active").all()
    return _authorized_for(db, [r[0] for r in rows], factory_id)
