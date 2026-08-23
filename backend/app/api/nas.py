"""NAS 归档同步接口（F-06）。"""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import client_ip, log_event
from app.core.rbac import coo_or_admin, nas_viewer
from app.db import get_db
from app.models import AuditDomain, SyncRecord, User
from app.schemas import NasStatusOut, SyncRecordOut
from app.services import nas_sync

router = APIRouter(prefix="/nas", tags=["nas"])


@router.get("/status", response_model=NasStatusOut)
def nas_status(db: Session = Depends(get_db), _: User = Depends(nas_viewer)):
    reachable = nas_sync.nas_reachable()
    # 先按窄列 (id, started_at) 排序取 ID 再按主键取行：
    # SyncRecord.details 是可达数百 KB 的 JSON，直接 ORDER BY 会让 MySQL 对宽行做
    # filesort 并撑爆 sort_buffer（行数少时优化器还会弃用索引），报 1038 Out of sort memory
    last_id = db.query(SyncRecord.id).order_by(SyncRecord.started_at.desc()).limit(1).scalar()
    last = db.get(SyncRecord, last_id) if last_id else None
    # 用 func.count 聚合：Query.count() 会包一层子查询把匹配行全字段物化，
    # 附件量达万级时 MySQL 排序缓冲不足直接报 1038 Out of sort memory
    pending = db.query(func.count(nas_sync.Attachment.id)).filter(
        nas_sync.Attachment.nas_synced.is_(False)).scalar() or 0
    return NasStatusOut(
        nas_root=nas_sync.nas_target_display(),
        nas_reachable=reachable,
        last_sync=SyncRecordOut.model_validate(last) if last else None,
        pending_count=pending,
    )


@router.post("/sync", response_model=SyncRecordOut)
def trigger_sync(request: Request, db: Session = Depends(get_db), user: User = Depends(coo_or_admin)):
    rec = nas_sync.run_sync(db, run_type="manual", triggered_by=user.id)
    log_event(db, AuditDomain.NAS, "manual_sync", actor=user, ip=client_ip(request),
              detail=f"success={rec.success},failed={rec.failed}")
    return rec


@router.get("/records", response_model=list[SyncRecordOut])
def sync_records(limit: int = Query(20, ge=1, le=200), db: Session = Depends(get_db),
                 _: User = Depends(nas_viewer)):
    # 同上：只对窄列排序取 ID，再按主键批量取行，避免对含大 JSON 的宽行做 filesort
    ids = [r[0] for r in db.query(SyncRecord.id)
           .order_by(SyncRecord.started_at.desc()).limit(limit).all()]
    if not ids:
        return []
    rows = db.query(SyncRecord).filter(SyncRecord.id.in_(ids)).all()
    order = {rid: i for i, rid in enumerate(ids)}
    return sorted(rows, key=lambda r: order.get(r.id, 0))
