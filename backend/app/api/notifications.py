"""站内通知中心：列表 / 未读数 / 标记已读。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.rbac import get_current_user
from app.db import get_db
from app.models import Notification, User

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(limit: int = Query(30, ge=1, le=200), offset: int = Query(0, ge=0),
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Notification).filter(Notification.user_id == user.id)
    # func.count 聚合，避免 Query.count() 的全字段子查询（通知表随使用无限增长）
    cnt = db.query(func.count(Notification.id)).filter(Notification.user_id == user.id)
    total = cnt.scalar() or 0
    unread = cnt.filter(Notification.is_read.is_(False)).scalar() or 0
    rows = (
        q.order_by(Notification.is_read.asc(), Notification.created_at.desc())
        .offset(offset).limit(limit).all()
    )
    return {
        "total": total,
        "unread": unread,
        "items": [{
            "id": n.id,
            "title": n.title,
            "body": n.body,
            "type": n.type,
            "link": n.link,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        } for n in rows],
    }


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = db.query(func.count(Notification.id)).filter(
        Notification.user_id == user.id, Notification.is_read.is_(False)).scalar() or 0
    return {"count": n}


@router.post("/{nid}/read")
def mark_read(nid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = db.get(Notification, nid)
    if not n or n.user_id != user.id:
        raise HTTPException(status_code=404, detail="通知不存在")
    n.is_read = True
    db.commit()
    return {"ok": True}


@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.query(Notification).filter(
        Notification.user_id == user.id, Notification.is_read.is_(False)
    ).update({"is_read": True}, synchronize_session=False)
    db.commit()
    return {"ok": True}
