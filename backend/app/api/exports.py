"""异步导出作业接口（第 80 轮）。

同步导出端点保持不变、继续可用；这里提供"提交—查询—下载"的另一条路，
用于大导出与并发高峰。两条路共用 services/exporter.py 的同一份生成器。
"""
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.audit import client_ip, log_event
from app.core.http_headers import content_disposition
from app.core import dl_ticket
from app.core.rbac import get_current_user, optional_current_user, user_from_download_ticket
from app.db import get_db
from app.models import AuditDomain, ExportJob, User
from app.schemas import Msg
from app.services import export_jobs

router = APIRouter(prefix="/exports", tags=["exports"])


def _out(j: ExportJob) -> dict:
    return {
        "id": j.id, "kind": j.kind, "status": j.status,
        "file_name": j.file_name, "file_size": j.file_size,
        "error": j.error or "",
        "created_at": j.created_at, "finished_at": j.finished_at,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_export(payload: dict, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """提交一个导出作业。

    **权限在这里判定**：每种导出各自的可见性规则由注册时提供的校验函数执行，
    与同步端点用同一套（否则异步这条路就成了绕过权限的旁路——第 53 轮票据
    下载踩过同一类问题，那次的结论是"换出用户后仍走完全相同的权限判定"）。
    """
    kind = str(payload.get("kind") or "")
    params = payload.get("params") or {}
    if kind not in export_jobs.known_kinds():
        raise HTTPException(status_code=400,
                            detail=f"未知的导出类型：{kind or '(空)'}")
    check = export_jobs.permission_check(kind)
    if check is not None:
        check(db, user, params)          # 无权时由校验函数抛 HTTPException
    job = export_jobs.submit(db, user, kind, params)
    log_event(db, AuditDomain.EXPORT, "export_job_submit", actor=user,
              ip=client_ip(request), target=kind, detail=f"job={job.id}")
    return _out(job)


@router.get("", response_model=list[dict])
def my_exports(limit: int = 20, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """我的导出作业（只看自己的：产物里可能含他人无权查看的数据）。"""
    rows = (db.query(ExportJob).filter(ExportJob.user_id == user.id)
            .order_by(ExportJob.created_at.desc(), ExportJob.id.desc())
            .limit(max(1, min(limit, 100))).all())
    return [_out(j) for j in rows]


@router.get("/{job_id}")
def export_status(job_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    j = db.get(ExportJob, job_id)
    if not j or j.user_id != user.id:
        raise HTTPException(status_code=404, detail="导出作业不存在")
    return _out(j)


@router.post("/{job_id}/ticket")
def issue_export_ticket(job_id: int, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    """签发下载票据。

    产物（尤其 ZIP）可能很大，走浏览器原生下载才有进度与断点续传（第 53 轮），
    而原生下载带不了 Bearer 头——第 87 轮浏览器实测：「我的导出」的下载按钮
    点开是 `Not authenticated`，整条异步链路的最后一步不通。与附件下载同一套票据。
    """
    j = db.get(ExportJob, job_id)
    if not j or j.user_id != user.id:
        raise HTTPException(status_code=404, detail="导出作业不存在")
    return {"ticket": dl_ticket.issue(job_id, user.id), "expires_in": dl_ticket.TICKET_TTL_SECONDS}


@router.get("/{job_id}/download")
def download_export(job_id: int, request: Request, ticket: str | None = None,
                    db: Session = Depends(get_db),
                    user: User | None = Depends(optional_current_user)):
    """下载产物。

    只允许提交人本人下载：产物是按**提交时的可见范围**生成的，
    换个人下载就等于绕过可见性收敛。票据换出的用户同样要过这一关。
    """
    user = user_from_download_ticket(request, job_id, ticket, db) or user
    if user is None:
        raise HTTPException(status_code=401, detail="无效或过期的凭证")
    j = db.get(ExportJob, job_id)
    if not j or j.user_id != user.id:
        raise HTTPException(status_code=404, detail="导出作业不存在")
    if j.status != "done":
        raise HTTPException(status_code=409,
                            detail=f"作业尚未完成（当前状态：{j.status}）")
    path = os.path.join(export_jobs.store_dir(), j.stored_name or "")
    if not j.stored_name or not os.path.exists(path):
        # 产物过期被清理，或磁盘上被人删了。说清楚而不是 404 让人以为作业不存在
        raise HTTPException(status_code=410,
                            detail=f"产物已过期或不存在（保留 {export_jobs.RETENTION_HOURS} 小时），请重新导出")
    log_event(db, AuditDomain.EXPORT, "export_job_download", actor=user,
              ip=client_ip(request), target=j.kind, detail=f"job={j.id}")
    return FileResponse(path, headers={"Content-Disposition": content_disposition(j.file_name)})


@router.delete("/{job_id}", response_model=Msg)
def delete_export(job_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    j = db.get(ExportJob, job_id)
    if not j or j.user_id != user.id:
        raise HTTPException(status_code=404, detail="导出作业不存在")
    if j.stored_name:
        try:
            os.unlink(os.path.join(export_jobs.store_dir(), j.stored_name))
        except OSError:
            pass
    db.delete(j)
    db.commit()
    return Msg(msg="已删除")
