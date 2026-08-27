"""客户订单管理：订单 CRUD、订单-资料包实例化、附件与审核（方案核心数据模型）。"""
import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants import ALLOWED_EXTENSIONS, ReviewDecision, ReviewLevel, VersionStatus
from app.core.heavy import heavy_slot
from app.services import export_jobs, exporter
from app.core.audit import client_ip, log_event
from app.core.config import settings
from app.core import dl_ticket
from app.core.i18n import local_name, status_label, t
from app.core.rbac import (
    can_edit_order, can_edit_order_package, export_viewer,
    factory_ids as _factory_ids, get_current_user,
    optional_current_user, user_from_download_ticket,
)
from app.core.http_headers import content_disposition
from app.core.xlsx import XLSX_MEDIA_TYPE, build_xlsx
from app.core.zipout import compression_for, zip_builder, zip_response
from app.core.snowflake import next_id
from app.core.storage import purge_files, save_upload, storage_guard
from app.core.filetype import guess_mime
from app.core.uploads import read_validated_upload, sanitize_name
from app.db import get_db
from app.models import (
    Attachment, AuditDomain, Factory, Notification, Order, OrderPackage, Package, User,
)
from app.schemas import (
    AttachmentOut, Msg, OrderCreate, OrderDetailOut, OrderInstanceCreate, OrderList, OrderOut,
    OrderPackageOut, OrderUpdate, ReviewRequest,
)
from app.services.nas_sync import archive_name, duplicate_names
from app.services.notify import notify_params, coo_reviewer_ids, dept_reviewer_ids, notify_users

router = APIRouter(prefix="/orders", tags=["orders"])

PREVIEW_MIME = {"application/pdf", "image/png", "image/jpeg", "image/gif", "image/bmp", "image/webp"}


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
        "factory_name": local_name(fac),
        "package_count": total,
        "released_count": released,
        "completion": completion,
    }


def _op_out(op: OrderPackage, db: Session | None = None, user: User | None = None) -> dict:
    pkg = op.package
    out = OrderPackageOut.model_validate(op).model_dump()
    out["package_code"] = pkg.code if pkg else ""
    out["package_name"] = local_name(pkg)
    out["package_dept_id"] = pkg.dept_id if pkg else None
    out["attachment_count"] = len(op.attachments)
    out["attachments"] = [AttachmentOut.model_validate(a).model_dump() for a in op.attachments]
    # 是否真的可以部门审核：前端只按"角色+部门"判断，看不到职责分离这条规则，
    # 于是审核人给自己提交的内容也会看到「通过/退回」按钮，点下去必然 403。
    # 该规则需要查库（本部门是否还有其他审核人），只能由后端下发。
    # 资料包线早已下发 reviewable_dept，订单线此前没有——又一处两条线的不对称。
    if db is not None and user is not None:
        from app.core.rbac import dept_review_block_reason
        out["reviewable_dept"] = dept_review_block_reason(
            user, pkg.dept_id if pkg else None, submitted_by=op.submitted_by, db=db) is None
    return out


# ---------- 列表 / 详情 ----------
@router.get("", response_model=OrderList)
def list_orders(q: str | None = Query(None, max_length=128),
                limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """订单列表：服务端搜索 + 分页。

    此前一次性下发全部订单、由前端做关键词过滤。订单是唯一随业务量无限增长的
    列表（实测 126 条 46KB，约 365 字节/条，千单规模即 365KB，每次打开页面都要
    重新拉一遍），而界面一次只显示十几行。

    搜索必须同时挪到服务端：只加分页会让关键词只在当前页内匹配，用户搜不到
    却以为"没有这张订单"——与第 35 轮审计导出忽略筛选属同一类静默错误。
    """
    from sqlalchemy import or_
    from sqlalchemy.orm import selectinload
    base = _visible_orders_q(db, user)
    if q and q.strip():
        kw = q.strip()
        # autoescape：转义 % 与 _，否则用户输入的通配符会悄悄放大结果集（第 37 轮同因）
        base = base.filter(or_(
            Order.order_no.contains(kw, autoescape=True),
            Order.customer.contains(kw, autoescape=True),
            Order.product.contains(kw, autoescape=True),
        ))
    total = base.with_entities(func.count(Order.id)).scalar() or 0
    fac_map = {f.id: f for f in db.query(Factory).all()}
    rows = (
        base.options(selectinload(Order.packages))
        # 必须带唯一兜底列：created_at 是**秒级精度**（datetime 无小数秒），同秒创建的
        # 订单之间顺序不确定，而 offset 分页要求全序。第 66 轮实测（127 张订单、
        # 只有 71 个不同时间戳）：每页 10 条翻完全部时，**3 张订单重复出现、另 3 张
        # 一次都没出现**；每页 25 条各 1 个；每页 20 条恰好干净——取决于页边界落在
        # 并列的哪一侧。用户翻完 127 行、数目对得上，却始终没看见那 3 张订单。
        # packages.py 早已因同一原因改用雪花 ID 排序，这里是同一个坑的另一处。
        .order_by(Order.created_at.desc(), Order.id.desc())
        .offset(offset).limit(limit)
        .all()
    )
    return {"total": total, "items": [_order_row(db, o, fac_map) for o in rows]}


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
    base["packages"] = [_op_out(op, db, user) for op in sorted(o.packages, key=lambda x: x.package.code if x.package else "")]
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
    purge_files(db, atts)
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
    # 界面的「添加资料包」下拉已经不列停用包，但后端此前不拦——第 82 轮实测
    # 直接调 API 照样 201。与第 28 轮工厂停用同一模式：前端藏了不等于后端拦了。
    if pkg.status != "active":
        raise HTTPException(status_code=400, detail="该资料包已停用，不可再加入订单")
    if any(op.package_id == pkg.id for op in o.packages):
        raise HTTPException(status_code=400, detail="该资料包已在订单中")
    op = OrderPackage(
        order_id=o.id,
        package_id=pkg.id,
        project_code=settings.PROJECT_CODE,
        status=VersionStatus.DRAFT,
        # 提交人给自己的订单加资料包时，实例归他自己——模板负责人（pkg.owner_user_id）
        # 是"资料包线"的分工（部门经理维护常备档案），不该顺带接管订单实例。
        # 原来的顺序把提交人那一档写在 pkg.owner_user_id 之后，而模板负责人实测 18 个
        # 全部有值，那一档等于死代码：采购专员建完订单，实例负责人成了部门经理，
        # 他既传不了附件，待办里也看不到这条活，反倒是部门经理收到"指派给你"。
        # 管理员 / COO 添加时仍沿用模板负责人——那才是"派活给部门"的场景。
        owner_user_id=(payload.owner_user_id
                       or (user.id if user.role == "submitter" else None)
                       or pkg.owner_user_id),
        required=payload.required,
        due_date=payload.due_date or pkg.due_date,
    )
    db.add(op)
    db.commit()
    db.refresh(op)
    log_event(db, AuditDomain.PACKAGE, "order_package_add", actor=user, ip=client_ip(request),
              target=f"{o.order_no}/{pkg.code}")
    # 通知被指派的责任人：指派资料包就是给人派活，而此前**没有任何信号**——
    # 第 64 轮实测把 3 个资料包指派给某提交人后，他的通知 +0、待办 +0，
    # 只能靠自己翻订单列表才发现有活。收集资料正是提交人的本职工作，
    # 而他的工作队列此前只显示"被退回的返工"，从不显示"新指派的活"。
    if op.owner_user_id:
        notify_users(db, [op.owner_user_id],
                     title=f"{o.order_no}/{pkg.code} 指派给你",
                     ntype="assigned", link=f"/orders/{o.id}",
                     exclude=user.id,          # 自己指派给自己不必通知
                     params=notify_params(f"{o.order_no}/{pkg.code}", pkg))
        db.commit()
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
    purge_files(db, atts)
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
                 body=op.package.name_zh, ntype="submit", link=f"/orders/{o.id}", exclude=user.id,
                 params=notify_params(f"{o.order_no}/{op.package.code}", op.package))
    db.commit()
    return _op_out(op)


@router.post("/{order_id}/packages/{op_id}/review", response_model=OrderPackageOut)
def review_order_package(order_id: int, op_id: int, payload: ReviewRequest, request: Request,
                         db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    o, op = _get_op(db, order_id, op_id, user)
    # 加锁重读：与并发的上传/删除附件串行化，避免基于旧快照写回破坏状态机
    op = _lock_op(db, op_id) or op
    from app.core.rbac import dept_review_block_reason, is_coo
    decision, level = payload.decision, payload.level
    # 退回必须填写整改要求：先校验，避免状态/审计日志已落库后才报错
    if decision == ReviewDecision.REJECT and not payload.reason:
        raise HTTPException(status_code=400, detail="退回必须填写整改要求")
    if level == ReviewLevel.DEPT:
        # 先鉴权再校验状态：反过来会让无审核权的用户通过 400/403 的差异探知流程进展
        blocked = dept_review_block_reason(user, op.package.dept_id if op.package else None,
                                           submitted_by=op.submitted_by, db=db)
        if blocked:
            raise HTTPException(status_code=403, detail=blocked)
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
                     params=notify_params(f"{o.order_no}/{pcode}", op.package),
                     link=f"/orders/{o.id}", exclude=user.id)
    elif recipient:
        if decision == ReviewDecision.APPROVE:
            notify_users(db, [recipient], title=f"{o.order_no}/{pcode} 已放行归档",
                         body=op.package.name_zh if op.package else "", ntype="released",
                         params=notify_params(f"{o.order_no}/{pcode}", op.package),
                         link=f"/orders/{o.id}", exclude=user.id)
        else:
            notify_users(db, [recipient], title=f"{o.order_no}/{pcode} 被退回",
                         body=op.package.name_zh if op.package else "", ntype="rejected",
                         params=notify_params(f"{o.order_no}/{pcode}", op.package),
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
                 params=notify_params(f"{o.order_no}/{pcode}", op.package),
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
        content, ext, md5, oname, ctype = await read_validated_upload(f, settings.MAX_FILE_MB)
        pending.append((content, ext, md5, oname, ctype))
    # 读取期间可能已被并发终审放行：加锁重读后按最新状态再判一次，避免向已锁定版本追加附件
    op = _lock_op(db, op_id)
    if not op:
        raise HTTPException(status_code=404, detail="资源不存在")
    if op.locked or op.status == VersionStatus.RELEASED:
        raise HTTPException(status_code=400, detail="已放行版本不可修改，请移除后重新实例化")
    created = []
    # 临界区必须覆盖到 commit：命中去重分支时不会重新落盘，而未提交的附件行
    # 对别的会话不可见——若此间别处回收了该物理文件，新附件就会指向一个不存在
    # 的文件（详见 storage.storage_guard）
    with storage_guard():
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
    purge_files(db, [att])
    db.delete(att)
    _reset_status_on_edit(op)
    db.commit()
    log_event(db, AuditDomain.ATTACHMENT, "op_delete", actor=user, ip=client_ip(request),
              target=f"{o.order_no}/{op.id}/{att.original_name}")
    return Msg(msg="已删除")


@router.post("/{order_id}/packages/{op_id}/attachments/{aid}/ticket")
def issue_order_download_ticket(order_id: int, op_id: int, aid: int,
                                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """签发下载票据（先走常规权限判定，通过后才发）。"""
    o, op = _get_op(db, order_id, op_id, user)
    att = db.get(Attachment, aid)
    if not att or att.order_package_id != op.id:
        raise HTTPException(status_code=404, detail="附件不存在")
    return {"ticket": dl_ticket.issue(aid, user.id), "expires_in": dl_ticket.TICKET_TTL_SECONDS}


@router.get("/{order_id}/packages/{op_id}/attachments/{aid}/file")
def download_order_attachment(order_id: int, op_id: int, aid: int, request: Request, preview: bool = False,
                              ticket: str | None = None,
                              db: Session = Depends(get_db),
                              user: User | None = Depends(optional_current_user)):
    user = user_from_download_ticket(request, aid, ticket, db) or user
    if user is None:
        raise HTTPException(status_code=401, detail="无效或过期的凭证")
    o, op = _get_op(db, order_id, op_id, user)
    att = db.get(Attachment, aid)
    if not att or att.order_package_id != op.id:
        raise HTTPException(status_code=404, detail="附件不存在")
    path = os.path.join(settings.UPLOAD_DIR, att.file_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="文件不存在")
    # 记录 IP：规格 F-10 要求下载留痕含 IP，这是追溯核查资料外泄去向的关键线索。
    #
    # target 必须带上订单与实例，只写文件名定位不了对象：F-10 要求"支持按人员、
    # 时间、**资料包**查询"，而工厂场景里「装箱单.pdf」「检验报告.pdf」这类名字
    # 天然跨订单重复——本库里 `coo_test_doc.pdf` 就有 65 条附件记录，散落在
    # 32 个订单实例、33 个版本上，一条只写文件名的下载留痕对应 65 个候选附件。
    # 上传与删除本来就记了 `订单号/实例ID[/文件名]`，唯独下载没记，
    # 而下载恰恰是**唯一把证据带出系统**的动作，最需要追溯。（第 60 轮）
    log_event(db, AuditDomain.ATTACHMENT, "op_download", actor=user, ip=client_ip(request),
              target=f"{o.order_no}/{op.id}/{att.original_name}",
              # 同一端点既服务预览也服务下载，此前一律记成"下载"——
              # 合规日志把没发生的事记成发生了，本身就是缺陷
              detail="预览" if preview else "下载")
    # 按扩展名判定而非库里存的 mime_type：历史附件的 mime_type 来自客户端声明，
    # 一份真 PDF 若当初被声明成 text/plain，至今仍无法预览
    mime = guess_mime(os.path.splitext(att.original_name or att.file_name or "")[1])
    # 取 basename 兜底：上传侧已剥离路径分隔符，但库里的历史记录仍可能带着
    # `../../etc/passwd.txt` 这类原名，而它会原样进 Content-Disposition
    dl_name = sanitize_name(os.path.basename(att.original_name or "")) or att.file_name
    if preview and mime in PREVIEW_MIME:
        return FileResponse(path, media_type=mime, filename=dl_name)
    return FileResponse(path, filename=dl_name)


@router.get("/{order_id}/export")
def export_order(order_id: int, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(export_viewer),
                 _heavy: None = Depends(heavy_slot)):
    """按订单导出资料清单（Excel），供审计/COO/管理员核查调阅使用。"""
    # 生成逻辑在 services/exporter.py，与异步导出作业共用同一份实现
    try:
        fname, path, _n = exporter.order_xlsx(db, user, {"order_id": order_id}, _visible_ids)
    except exporter.ExportGone as e:
        raise HTTPException(status_code=404, detail=str(e))
    log_event(db, AuditDomain.EXPORT, "order_export", actor=user, ip=client_ip(request),
              target=order_id)
    return exporter.deliver(path, XLSX_MEDIA_TYPE, fname)


@router.get("/{order_id}/export/zip")
def export_order_zip(order_id: int, request: Request, db: Session = Depends(get_db),
                     user: User = Depends(export_viewer),
                     _heavy: None = Depends(heavy_slot)):
    """按订单打包全部真实附件（ZIP），供核查调阅/Form 28 回函使用。"""
    # 生成逻辑在 services/exporter.py，与异步导出作业共用同一份实现
    try:
        fname, path, _n = exporter.order_zip(db, user, {"order_id": order_id}, _visible_ids)
    except exporter.ExportGone as e:
        raise HTTPException(status_code=404, detail=str(e))
    log_event(db, AuditDomain.EXPORT, "order_export_zip", actor=user, ip=client_ip(request),
              target=order_id)
    return zip_response(path, content_disposition(fname))


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


def _visible_ids(db: Session, user: User) -> set:
    """当前用户可见的订单 ID 集合。可见性规则只此一处，导出生成器由此获取。"""
    return {x.id for x in _visible_orders_q(db, user).all()}


# ---- 注册为异步导出作业类型（说明见 api/audit.py 末尾）----
def _order_xlsx_job(db, user, params):
    return exporter.order_xlsx(db, user, params, _visible_ids)


def _order_zip_job(db, user, params):
    return exporter.order_zip(db, user, params, _visible_ids)


def _order_job_check(db, user, params):
    """与同步端点同一套：先过 export_viewer，再确认这张订单对他可见。"""
    export_viewer(user)
    oid = int(params.get("order_id") or 0)
    if oid not in _visible_ids(db, user):
        raise HTTPException(status_code=404, detail="订单不存在")


export_jobs.register("order_xlsx", _order_xlsx_job, _order_job_check)
export_jobs.register("order_zip", _order_zip_job, _order_job_check)
