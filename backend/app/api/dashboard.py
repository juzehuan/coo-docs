"""工作概览看板（F-03）。"""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.constants import VersionStatus
from app.core.audit import client_ip, log_event
from app.core.rbac import get_current_user
from app.db import get_db
from app.models import Attachment, AuditDomain, Package, PackageVersion, User
from app.schemas import DashboardOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pkgs = db.query(Package).filter(Package.status == "active").all()
    versions = db.query(PackageVersion).all()
    # 构建 资料包 -> 最新版本状态
    latest = {}
    for v in versions:
        if v.package_id not in latest or v.created_at > latest[v.package_id].created_at:
            latest[v.package_id] = v

    released_count = sum(1 for p in pkgs if p.id in latest and latest[p.id].status == VersionStatus.RELEASED)
    completion = round(released_count / len(pkgs) * 100, 1) if pkgs else 0.0

    total_attachments = db.query(Attachment).count()

    # 待我处理：提交人看自己被退回；部门审核人看待部门审核；COO 看待终审
    pending_mine = 0
    for p in pkgs:
        v = latest.get(p.id)
        if not v:
            continue
        if user.role == "submitter" and p.owner_user_id == user.id and v.status == VersionStatus.REJECTED:
            pending_mine += 1
        elif user.role == "dept_reviewer" and p.dept_id == user.dept_id and v.status == VersionStatus.PENDING_DEPT:
            pending_mine += 1
        elif user.role in ("coo_reviewer", "admin") and v.status == VersionStatus.PENDING_COO:
            pending_mine += 1

    overdue = 0
    need_attention = []
    progress = []
    for p in pkgs:
        v = latest.get(p.id)
        st = v.status if v else "none"
        att_n = len(v.attachments) if v else 0
        # 进度：已放行=100，待终审=80，待部门=50，退回=30，草稿=10，无=0
        pct = {"released": 100, "pending_coo": 80, "pending_dept": 50,
               "rejected": 30, "draft": 10, "none": 0}.get(st, 0)
        progress.append({"code": p.code, "name": p.name_zh, "status": st, "percent": pct,
                         "attachments": att_n})
        if st == "rejected":
            overdue += 1
            need_attention.append({"code": p.code, "name": p.name_zh, "issue": "已退回，待整改",
                                   "reason": v.dept_reject_reason or v.coo_reject_reason})
        elif st == "pending_coo":
            need_attention.append({"code": p.code, "name": p.name_zh, "issue": "待 COO 终审", "reason": ""})
        elif st == "pending_dept":
            need_attention.append({"code": p.code, "name": p.name_zh, "issue": "待部门审核", "reason": ""})

    return DashboardOut(
        package_completion=completion,
        total_attachments=total_attachments,
        pending_mine=pending_mine,
        released=released_count,
        overdue=overdue,
        package_progress=sorted(progress, key=lambda x: -x["percent"]),
        need_attention=need_attention[:10],
    )


@router.get("/export")
def export_archive_list(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """归档清单导出（CSV）。审计查看人/COO/管理员可用。"""
    if user.role == "submitter" or user.role == "dept_reviewer":
        from fastapi import HTTPException, status
        raise HTTPException(status_code=403, detail="无权导出")
    versions = db.query(PackageVersion).all()
    pkgs = {p.id: p for p in db.query(Package).all()}
    header = ["资料包编号", "资料包名称", "版本", "状态", "责任人", "附件数", "已同步NAS"]
    lines = [",".join(header)]
    for v in versions:
        p = pkgs.get(v.package_id)
        synced = sum(1 for a in v.attachments if a.nas_synced)
        line = [p.code if p else "", p.name_zh if p else "", v.version_no, v.status,
                str(v.submitted_by or ""), str(len(v.attachments)), f"{synced}/{len(v.attachments)}"]
        lines.append(",".join(f'"{c}"' for c in line))
    csv = "\n".join(lines)
    log_event(db, AuditDomain.EXPORT, "archive_csv", actor=user, ip=client_ip(None))
    return Response(content="\ufeff" + csv, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=archive_list.csv"})
