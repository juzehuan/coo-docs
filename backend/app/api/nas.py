"""NAS 归档同步接口（F-06）。"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import client_ip, log_event
from app.core import nas_config
from app.core.rbac import admin_only, coo_or_admin, nas_viewer
from app.db import get_db
from app.models import AuditDomain, SyncRecord, User
from app.schemas import NasConfigIn, NasConfigOut, NasStatusOut, NasTestResult, SyncRecordOut
from app.services import nas_sync

router = APIRouter(prefix="/nas", tags=["nas"])


def _target_of(cfg: dict) -> str:
    """审计用的归档目标描述（不含密钥）。"""
    return (f"s3://{cfg['bucket']}@{cfg['endpoint_url']}"
            if cfg["mode"] == "s3" else cfg["local_root"])


@router.get("/status", response_model=NasStatusOut)
def nas_status(db: Session = Depends(get_db), _: User = Depends(nas_viewer)):
    reachable = nas_sync.nas_reachable()
    # 先按窄列 (id, started_at) 排序取 ID 再按主键取行：
    # SyncRecord.details 是可达数百 KB 的 JSON，直接 ORDER BY 会让 MySQL 对宽行做
    # filesort 并撑爆 sort_buffer（行数少时优化器还会弃用索引），报 1038 Out of sort memory
    # 同秒并列时"最近一次同步"会取到哪条不确定，补唯一兜底列
    last_id = (db.query(SyncRecord.id)
               .order_by(SyncRecord.started_at.desc(), SyncRecord.id.desc())
               .limit(1).scalar())
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
    try:
        rec = nas_sync.run_sync(db, run_type="manual", triggered_by=user.id)
    except nas_sync.SyncBusy as e:
        # 409 而非 500：这是"当前不可执行"而非故障，前端据此提示用户稍后再试
        raise HTTPException(status_code=409, detail=str(e))
    log_event(db, AuditDomain.NAS, "manual_sync", actor=user, ip=client_ip(request),
              detail=f"success={rec.success},failed={rec.failed}")
    return rec


@router.get("/config", response_model=NasConfigOut)
def get_nas_config(_: User = Depends(admin_only)):
    """当前 NAS 归档配置。密钥以掩码返回——只告知是否已设置，不回显明文。"""
    return NasConfigOut(**nas_config.masked(nas_config.get_config()))


@router.put("/config", response_model=NasConfigOut)
def update_nas_config(payload: NasConfigIn, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(admin_only)):
    """保存 NAS 归档配置。

    这些信息（NAS 地址、访问密钥、桶名、挂载点、同步时间）此前只能改环境变量
    并重启整套服务，而它们恰恰是交付现场才确定、且会随换机/轮换密钥而变的内容。
    """
    cfg, requeued = nas_config.save_config(db, payload.model_dump())
    # 审计留痕不记密钥本身，只记改了哪些关键项，便于事后追溯"归档目标何时被改动"
    log_event(db, AuditDomain.NAS, "config_update", actor=user, ip=client_ip(request),
              detail=f"mode={cfg['mode']},target={_target_of(cfg)},sync_time={cfg['sync_time']},"
                     f"auto_sync={cfg['auto_sync']},requeued={requeued}")
    out = NasConfigOut(**nas_config.masked(cfg))
    out.requeued = requeued
    return out


@router.post("/config/test", response_model=NasTestResult)
def test_nas_config(payload: NasConfigIn, _: User = Depends(admin_only)):
    """用表单里的参数试连一次，**不写库**。

    让管理员在保存前就知道地址密钥对不对，而不是保存之后等到当晚自动同步
    失败才发现——那时证据已经该归档而未归档。
    """
    cfg = nas_config._normalize({**nas_config.get_config(), **payload.model_dump()})
    incoming = (payload.secret_key or "").strip()
    if not incoming or incoming == nas_config.MASK:
        cfg["secret_key"] = nas_config.get_config()["secret_key"]   # 未改密钥则沿用已存的
    return NasTestResult(**nas_sync.probe_config(cfg))


@router.get("/records", response_model=list[SyncRecordOut])
def sync_records(limit: int = Query(20, ge=1, le=200), db: Session = Depends(get_db),
                 _: User = Depends(nas_viewer)):
    # 同上：只对窄列排序取 ID，再按主键批量取行，避免对含大 JSON 的宽行做 filesort
    ids = [r[0] for r in db.query(SyncRecord.id)
           .order_by(SyncRecord.started_at.desc(), SyncRecord.id.desc()).limit(limit).all()]
    if not ids:
        return []
    rows = db.query(SyncRecord).filter(SyncRecord.id.in_(ids)).all()
    order = {rid: i for i, rid in enumerate(ids)}
    return sorted(rows, key=lambda r: order.get(r.id, 0))
