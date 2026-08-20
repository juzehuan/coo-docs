"""NAS 归档同步接口（F-06）。"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.audit import client_ip, log_event
from app.core.rbac import coo_or_admin, get_current_user
from app.db import get_db
from app.models import AuditDomain, SyncRecord, User
from app.schemas import NasStatusOut, SyncRecordOut
from app.services import nas_sync

router = APIRouter(prefix="/nas", tags=["nas"])


@router.get("/status", response_model=NasStatusOut)
def nas_status(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    reachable = nas_sync.nas_reachable()
    last = db.query(SyncRecord).order_by(SyncRecord.started_at.desc()).first()
    pending = db.query(nas_sync.Attachment).filter(nas_sync.Attachment.nas_synced.is_(False)).count()
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
def sync_records(limit: int = 20, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(SyncRecord).order_by(SyncRecord.started_at.desc()).limit(limit).all()
