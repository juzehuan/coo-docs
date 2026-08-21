"""客户订单管理：订单 CRUD、订单-资料包实例化、附件与审核（方案核心数据模型）。"""
import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.constants import ALLOWED_EXTENSIONS, ReviewDecision, ReviewLevel, VersionStatus
from app.core.audit import client_ip, log_event
from app.core.config import settings
from app.core.rbac import (
    can_edit_order, can_edit_order_package, export_viewer, get_current_user,
)
from app.core.snowflake import next_id
from app.core.storage import save_upload
from app.db import get_db
from app.models import (
    Attachment, AuditDomain, Factory, Order, OrderPackage, Package, User,
)
from app.schemas import (
    AttachmentOut, Msg, OrderCreate, OrderDetailOut, OrderInstanceCreate, OrderOut,
    OrderPackageOut, OrderUpdate, ReviewRequest,
)
from app.services.notify import coo_reviewer_ids, dept_reviewer_ids, notify_users

router = APIRouter(prefix="/orders", tags=["orders"])

PREVIEW_MIME = {"application/pdf", "image/png", "image/jpeg", "image/gif", "image/bmp", "image/webp"}


def _factory_ids(user: User, db: Session) -> list[int]:
    """当前账号可见的工厂 ID；admin 可见全部激活工厂。"""
    if user.role == "admin":
        return [f.id for f in db.query(Factory).filter(Factory.status == "active").all()]
    return [f.id for f in user.factories]


def _visible_orders_q(db: Session, user: User):
    fids = _factory_ids(user, db)
    return db.query(Order).filter(Order.factory_id.in_(fids))


def _package_stats(op: OrderPackage) -> dict:
    """订单-资料包完成度与附件数。"""
    return {
        "attachment_count": len(op.attachments),
    }


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


def _order_row(db: Session, o: Order) -> dict:
    fac = db.get(Factory, o.factory_id) if o.factory_id else None
    opkgs = o.packages
    released = sum(1 for p in opkgs if p.status == VersionStatus.RELEASED)
    total = len(opkgs)
    completion = round(released / total * 100, 1) if total else 0.0
    return {
        **OrderOut.model_validate(o).model_dump(),
        "factory_code": fac.code if fac else "",
        "factory_name": fac.name_zh if fac else "",
        "package_count": total,
        "released_count": released,
        "completion": completion,
    }


def _op_out(op: OrderPackage) -> dict:
    pkg = op.package
    out = OrderPackageOut.model_validate(op).model_dump()
    out["package_code"] = pkg.code if pkg else ""
    out["package_name"] = pkg.name_zh if pkg else ""
    out["package_dept_id"] = pkg.dept_id if pkg else None
    out["attachment_count"] = len(op.attachments)
    out["attachments"] = [AttachmentOut.model_validate(a).model_dump() for a in op.attachments]
    return out


# ---------- 列表 / 详情 ----------
@router.get("", response_model=list[OrderOut])
def list_orders(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [_order_row(db, o) for o in _visible_orders_q(db, user).order_by(Order.created_at.desc()).all()]


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(payload: OrderCreate, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    fids = _factory_ids(user, db)
    if payload.factory_id not in fids:
        raise HTTPException(status_code=403, detail="无权为该工厂创建订单")
    if db.query(Order).filter(Order.order_no == payload.order_no).first():
        raise HTTPException(status_code=400, detail="订单号已存在")
    data = payload.model_dump()
    # 提交人创建订单时默认本人为责任人，否则后续无法编辑/操作该订单
    if not data.get("owner_user_id") and user.role == "submitter":
        data["owner_user_id"] = user.id
    o = Order(**data)
    db.add(o)
    db.commit()
    db.refresh(o)
    log_event(db, AuditDomain.PACKAGE, "order_create", actor=user, ip=client_ip(request),
              target=o.order_no)
    return _order_row(db, o)


@router.patch("/{order_id}", response_model=OrderOut)
def update_order(order_id: int, payload: OrderUpdate, request: Request,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    o = db.get(Order, order_id)
    if not o or o.id not in [x.id for x in _visible_orders_q(db, user).all()]:
        raise HTTPException(status_code=404, detail="订单不存在")
    if not can_edit_order(user, o):
        raise HTTPException(status_code=403, detail="无权修改该订单")
    data = payload.model_dump(exclude_unset=True)
    if "factory_id" in data and data["factory_id"] != o.factory_id:
        raise HTTPException(status_code=400, detail="创建后不允许变更工厂")
    for k, v in data.items():
        setattr(o, k, v)
    db.commit()
    db.refresh(o)
    log_event(db, AuditDomain.PACKAGE, "order_update", actor=user, ip=client_ip(request),
              target=o.order_no)
    return _order_row(db, o)


@router.get("/{order_id}", response_model=OrderDetailOut)
def order_detail(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    o = db.get(Order, order_id)
    if not o or o.id not in [x.id for x in _visible_orders_q(db, user).all()]:
        raise HTTPException(status_code=404, detail="订单不存在")
    base = _order_row(db, o)
    base["packages"] = [_op_out(op) for op in sorted(o.packages, key=lambda x: x.package.code if x.package else "")]
    return base


@router.delete("/{order_id}", response_model=Msg)
def delete_order(order_id: int, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    o = db.get(Order, order_id)
    if not o or o.id not in [x.id for x in _visible_orders_q(db, user).all()]:
        raise HTTPException(status_code=404, detail="订单不存在")
    if not can_edit_order(user, o):
        raise HTTPException(status_code=403, detail="仅责任人/管理员可删除订单")
    # 内容哈希命名可能被多个附件行复用，仅当无其它引用时才删除物理文件
    atts = [att for op in o.packages for att in op.attachments]
    db.delete(o)
    db.commit()
    _purge_files(db, atts)
    log_event(db, AuditDomain.PACKAGE, "order_delete", actor=user, ip=client_ip(request),
              target=o.order_no)
    return Msg(msg="已删除")


# ---------- 订单-资料包实例化 ----------
@router.post("/{order_id}/packages", response_model=OrderPackageOut, status_code=status.HTTP_201_CREATED)
def add_order_package(order_id: int, payload: OrderInstanceCreate, request: Request,
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    o = db.get(Order, order_id)
    if not o or o.id not in [x.id for x in _visible_orders_q(db, user).all()]:
        raise HTTPException(status_code=404, detail="订单不存在")
    if not can_edit_order(user, o):
        raise HTTPException(status_code=403, detail="无权为订单添加资料包")
    pkg = db.get(Package, payload.package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="资料包模板不存在")
    if any(op.package_id == pkg.id for op in o.packages):
        raise HTTPException(status_code=400, detail="该资料包已在订单中")
    op = OrderPackage(
        order_id=o.id,
        package_id=pkg.id,
        project_code=settings.PROJECT_CODE,
        status=VersionStatus.DRAFT,
        owner_user_id=(payload.owner_user_id or pkg.owner_user_id
                       or (user.id if user.role == "submitter" else None)),
        required=payload.required,
        due_date=payload.due_date or pkg.due_date,
    )
    db.add(op)
    db.commit()
    db.refresh(op)
    log_event(db, AuditDomain.PACKAGE, "order_package_add", actor=user, ip=client_ip(request),
              target=f"{o.order_no}/{pkg.code}")
    return _op_out(op)


@router.delete("/{order_id}/packages/{op_id}", response_model=Msg)
def remove_order_package(order_id: int, op_id: int, request: Request,
                         db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    o = db.get(Order, order_id)
    op = db.get(OrderPackage, op_id)
    if not o or not op or op.order_id != o.id or o.id not in [x.id for x in _visible_orders_q(db, user).all()]:
        raise HTTPException(status_code=404, detail="资源不存在")
    if not can_edit_order_package(user, op):
        raise HTTPException(status_code=403, detail="无权移除该订单资料包")
    if op.locked or op.status == VersionStatus.RELEASED:
        raise HTTPException(status_code=400, detail="已放行实例不可移除，如需变更请新建订单")
    # 内容哈希命名可能被多个附件行复用，仅当无其它引用时才删除物理文件
    atts = list(op.attachments)
    db.delete(op)
    db.commit()
    _purge_files(db, atts)
    log_event(db, AuditDomain.PACKAGE, "order_package_remove", actor=user, ip=client_ip(request),
              target=f"{o.order_no}/{op_id}")
    return Msg(msg="已移除")


@router.post("/{order_id}/packages/{op_id}/submit", response_model=OrderPackageOut)
def submit_order_package(order_id: int, op_id: int, request: Request,
                         db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    o, op = _get_op(db, order_id, op_id, user)
    if not can_edit_order_package(user, op):
        raise HTTPException(status_code=403, detail="无权操作该订单资料包")
    if op.status not in (VersionStatus.DRAFT, VersionStatus.REJECTED, VersionStatus.WITHDRAWN):
        raise HTTPException(status_code=400, detail="当前状态不可提交")
    if not op.attachments:
        raise HTTPException(status_code=400, detail="请先上传至少一个附件")
    op.status = VersionStatus.PENDING_DEPT
    op.submitted_by = user.id
    op.submitted_at = _utcnow()
    db.commit()
    db.refresh(op)
    log_event(db, AuditDomain.REVIEW, "op_submit", actor=user, ip=client_ip(request),
              target=f"{o.order_no}/{op.package.code}")
    dept_id = op.package.dept_id if op.package else None
    notify_users(db, dept_reviewer_ids(db, dept_id),
                 title=f"{o.order_no}/{op.package.code} 待部门审核",
                 body=op.package.name_zh, ntype="submit", link=f"/orders/{o.id}", exclude=user.id)
    db.commit()
    return _op_out(op)


@router.post("/{order_id}/packages/{op_id}/review", response_model=OrderPackageOut)
def review_order_package(order_id: int, op_id: int, payload: ReviewRequest, request: Request,
                         db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    o, op = _get_op(db, order_id, op_id, user)
    from app.core.rbac import can_review_dept, is_coo
    decision, level = payload.decision, payload.level
    # 退回必须填写整改要求：先校验，避免状态/审计日志已落库后才报错
    if decision == ReviewDecision.REJECT and not payload.reason:
        raise HTTPException(status_code=400, detail="退回必须填写整改要求")
    if level == ReviewLevel.DEPT:
        if op.status != VersionStatus.PENDING_DEPT:
            raise HTTPException(status_code=400, detail="当前不在待部门审核状态")
        if not can_review_dept(user, op.package.dept_id if op.package else None):
            raise HTTPException(status_code=403, detail="非本部门审核人")
        op.dept_reviewer_id = user.id
        op.dept_reviewed_at = _utcnow()
        if decision == ReviewDecision.APPROVE:
            op.status = VersionStatus.PENDING_COO
        else:
            op.status = VersionStatus.REJECTED
            op.dept_reject_reason = payload.reason
        log_event(db, AuditDomain.REVIEW, "op_dept_approve" if decision == "approve" else "op_dept_reject",
                  actor=user, ip=client_ip(request), target=f"{o.order_no}/{op_id}", detail=payload.reason)
    elif level == ReviewLevel.COO:
        if op.status != VersionStatus.PENDING_COO:
            raise HTTPException(status_code=400, detail="当前不在待COO终审状态")
        if not is_coo(user):
            raise HTTPException(status_code=403, detail="仅 COO 终审人可终审")
        op.coo_reviewer_id = user.id
        op.coo_reviewed_at = _utcnow()
        if decision == ReviewDecision.APPROVE:
            op.status = VersionStatus.RELEASED
            op.locked = True
        else:
            op.status = VersionStatus.REJECTED
            op.coo_reject_reason = payload.reason
        log_event(db, AuditDomain.REVIEW, "op_coo_approve" if decision == "approve" else "op_coo_reject",
                  actor=user, ip=client_ip(request), target=f"{o.order_no}/{op_id}", detail=payload.reason)
    else:
        raise HTTPException(status_code=400, detail="无效的审核层级")

    # 事件通知：部门通过→COO 终审人；退回/放行→责任人
    recipient = op.owner_user_id or op.submitted_by
    pcode = op.package.code if op.package else ""
    if level == ReviewLevel.DEPT and decision == ReviewDecision.APPROVE:
        notify_users(db, coo_reviewer_ids(db),
                     title=f"{o.order_no}/{pcode} 待COO终审",
                     body=op.package.name_zh if op.package else "", ntype="coo_review",
                     link=f"/orders/{o.id}", exclude=user.id)
    elif recipient:
        if decision == ReviewDecision.APPROVE:
            notify_users(db, [recipient], title=f"{o.order_no}/{pcode} 已放行归档",
                         body=op.package.name_zh if op.package else "", ntype="released",
                         link=f"/orders/{o.id}", exclude=user.id)
        else:
            notify_users(db, [recipient], title=f"{o.order_no}/{pcode} 被退回",
                         body=op.package.name_zh if op.package else "", ntype="rejected",
                         link=f"/orders/{o.id}", exclude=user.id)

    db.commit()
    db.refresh(op)
    return _op_out(op)


# ---------- 撤回 ----------
@router.post("/{order_id}/packages/{op_id}/withdraw", response_model=OrderPackageOut)
def withdraw_order_package(order_id: int, op_id: int, request: Request,
                           db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """提交人撤回：待部门审核 / 待COO终审的实例可撤回，撤回复审后重新提交。"""
    o, op = _get_op(db, order_id, op_id, user)
    if op.status not in (VersionStatus.PENDING_DEPT, VersionStatus.PENDING_COO):
        raise HTTPException(status_code=400, detail="当前状态不可撤回")
    # 仅提交人本人/责任人本人或管理员可撤回
    if user.role != "admin" and op.submitted_by != user.id and op.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="仅提交人本人可撤回")
    op.status = VersionStatus.WITHDRAWN
    op.dept_reject_reason = ""
    op.coo_reject_reason = ""
    db.commit()
    db.refresh(op)
    log_event(db, AuditDomain.REVIEW, "op_withdraw", actor=user, ip=client_ip(request),
              target=f"{o.order_no}/{op_id}")
    dept_id = op.package.dept_id if op.package else None
    pcode = op.package.code if op.package else ""
    notify_users(db, dept_reviewer_ids(db, dept_id),
                 title=f"{o.order_no}/{pcode} 已撤回",
                 body=op.package.name_zh if op.package else "", ntype="withdrawn",
                 link=f"/orders/{o.id}", exclude=user.id)
    db.commit()
    return _op_out(op)


# ---------- 附件 ----------
@router.post("/{order_id}/packages/{op_id}/attachments", response_model=list[AttachmentOut])
async def upload_order_attachment(
    order_id: int, op_id: int, request: Request,
    files: list[UploadFile] = File(...),
    batch_no: str = Form(""),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    o, op = _get_op(db, order_id, op_id, user)
    if not can_edit_order_package(user, op):
        raise HTTPException(status_code=403, detail="无权操作该订单资料包")
    if op.locked:
        raise HTTPException(status_code=400, detail="已放行版本不可修改，请移除后重新实例化")
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    created = []
    for f in files:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"不支持的文件类型：{ext}")
        content = await f.read()
        if len(content) > settings.MAX_FILE_MB * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"文件超过 {settings.MAX_FILE_MB}MB 上限")
        import hashlib
        md5 = hashlib.md5(content).hexdigest()
        att_id = next_id()
        stored = save_upload(content, ext)
        att = Attachment(
            id=att_id, order_package_id=op.id, file_name=stored, original_name=f.filename,
            file_size=len(content), md5=md5, mime_type=f.content_type or "application/octet-stream",
            order_no=o.order_no, batch_no=batch_no, uploaded_by=user.id,
        )
        db.add(att)
        created.append(att)
    _reset_status_on_edit(op)
    db.commit()
    for att in created:
        db.refresh(att)
    log_event(db, AuditDomain.ATTACHMENT, "op_upload", actor=user, ip=client_ip(request),
              target=f"{o.order_no}/{op_id}", detail=f"{len(created)} 个文件")
    return created


@router.delete("/{order_id}/packages/{op_id}/attachments/{aid}", response_model=Msg)
def delete_order_attachment(order_id: int, op_id: int, aid: int, request: Request,
                            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    o, op = _get_op(db, order_id, op_id, user)
    if not can_edit_order_package(user, op):
        raise HTTPException(status_code=403, detail="无权操作该订单资料包")
    att = db.get(Attachment, aid)
    if not att or att.order_package_id != op.id:
        raise HTTPException(status_code=404, detail="附件不存在")
    if op.locked:
        raise HTTPException(status_code=400, detail="已放行版本不可修改")
    # 内容哈希命名可能被多个附件行复用，仅当无其它引用时才删除物理文件
    _purge_files(db, [att])
    db.delete(att)
    _reset_status_on_edit(op)
    db.commit()
    log_event(db, AuditDomain.ATTACHMENT, "op_delete", actor=user, ip=client_ip(request),
              target=f"{o.order_no}/{op.id}/{att.original_name}")
    return Msg(msg="已删除")


@router.get("/{order_id}/packages/{op_id}/attachments/{aid}/file")
def download_order_attachment(order_id: int, op_id: int, aid: int, preview: bool = False,
                              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    o, op = _get_op(db, order_id, op_id, user)
    att = db.get(Attachment, aid)
    if not att or att.order_package_id != op.id:
        raise HTTPException(status_code=404, detail="附件不存在")
    path = os.path.join(settings.UPLOAD_DIR, att.file_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="文件不存在")
    log_event(db, AuditDomain.ATTACHMENT, "op_download", actor=user, target=f"{att.original_name}")
    if preview and att.mime_type in PREVIEW_MIME:
        return FileResponse(path, media_type=att.mime_type, filename=att.original_name)
    return FileResponse(path, filename=att.original_name)


@router.get("/{order_id}/export")
def export_order(order_id: int, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(export_viewer)):
    """按订单导出归档清单（CSV），供审计/COO/管理员核查调阅使用。"""
    o = db.get(Order, order_id)
    if not o or o.id not in [x.id for x in _visible_orders_q(db, user).all()]:
        raise HTTPException(status_code=404, detail="订单不存在")
    from fastapi import Response
    fac = db.get(Factory, o.factory_id) if o.factory_id else None
    header = ["工厂", "订单号", "资料包编号", "资料包名称", "状态", "责任人ID", "附件数", "已放行锁定", "截止日期"]
    lines = [",".join(header)]
    for op in sorted(o.packages, key=lambda x: x.package.code if x.package else ""):
        pkg = op.package
        _q = lambda c: str(c).replace(chr(34), chr(34) * 2)
        lines.append(",".join(f'"{_q(c)}"' for c in [
            fac.code if fac else "", o.order_no, pkg.code if pkg else "",
            pkg.name_zh if pkg else "", op.status, str(op.owner_user_id or ""),
            str(len(op.attachments)), "是" if op.locked else "否", op.due_date,
        ]))
    csv = "\n".join(lines)
    log_event(db, AuditDomain.EXPORT, "order_export", actor=user, ip=client_ip(request), target=o.order_no)
    return Response(content="\ufeff" + csv, media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=order_{o.order_no}.csv"})


@router.get("/{order_id}/export/zip")
def export_order_zip(order_id: int, request: Request, db: Session = Depends(get_db),
                     user: User = Depends(export_viewer)):
    """按订单打包全部真实附件（ZIP），供核查调阅/Form 28 回函使用。"""
    import io
    import re
    import zipfile
    from fastapi.responses import StreamingResponse

    o = db.get(Order, order_id)
    if not o or o.id not in [x.id for x in _visible_orders_q(db, user).all()]:
        raise HTTPException(status_code=404, detail="订单不存在")
    fac = db.get(Factory, o.factory_id) if o.factory_id else None
    fac_code = fac.code if fac else "NA"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = [["工厂", "订单号", "资料包编号", "附件原名", "存储文件名", "大小(字节)"]]
        for op in sorted(o.packages, key=lambda x: (x.package.code if x.package else "", x.id)):
            pkg_code = op.package.code if op.package else "NA"
            for att in op.attachments:
                src = os.path.join(settings.UPLOAD_DIR, att.file_name)
                if not os.path.exists(src):
                    continue
                # 安全化归档目录名与文件名
                safe_code = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]", "_", pkg_code)
                safe_name = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]", "_", att.original_name or att.file_name)
                arc = f"{fac_code}/{o.order_no}/{safe_code}/{safe_name}"
                zf.write(src, arc)
                manifest.append([fac_code, o.order_no, pkg_code, att.original_name, att.file_name,
                                 str(att.file_size)])
        _q = lambda c: str(c).replace(chr(34), chr(34) * 2)
        meta = "\n".join(",".join(f'"{_q(c)}"' for c in row) for row in manifest)
        zf.writestr("_manifest.csv", "\ufeff" + meta)
    buf.seek(0)
    log_event(db, AuditDomain.EXPORT, "order_export_zip", actor=user, ip=client_ip(request), target=o.order_no)
    safe_no = re.sub(r"[^A-Za-z0-9_\-]", "_", o.order_no)
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=order_{safe_no}_archive.zip"},
    )


# ---------- 工具 ----------
def _utcnow():
    import datetime
    return datetime.datetime.utcnow()


def _get_op(db: Session, order_id: int, op_id: int, user: User):
    o = db.get(Order, order_id)
    op = db.get(OrderPackage, op_id)
    if not o or not op or op.order_id != o.id or o.id not in [x.id for x in _visible_orders_q(db, user).all()]:
        raise HTTPException(status_code=404, detail="资源不存在")
    return o, op


def _reset_status_on_edit(op: OrderPackage):
    if op.locked:
        return
    if op.status in (VersionStatus.PENDING_DEPT, VersionStatus.PENDING_COO,
                     VersionStatus.RELEASED, VersionStatus.REJECTED):
        op.status = VersionStatus.PENDING_DEPT
        op.dept_reject_reason = ""
        op.coo_reject_reason = ""