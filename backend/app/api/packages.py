"""资料包 / 版本 / 附件 / 审核（F-04, F-05, F-07, F-08）。"""
import os
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.constants import ALLOWED_EXTENSIONS, ReviewDecision, ReviewLevel, VersionStatus
from app.core.audit import client_ip, log_event
from app.core.config import settings
from app.core.rbac import (
    admin_only, can_edit_package, can_review_dept, can_view_package, get_current_user, is_coo,
)
from app.core.snowflake import next_id
from app.core.storage import save_upload
from app.core.filetype import guess_mime
from app.core.uploads import read_validated_upload
from app.db import get_db
from app.models import (
    Attachment, AuditDomain, Package, PackageVersion, User,
)
from app.schemas import (
    AttachmentOut, Msg, PackageCreate, PackageOut, PackageUpdate, ReviewRequest, VersionCreate, VersionOut,
)
from app.services.notify import notify_params, coo_reviewer_ids, dept_reviewer_ids, notify_users

router = APIRouter(prefix="/packages", tags=["packages"])

PREVIEW_MIME = {"application/pdf", "image/png", "image/jpeg", "image/gif", "image/bmp", "image/webp"}


# ---------- 列表 / 详情 ----------
def _visible_packages(db: Session, user: User):
    q = db.query(Package)
    if user.role == "dept_reviewer":
        q = q.filter(Package.dept_id == user.dept_id)
    elif user.role == "submitter":
        q = q.filter(Package.owner_user_id == user.id)
    # admin / coo_reviewer / auditor 可见全部
    return q.order_by(Package.sort_order, Package.code).all()


def _latest_version(db: Session, pkg_id: int):
    return (
        db.query(PackageVersion)
        .filter(PackageVersion.package_id == pkg_id)
        .order_by(PackageVersion.id.desc())   # 按雪花 ID：created_at 是秒级精度，同秒创建时排序不确定
        .first()
    )


def _lock_version(db: Session, vid: int) -> PackageVersion | None:
    """行级锁重读版本行：与订单线 _lock_op 同理，防止审核与附件改动并发破坏状态机。"""
    return (
        db.query(PackageVersion)
        .populate_existing()
        .with_for_update()
        .filter(PackageVersion.id == vid)
        .first()
    )


def _purge_files(db: Session, atts: list) -> None:
    """批量删除附件行对应的物理文件。

    存储按 sha256 内容哈希命名，多个附件行（订单附件 / 版本附件）可能复用同一
    物理文件，仅当删除集合之外无其它引用时才删除，避免误删仍被引用的文件。
    """
    if not atts:
        return
    names = {a.file_name for a in atts}
    ids = [a.id for a in atts]
    for name in names:
        q = db.query(Attachment.id).filter(Attachment.file_name == name)
        if ids:
            q = q.filter(Attachment.id.notin_(ids))
        if q.first():
            continue
        path = os.path.join(settings.UPLOAD_DIR, name)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


@router.get("", response_model=list[dict])
def list_packages(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pkgs = _visible_packages(db, user)
    result = []
    for p in pkgs:
        lv = _latest_version(db, p.id)
        result.append({
            **PackageOut.model_validate(p).model_dump(),
            "current_status": lv.status if lv else "none",
            "current_version": lv.version_no if lv else "",
            "attachment_count": len(lv.attachments) if lv else 0,
            "editable": can_edit_package(user, p) and (lv is None or lv.status in (VersionStatus.DRAFT, VersionStatus.REJECTED)),
            "reviewable_dept": can_review_dept(user, p.dept_id, db=db,
                                               submitted_by=lv.submitted_by if lv else None)
                                and lv is not None and lv.status == VersionStatus.PENDING_DEPT,
            "reviewable_coo": is_coo(user) and lv is not None and lv.status == VersionStatus.PENDING_COO,
        })
    return result


@router.post("", response_model=PackageOut, status_code=status.HTTP_201_CREATED)
def create_package(payload: PackageCreate, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(admin_only)):
    if db.query(Package).filter(Package.code == payload.code).first():
        raise HTTPException(status_code=400, detail="资料包编号已存在")
    p = Package(**payload.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    log_event(db, AuditDomain.PACKAGE, "create", actor=user, ip=client_ip(request),
              target=p.code)
    return p


@router.patch("/{pkg_id}", response_model=PackageOut)
def update_package(pkg_id: int, payload: PackageUpdate, request: Request,
                   db: Session = Depends(get_db), user: User = Depends(admin_only)):
    p = db.get(Package, pkg_id)
    if not p:
        raise HTTPException(status_code=404, detail="资料包不存在")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    log_event(db, AuditDomain.PACKAGE, "update", actor=user, ip=client_ip(request),
              target=p.code)
    return p


@router.get("/{pkg_id}", response_model=dict)
def package_detail(pkg_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.get(Package, pkg_id)
    if not p or not can_view_package(user, p):
        raise HTTPException(status_code=404, detail="资料包不存在")
    versions = (
        db.query(PackageVersion)
        .filter(PackageVersion.package_id == pkg_id)
        .order_by(PackageVersion.id.desc())   # 按雪花 ID：created_at 是秒级精度，同秒创建时排序不确定
        .all()
    )
    return {
        **PackageOut.model_validate(p).model_dump(),
        "versions": [VersionOut.model_validate(v).model_dump() for v in versions],
    }


# ---------- 版本 ----------
def _next_version_no(db: Session, pkg_id: int) -> str:
    latest = _latest_version(db, pkg_id)
    if not latest:
        return "V1.0"
    m = re.match(r"V(\d+)\.(\d+)", latest.version_no)
    if not m:
        return "V1.0"
    major, minor = int(m.group(1)), int(m.group(2))
    minor += 1
    if minor > 9:
        major += 1
        minor = 0
    return f"V{major}.{minor}"


@router.post("/{pkg_id}/versions", response_model=VersionOut, status_code=status.HTTP_201_CREATED)
def create_version(pkg_id: int, payload: VersionCreate, request: Request,
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.get(Package, pkg_id)
    if not p:
        raise HTTPException(status_code=404, detail="资料包不存在")
    if not can_edit_package(user, p):
        raise HTTPException(status_code=403, detail="无权操作该资料包")
    project = payload.project_code or settings.PROJECT_CODE
    v = PackageVersion(
        id=next_id(),
        package_id=pkg_id,
        project_code=project,
        version_no=_next_version_no(db, pkg_id),
        status=VersionStatus.DRAFT,
        change_note=payload.change_note,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    log_event(db, AuditDomain.VERSION, "create", actor=user, ip=client_ip(request),
              target=f"{p.code}/{v.version_no}")
    return v


@router.get("/{pkg_id}/versions/{vid}", response_model=VersionOut)
def version_detail(pkg_id: int, vid: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    v = db.get(PackageVersion, vid)
    p = db.get(Package, pkg_id)
    if not v or v.package_id != pkg_id or not p or not can_view_package(user, p):
        raise HTTPException(status_code=404, detail="版本不存在")
    return v


@router.delete("/{pkg_id}/versions/{vid}", response_model=Msg)
def delete_version(pkg_id: int, vid: int, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(admin_only)):
    v = db.get(PackageVersion, vid)
    if not v or v.package_id != pkg_id:
        raise HTTPException(status_code=404, detail="版本不存在")
    if v.status == VersionStatus.RELEASED:
        raise HTTPException(status_code=400, detail="已放行版本不可删除")
    # 内容哈希命名可能被多个附件行复用，仅当无其它引用时才删除物理文件
    atts = list(v.attachments)
    p = db.get(Package, pkg_id)
    target = f"{p.code if p else pkg_id}/{v.version_no}"
    db.delete(v)
    db.commit()
    _purge_files(db, atts)
    log_event(db, AuditDomain.PACKAGE, "version_delete", actor=user, ip=client_ip(request),
              target=target)
    return Msg(msg="已删除")


# ---------- 附件上传 / 删除 ----------
def _reset_status_on_edit(v: PackageVersion):
    """上传/替换附件后，若已处于审核/放行/退回态则回退至待部门审核。"""
    if v.status in (VersionStatus.PENDING_DEPT, VersionStatus.PENDING_COO,
                    VersionStatus.RELEASED, VersionStatus.REJECTED):
        v.status = VersionStatus.PENDING_DEPT
        v.dept_reject_reason = ""
        v.coo_reject_reason = ""


@router.post("/{pkg_id}/versions/{vid}/attachments", response_model=list[AttachmentOut])
async def upload_attachments(
    pkg_id: int, vid: int, request: Request,
    files: list[UploadFile] = File(...),
    order_no: str = Form("", max_length=128),   # 对齐 attachments 列宽
    batch_no: str = Form("", max_length=128),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    p = db.get(Package, pkg_id)
    v = db.get(PackageVersion, vid)
    if not p or not v or v.package_id != pkg_id:
        raise HTTPException(status_code=404, detail="资料包或版本不存在")
    if not can_edit_package(user, p):
        raise HTTPException(status_code=403, detail="无权操作该资料包")
    if v.status == VersionStatus.RELEASED:
        raise HTTPException(status_code=400, detail="已放行版本不可修改，请创建新版本")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    # 先读入内存并校验（耗时段），尚未落盘、未写库
    pending: list[tuple[bytes, str, str, str, str]] = []
    for f in files:
        content, ext, md5, oname, ctype = await read_validated_upload(f, settings.MAX_FILE_MB)
        pending.append((content, ext, md5, oname, ctype))
    # 读取期间可能已被并发终审放行：加锁重读后按最新状态再判一次
    v = _lock_version(db, vid)
    if not v:
        raise HTTPException(status_code=404, detail="版本不存在")
    if v.status == VersionStatus.RELEASED or v.locked:
        raise HTTPException(status_code=400, detail="已放行版本不可修改，请创建新版本")
    created = []
    for content, ext, md5, fname, ctype in pending:
        att_id = next_id()
        stored = save_upload(content, ext)
        att = Attachment(
            id=att_id, version_id=vid, file_name=stored, original_name=fname,
            file_size=len(content), md5=md5, mime_type=ctype,
            order_no=order_no, batch_no=batch_no, uploaded_by=user.id,
        )
        db.add(att)
        created.append(att)
    _reset_status_on_edit(v)
    db.commit()
    for att in created:
        db.refresh(att)
    log_event(db, AuditDomain.ATTACHMENT, "upload", actor=user, ip=client_ip(request),
              target=f"{p.code}/{v.version_no}", detail=f"{len(created)} 个文件")
    return created


@router.delete("/{pkg_id}/versions/{vid}/attachments/{aid}", response_model=Msg)
def delete_attachment(pkg_id: int, vid: int, aid: int, request: Request,
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.get(Package, pkg_id)
    v = db.get(PackageVersion, vid)
    att = db.get(Attachment, aid)
    if not p or not v or not att or att.version_id != vid:
        raise HTTPException(status_code=404, detail="资源不存在")
    if not can_edit_package(user, p):
        raise HTTPException(status_code=403, detail="无权操作")
    v = _lock_version(db, vid) or v   # 加锁重读，避免与并发终审放行竞态
    if v.status == VersionStatus.RELEASED or v.locked:
        raise HTTPException(status_code=400, detail="已放行版本不可修改")
    # 内容哈希命名可能被多个附件行复用，仅当无其它引用时才删除物理文件
    reused = db.query(Attachment.id).filter(
        Attachment.file_name == att.file_name, Attachment.id != att.id).first()
    path = os.path.join(settings.UPLOAD_DIR, att.file_name)
    if not reused and os.path.exists(path):
        os.remove(path)
    db.delete(att)
    _reset_status_on_edit(v)
    db.commit()
    log_event(db, AuditDomain.ATTACHMENT, "delete", actor=user, ip=client_ip(request),
              target=f"{p.code}/{v.version_no}/{att.original_name}")
    return Msg(msg="已删除")


@router.get("/{pkg_id}/versions/{vid}/attachments/{aid}/file")
def download_attachment(pkg_id: int, vid: int, aid: int, request: Request, preview: bool = False,
                        db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    att = db.get(Attachment, aid)
    v = db.get(PackageVersion, vid) if att else None
    p = db.get(Package, pkg_id) if v else None
    if not att or not v or not p or att.version_id != vid or v.package_id != pkg_id:
        raise HTTPException(status_code=404, detail="资源不存在")
    if not can_view_package(user, p):
        raise HTTPException(status_code=404, detail="资源不存在")
    path = os.path.join(settings.UPLOAD_DIR, att.file_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="文件不存在")
    # 记录 IP：规格 F-10 要求下载留痕含 IP
    log_event(db, AuditDomain.ATTACHMENT, "download", actor=user, ip=client_ip(request),
              target=f"{att.original_name}")
    # 按扩展名判定而非库里存的 mime_type：历史附件的 mime_type 来自客户端声明，
    # 一份真 PDF 若当初被声明成 text/plain，至今仍无法预览
    mime = guess_mime(os.path.splitext(att.original_name or att.file_name or "")[1])
    if preview and mime in PREVIEW_MIME:
        return FileResponse(path, media_type=mime, filename=att.original_name)
    return FileResponse(path, filename=att.original_name)


# ---------- 提交 / 审核 ----------
@router.post("/{pkg_id}/versions/{vid}/submit", response_model=VersionOut)
def submit_version(pkg_id: int, vid: int, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    p = db.get(Package, pkg_id)
    v = db.get(PackageVersion, vid)
    if not p or not v or v.package_id != pkg_id:
        raise HTTPException(status_code=404, detail="资源不存在")
    if not can_edit_package(user, p):
        raise HTTPException(status_code=403, detail="无权操作")
    v = _lock_version(db, vid) or v   # 与并发审核串行化
    if v.status not in (VersionStatus.DRAFT, VersionStatus.REJECTED, VersionStatus.WITHDRAWN):
        raise HTTPException(status_code=400, detail="当前状态不可提交")
    if not v.attachments:
        raise HTTPException(status_code=400, detail="请先上传至少一个附件")
    v.status = VersionStatus.PENDING_DEPT
    v.submitted_by = user.id
    v.submitted_at = __import__("datetime").datetime.utcnow()
    db.commit()
    db.refresh(v)
    log_event(db, AuditDomain.REVIEW, "submit", actor=user, ip=client_ip(request),
              target=f"{p.code}/{v.version_no}")
    notify_users(db, dept_reviewer_ids(db, p.dept_id),
                 title=f"{p.code} {v.version_no} 待部门审核",
                 params=notify_params(f"{p.code} {v.version_no}", p),
                 body=f"{p.name_zh} · {v.change_note or ''}".strip(" ·"),
                 ntype="submit", link=f"/packages/{p.id}", exclude=user.id)
    db.commit()
    return v


@router.post("/{pkg_id}/versions/{vid}/review", response_model=VersionOut)
def review_version(pkg_id: int, vid: int, payload: ReviewRequest, request: Request,
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.get(Package, pkg_id)
    v = db.get(PackageVersion, vid)
    if not p or not v or v.package_id != pkg_id:
        raise HTTPException(status_code=404, detail="资源不存在")

    v = _lock_version(db, vid) or v   # 加锁重读，与并发上传/删除附件串行化
    decision = payload.decision
    level = payload.level
    # 退回必须填写整改要求：先校验，避免状态/审计日志已落库后才报错
    if decision == ReviewDecision.REJECT and not payload.reason:
        raise HTTPException(status_code=400, detail="退回必须填写整改要求")

    if level == ReviewLevel.DEPT:
        # 先鉴权再校验状态，避免用状态码差异泄露流程进展
        if not can_review_dept(user, p.dept_id, db=db, submitted_by=v.submitted_by):
            raise HTTPException(status_code=403, detail="非本部门审核人")
        if v.status != VersionStatus.PENDING_DEPT:
            raise HTTPException(status_code=400, detail="当前不在待部门审核状态")
        v.dept_reviewer_id = user.id
        v.dept_reviewed_at = __import__("datetime").datetime.utcnow()
        if decision == ReviewDecision.APPROVE:
            v.status = VersionStatus.PENDING_COO
        else:
            v.status = VersionStatus.REJECTED
            v.dept_reject_reason = payload.reason
        log_event(db, AuditDomain.REVIEW, "dept_approve" if decision == "approve" else "dept_reject",
                  actor=user, ip=client_ip(request), target=f"{p.code}/{v.version_no}",
                  detail=payload.reason)
    elif level == ReviewLevel.COO:
        if not is_coo(user):
            raise HTTPException(status_code=403, detail="仅 COO 终审人可终审")
        if v.status != VersionStatus.PENDING_COO:
            raise HTTPException(status_code=400, detail="当前不在待COO终审状态")
        v.coo_reviewer_id = user.id
        v.coo_reviewed_at = __import__("datetime").datetime.utcnow()
        if decision == ReviewDecision.APPROVE:
            v.status = VersionStatus.RELEASED
            v.locked = True
        else:
            v.status = VersionStatus.REJECTED
            v.coo_reject_reason = payload.reason
        log_event(db, AuditDomain.REVIEW, "coo_approve" if decision == "approve" else "coo_reject",
                  actor=user, ip=client_ip(request), target=f"{p.code}/{v.version_no}",
                  detail=payload.reason)
    else:
        raise HTTPException(status_code=400, detail="无效的审核层级")

    # 事件通知：部门通过→COO 终审人；退回/放行→资料责任人
    recipient = p.owner_user_id or v.submitted_by
    if level == ReviewLevel.DEPT and decision == ReviewDecision.APPROVE:
        notify_users(db, coo_reviewer_ids(db),
                     title=f"{p.code} {v.version_no} 待COO终审",
                     body=p.name_zh, ntype="coo_review", link=f"/packages/{p.id}", exclude=user.id,
                     params=notify_params(f"{p.code} {v.version_no}", p))
    elif recipient:
        if decision == ReviewDecision.APPROVE:
            notify_users(db, [recipient], title=f"{p.code} {v.version_no} 已放行归档",
                         body=p.name_zh, ntype="released", link=f"/packages/{p.id}", exclude=user.id,
                         params=notify_params(f"{p.code} {v.version_no}", p))
        else:
            notify_users(db, [recipient], title=f"{p.code} {v.version_no} 被退回",
                         body=p.name_zh, ntype="rejected", link=f"/packages/{p.id}", exclude=user.id,
                         params=notify_params(f"{p.code} {v.version_no}", p))

    db.commit()
    db.refresh(v)
    return v


@router.post("/{pkg_id}/versions/{vid}/withdraw", response_model=VersionOut)
def withdraw_version(pkg_id: int, vid: int, request: Request,
                     db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """提交人撤回：待部门审核 / 待COO终审的版本可撤回，撤回复审后重新提交。"""
    import datetime as _dt
    p = db.get(Package, pkg_id)
    v = db.get(PackageVersion, vid)
    if not p or not v or v.package_id != pkg_id:
        raise HTTPException(status_code=404, detail="资源不存在")
    # 与并发审核串行化：撤回同样是"检查状态后写状态"，不加锁会与终审放行竞态
    v = _lock_version(db, vid) or v
    if v.status not in (VersionStatus.PENDING_DEPT, VersionStatus.PENDING_COO):
        raise HTTPException(status_code=400, detail="当前状态不可撤回")
    # 仅提交人本人/责任人本人或管理员可撤回
    if user.role != "admin" and v.submitted_by != user.id and p.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="仅提交人本人可撤回")
    v.status = VersionStatus.WITHDRAWN
    v.dept_reject_reason = ""
    v.coo_reject_reason = ""
    db.commit()
    db.refresh(v)
    log_event(db, AuditDomain.REVIEW, "withdraw", actor=user, ip=client_ip(request),
              target=f"{p.code}/{v.version_no}")
    notify_users(db, dept_reviewer_ids(db, p.dept_id),
                 title=f"{p.code} {v.version_no} 已撤回",
                 body=p.name_zh, ntype="withdrawn", link=f"/packages/{p.id}", exclude=user.id,
                 params=notify_params(f"{p.code} {v.version_no}", p))
    db.commit()
    return v
