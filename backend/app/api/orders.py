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
from app.core.csv_safe import csv_row
from app.core.http_headers import content_disposition
from app.core.snowflake import next_id
from app.core.storage import save_upload
from app.core.uploads import read_validated_upload
from app.db import get_db
from app.models import (
    Attachment, AuditDomain, Factory, Notification, Order, OrderPackage, Package, User,
)
from app.schemas import (
    AttachmentOut, Msg, OrderCreate, OrderDetailOut, OrderInstanceCreate, OrderOut,
    OrderPackageOut, OrderUpdate, ReviewRequest,
)
from app.services.nas_sync import archive_name, duplicate_names
from app.services.notify import coo_reviewer_ids, dept_reviewer_ids, notify_users

router = APIRouter(prefix="/orders", tags=["orders"])

PREVIEW_MIME = {"application/pdf", "image/png", "image/jpeg", "image/gif", "image/bmp", "image/webp"}


def _factory_ids(user: User, db: Session) -> list[int]:
    """当前账号可见的工厂 ID；admin 可见全部工厂。

    这里**不能**按 status 过滤：本函数同时用于 _visible_orders_q（可见性），
    停用一个工厂会让该厂的历史订单对管理员整体消失、详情返回 404，
    看起来与数据丢失无异；而普通用户走 user.factories 不受影响，
    结果是唯一看不到的反而是管理员。
    "停用"只应阻止新建订单，该约束在 create_order 里按工厂 status 单独判断。
    """
    if user.role == "admin":
        return [f.id for f in db.query(Factory).all()]
    return [f.id for f in user.factories]


def _visible_orders_q(db: Session, user: User):
    fids = _factory_ids(user, db)
    q = db.query(Order).filter(Order.factory_id.in_(fids))
    # 提交人仅能看到自己负责的订单，避免同厂越权查看
    if user.role == "submitter":
        q = q.filter(Order.owner_user_id == user.id)
    return q


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


def _order_row(db: Session, o: Order, fac_map: dict | None = None) -> dict:
    # 列表场景传入 fac_map，避免每行各查一次工厂（两年规模下等于数百条 SQL）
    if fac_map is not None:
        fac = fac_map.get(o.factory_id)
    else:
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
    # selectinload 一次性载入全部订单的资料包实例，工厂用一次查询做成字典：
    # 否则 _order_row 会为每个订单各发一次查询（两年规模下等于数百条 SQL）
    from sqlalchemy.orm import selectinload
    fac_map = {f.id: f for f in db.query(Factory).all()}
    rows = (
        _visible_orders_q(db, user)
        .options(selectinload(Order.packages))
        .order_by(Order.created_at.desc())
        .all()
    )
    return [_order_row(db, o, fac_map) for o in rows]


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(payload: OrderCreate, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    fids = _factory_ids(user, db)
    if payload.factory_id not in fids:
        raise HTTPException(status_code=403, detail="无权为该工厂创建订单")
    # 停用的工厂不得再承接新订单，否则"停用"只是个显示标签、不产生任何约束。
    # 已有订单不受影响（停用表达的是"不再新接单"，不是"抹掉历史"）。
    fac = db.get(Factory, payload.factory_id)
    if fac is not None and fac.status != "active":
        raise HTTPException(status_code=400, detail="该工厂已停用，无法创建新订单")
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
    # 保护已放行归档：单独移除已放行实例已被拒绝，但删除整个订单会经 cascade
    # 连带销毁其下已终审放行且锁定的实例与附件，绕开"已放行不可删除、历史永久留存"的约束。
    locked = [op for op in o.packages
              if op.locked or op.status == VersionStatus.RELEASED]
    if locked:
        raise HTTPException(
            status_code=400,
            detail=f"订单含 {len(locked)} 个已放行归档实例，不可删除；如需停用请将订单状态改为已关闭",
        )
    # 内容哈希命名可能被多个附件行复用，仅当无其它引用时才删除物理文件
    atts = [att for op in o.packages for att in op.attachments]
    # 一并清理指向该订单的通知：link 是字符串字段不受外键约束，订单删除后
    # 这些通知会永久留存成死链接，用户点进去只看到空白页且无从判断原因
    db.query(Notification).filter(Notification.link == f"/orders/{o.id}").delete(
        synchronize_session=False)
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
    op = _lock_op(db, op_id) or op   # 与并发审核串行化
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
    notify_users(db, dept_reviewer_ids(db, dept_id, factory_id=o.factory_id),
                 title=f"{o.order_no}/{op.package.code} 待部门审核",
                 body=op.package.name_zh, ntype="submit", link=f"/orders/{o.id}", exclude=user.id)
    db.commit()
    return _op_out(op)


@router.post("/{order_id}/packages/{op_id}/review", response_model=OrderPackageOut)
def review_order_package(order_id: int, op_id: int, payload: ReviewRequest, request: Request,
                         db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    o, op = _get_op(db, order_id, op_id, user)
    # 加锁重读：与并发的上传/删除附件串行化，避免基于旧快照写回破坏状态机
    op = _lock_op(db, op_id) or op
    from app.core.rbac import can_review_dept, is_coo
    decision, level = payload.decision, payload.level
    # 退回必须填写整改要求：先校验，避免状态/审计日志已落库后才报错
    if decision == ReviewDecision.REJECT and not payload.reason:
        raise HTTPException(status_code=400, detail="退回必须填写整改要求")
    if level == ReviewLevel.DEPT:
        # 先鉴权再校验状态：反过来会让无审核权的用户通过 400/403 的差异探知流程进展
        if not can_review_dept(user, op.package.dept_id if op.package else None,
                               submitted_by=op.submitted_by, db=db):
            raise HTTPException(status_code=403, detail="非本部门审核人")
        if op.status != VersionStatus.PENDING_DEPT:
            raise HTTPException(status_code=400, detail="当前不在待部门审核状态")
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
        if not is_coo(user):
            raise HTTPException(status_code=403, detail="仅 COO 终审人可终审")
        if op.status != VersionStatus.PENDING_COO:
            raise HTTPException(status_code=400, detail="当前不在待COO终审状态")
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
        notify_users(db, coo_reviewer_ids(db, factory_id=o.factory_id),
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
    # 与并发审核串行化：撤回同样是"检查状态后写状态"，不加锁时可与终审放行竞态，
    # 产生 locked=True 却显示已撤回的破损状态（实测 5 次并发中复现 2 次）
    op = _lock_op(db, op_id) or op
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
    notify_users(db, dept_reviewer_ids(db, dept_id, factory_id=o.factory_id),
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
    batch_no: str = Form("", max_length=128),   # 对齐 attachments.batch_no 列宽
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    o, op = _get_op(db, order_id, op_id, user)
    if not can_edit_order_package(user, op):
        raise HTTPException(status_code=403, detail="无权操作该订单资料包")
    if op.locked:
        raise HTTPException(status_code=400, detail="已放行版本不可修改，请移除后重新实例化")
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    # 先把文件读入内存并校验（耗时段），此时尚未落盘、未写库
    pending: list[tuple[bytes, str, str, str, str]] = []
    for f in files:
        content, ext, md5, oname = await read_validated_upload(f, settings.MAX_FILE_MB)
        pending.append((content, ext, md5, oname, (f.content_type or "application/octet-stream")[:128]))
    # 读取期间可能已被并发终审放行：加锁重读后按最新状态再判一次，避免向已锁定版本追加附件
    op = _lock_op(db, op_id)
    if not op:
        raise HTTPException(status_code=404, detail="资源不存在")
    if op.locked or op.status == VersionStatus.RELEASED:
        raise HTTPException(status_code=400, detail="已放行版本不可修改，请移除后重新实例化")
    created = []
    for content, ext, md5, fname, ctype in pending:
        att_id = next_id()
        stored = save_upload(content, ext)
        att = Attachment(
            id=att_id, order_package_id=op.id, file_name=stored, original_name=fname,
            file_size=len(content), md5=md5, mime_type=ctype,
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
    # 加锁重读，避免与并发终审放行竞态导致向已锁定版本删除附件
    op = _lock_op(db, op_id) or op
    att = db.get(Attachment, aid)
    if not att or att.order_package_id != op.id:
        raise HTTPException(status_code=404, detail="附件不存在")
    if op.locked or op.status == VersionStatus.RELEASED:
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
def download_order_attachment(order_id: int, op_id: int, aid: int, request: Request, preview: bool = False,
                              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    o, op = _get_op(db, order_id, op_id, user)
    att = db.get(Attachment, aid)
    if not att or att.order_package_id != op.id:
        raise HTTPException(status_code=404, detail="附件不存在")
    path = os.path.join(settings.UPLOAD_DIR, att.file_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="文件不存在")
    # 记录 IP：规格 F-10 要求下载留痕含 IP，这是追溯核查资料外泄去向的关键线索
    log_event(db, AuditDomain.ATTACHMENT, "op_download", actor=user, ip=client_ip(request),
              target=f"{att.original_name}")
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
        lines.append(csv_row([
            fac.code if fac else "", o.order_no, pkg.code if pkg else "",
            pkg.name_zh if pkg else "", op.status, str(op.owner_user_id or ""),
            str(len(op.attachments)), "是" if op.locked else "否", op.due_date,
        ]))
    csv = "\n".join(lines)
    log_event(db, AuditDomain.EXPORT, "order_export", actor=user, ip=client_ip(request), target=o.order_no)
    return Response(content="\ufeff" + csv, media_type="text/csv",
                    headers={"Content-Disposition": content_disposition(f"order_{o.order_no}.csv")})


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
    fac_code = re.sub(r"[^A-Za-z0-9_\-]", "_", fac.code) if fac else "NA"
    safe_order = re.sub(r"[^A-Za-z0-9_\-]", "_", o.order_no or "order")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = [["工厂", "订单号", "资料包编号", "包内文件名", "附件原名", "存储文件名", "大小(字节)", "MD5"]]
        for op in sorted(o.packages, key=lambda x: (x.package.code if x.package else "", x.id)):
            pkg_code = op.package.code if op.package else "NA"
            # 同一资料包内的同名附件（如多个供应商各自的"发票.pdf"）若都用原文件名，
            # 在 ZIP 里会生成路径完全相同的条目，解压时互相覆盖 —— 交付给核查方的
            # 材料静默缺件，而清单仍列出全部。复用 NAS 归档的命名规则以保持一致。
            dup = duplicate_names(op.attachments)
            for att in op.attachments:
                src = os.path.join(settings.UPLOAD_DIR, att.file_name)
                if not os.path.exists(src):
                    continue
                # 安全化归档目录名与文件名，防路径穿越（ZIP Slip）
                safe_code = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]", "_", pkg_code)
                safe_name = archive_name(att, dup)
                arc = f"{fac_code}/{safe_order}/{safe_code}/{safe_name}"
                zf.write(src, arc)
                manifest.append([fac_code, o.order_no, pkg_code, safe_name, att.original_name,
                                 att.file_name, str(att.file_size), att.md5 or ""])
        meta = "\n".join(csv_row(row) for row in manifest)
        zf.writestr("_manifest.csv", "\ufeff" + meta)
    buf.seek(0)
    log_event(db, AuditDomain.EXPORT, "order_export_zip", actor=user, ip=client_ip(request), target=o.order_no)
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": content_disposition(f"order_{o.order_no}_archive.zip")},
    )


# ---------- 工具 ----------
def _utcnow():
    import datetime
    return datetime.datetime.utcnow()


def _lock_op(db: Session, op_id: int) -> OrderPackage | None:
    """行级锁重读订单资料包实例。

    审核与上传/删除附件都会改写状态机（status/locked），二者并发时若各自基于
    进入时的旧快照写回，会产生 locked=True 但 status=pending_dept 这类破损状态，
    并让已放行版本被追加附件（违反"放行即锁定"的合规约束）。
    改写前统一在此加锁重读，让并发请求串行化：后到者看到的是前者提交后的真实状态。
    populate_existing 强制刷新身份映射中的旧属性；SQLite 无 FOR UPDATE，方言会自动忽略。
    """
    return (
        db.query(OrderPackage)
        .populate_existing()
        .with_for_update()
        .filter(OrderPackage.id == op_id)
        .first()
    )


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