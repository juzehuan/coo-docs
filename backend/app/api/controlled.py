"""受控区：仅展示 COO 已终审放行的版本，并支持归档下载（F-09）。"""
import io
import os
import re
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.constants import AuditDomain, VersionStatus
from app.core.heavy import heavy_slot
from app.services import export_jobs, exporter
from app.core.audit import client_ip, log_event
from app.core.config import settings
from app.core.i18n import local_name, t
from app.core.xlsx import build_xlsx
from app.core.zipout import compression_for, zip_builder, zip_response
from app.core.http_headers import content_disposition
from app.services.nas_sync import archive_name, duplicate_names
from app.core.rbac import require_roles
from app.db import get_db
from app.models import Order, OrderPackage, Package, PackageVersion, User
from app.schemas import AttachmentOut

router = APIRouter(prefix="/controlled", tags=["controlled"])

# 受控区（F-09）为只读调阅区：部门审核人、COO 终审人、管理员，以及审计查看人。
# 规格书角色表明确「审计查看人：只读调阅已放行资料，导出清单」——受控区正是内审/
# 外部核查配合人员的主要工作面，此处若排除 auditor 会让该角色无法履行本职。
# 本模块只提供查看与归档下载，不含任何写入口，故对 auditor 开放不违反其只读约束。
controlled_access = require_roles("dept_reviewer", "coo_reviewer", "auditor", "admin")


def _visible_pkg_ids(db: Session, user: User) -> set:
    """受控区可见范围：部门审核人仅本部门包；COO/审计查看人/管理员可见全部。"""
    q = db.query(Package)
    if user.role == "dept_reviewer":
        q = q.filter(Package.dept_id == user.dept_id)
    return {p.id for p in q.all()}


def _visible_factory_ids(db: Session, user: User) -> set:
    """受控区订单线的工厂可见范围。

    工厂是本系统的数据隔离边界（规格 2.4）：受控区若不做同样的过滤，
    就会从这条旁路泄露未授权工厂的订单号与资料包内容（第 13 轮通知泄漏同源）。
    """
    from app.models import Factory
    if user.role == "admin":
        return {f.id for f in db.query(Factory).all()}
    return {f.id for f in user.factories}


@router.get("", response_model=dict)
def controlled_area(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                    db: Session = Depends(get_db), user: User = Depends(controlled_access)):
    """受控区清单：COO 已终审放行的全部受控单元。

    此前只查 PackageVersion，**遗漏了订单资料包实例这条线**——而订单线才是
    日常主要工作流（客户订单 → 资料包实例 → 双级审核 → 放行锁定）。实测库中
    32 条已放行版本全部可见，而 31 条已放行且锁定的订单实例在受控区完全看不到。
    受控区是审计员与外部核查方调阅已放行资料的主要工作面，缺一半等于查不全。
    NAS 归档、ZIP 交付、工作台统计本就覆盖两条线，受控区是唯一的例外。
    """
    visible = _visible_pkg_ids(db, user)
    fids = _visible_factory_ids(db, user)
    pkgs = {p.id: p for p in db.query(Package).all()}

    # 分两阶段：先只取排序所需的轻量列（不含附件），排序分页后，
    # 才为**本页**加载完整对象与附件。
    # 直接把全部已放行内容连同附件读进内存再切片，会让响应体积有界、
    # 数据库工作量却依旧随放行总量增长（实测 63 条时单请求已 207ms）。
    keys: list[tuple] = []

    for vid, pid, vno in (
        db.query(PackageVersion.id, PackageVersion.package_id, PackageVersion.version_no)
        .filter(PackageVersion.status == VersionStatus.RELEASED,
                PackageVersion.package_id.in_(visible)).all()
    ):
        p = pkgs.get(pid)
        if p:
            keys.append((p.code, vno or "", "version", vid))

    if fids:
        for opid, pid, ono in (
            db.query(OrderPackage.id, OrderPackage.package_id, Order.order_no)
            .join(Order, OrderPackage.order_id == Order.id)
            .filter(OrderPackage.status == VersionStatus.RELEASED,
                    OrderPackage.locked.is_(True),
                    OrderPackage.package_id.in_(visible),
                    Order.factory_id.in_(fids)).all()
        ):
            p = pkgs.get(pid)
            if p:
                keys.append((p.code, ono or "", "order", opid))

    # 带上类型与唯一 ID：Python 的 sort 虽然稳定，但输入顺序来自上面两条**没有
    # ORDER BY** 的查询，数据库返回顺序一变，并列项的相对位置就跟着变——
    # 而下面是 offset 切片分页，同样要求全序（同 orders 的问题）。
    keys.sort(key=lambda k: (k[0], k[1], k[2], k[3]))
    total = len(keys)
    page = keys[offset:offset + limit]

    # 仅为本页加载完整对象（含附件）
    vids = [k[3] for k in page if k[2] == "version"]
    opids = [k[3] for k in page if k[2] == "order"]
    vmap = {v.id: v for v in db.query(PackageVersion).filter(PackageVersion.id.in_(vids)).all()} if vids else {}
    omap = {}
    if opids:
        for op in db.query(OrderPackage).filter(OrderPackage.id.in_(opids)).all():
            omap[op.id] = op
    order_map = {o.id: o for o in db.query(Order).filter(
        Order.id.in_([op.order_id for op in omap.values()])).all()} if omap else {}

    items = []
    for code, subject, kind, oid in page:
        if kind == "version":
            v = vmap.get(oid)
            p = pkgs.get(v.package_id) if v else None
            if not v or not p:
                continue
            items.append({
                "kind": "version", "key": f"v-{v.id}",
                "package_code": p.code, "package_name": local_name(p),
                "subject": v.version_no,
                "attachment_count": len(v.attachments), "locked": v.locked,
                "released_at": v.coo_reviewed_at.isoformat() if v.coo_reviewed_at else None,
                "ids": {"pkg_id": str(p.id), "version_id": str(v.id)},
                "attachments": [AttachmentOut.model_validate(a).model_dump() for a in v.attachments],
            })
        else:
            op = omap.get(oid)
            p = pkgs.get(op.package_id) if op else None
            o = order_map.get(op.order_id) if op else None
            if not op or not p or not o:
                continue
            items.append({
                "kind": "order", "key": f"o-{op.id}",
                "package_code": p.code, "package_name": local_name(p),
                "subject": o.order_no,
                "attachment_count": len(op.attachments), "locked": op.locked,
                "released_at": op.coo_reviewed_at.isoformat() if op.coo_reviewed_at else None,
                "ids": {"order_id": str(o.id), "op_id": str(op.id)},
                "attachments": [AttachmentOut.model_validate(a).model_dump() for a in op.attachments],
            })

    return {"total": total, "items": items}


@router.get("/orders/{order_id}/packages/{op_id}/export/zip")
def download_released_order_zip(order_id: int, op_id: int, request: Request,
                                db: Session = Depends(get_db),
                                user: User = Depends(controlled_access),
                                _heavy: None = Depends(heavy_slot)):
    """受控区归档下载（订单线）：打包某已放行订单实例的附件为 ZIP。"""
    # 生成逻辑在 services/exporter.py，与异步导出作业共用同一份实现
    fname, path, _n = exporter.controlled_order_zip(
        db, user, {"order_id": order_id, "op_id": op_id}, _check_order)
    o = db.get(Order, order_id)
    p = db.get(Package, db.get(OrderPackage, op_id).package_id)
    log_event(db, AuditDomain.EXPORT, "controlled_export_zip", actor=user,
              ip=client_ip(request), target=f"{p.code if p else ''}/{o.order_no}")
    return zip_response(path, content_disposition(fname))


@router.get("/{pkg_id}/versions/{vid}/export/zip")
def download_released_zip(pkg_id: int, vid: int, request: Request,
                          db: Session = Depends(get_db),
                          user: User = Depends(controlled_access),
                          _heavy: None = Depends(heavy_slot)):
    """受控区归档下载：打包某受控版本的已放行真实附件为 ZIP，供核查调阅/Form 28 回函。"""
    # 生成逻辑在 services/exporter.py，与异步导出作业共用同一份实现
    fname, path, _n = exporter.controlled_version_zip(
        db, user, {"pkg_id": pkg_id, "version_id": vid}, _check_version)
    p = db.get(Package, pkg_id)
    v = db.get(PackageVersion, vid)
    log_event(db, AuditDomain.EXPORT, "controlled_export_zip", actor=user,
              ip=client_ip(request), target=f"{p.code}/{v.version_no}")
    return zip_response(path, content_disposition(fname))


def _check_order(db: Session, user: User, params: dict):
    """受控区订单线的可见性与受控状态判定。同步端点与作业共用同一套规则。"""
    op = db.get(OrderPackage, int(params.get("op_id") or 0))
    o = db.get(Order, int(params.get("order_id") or 0))
    if (not op or not o or op.order_id != o.id
            or op.status != VersionStatus.RELEASED or not op.locked):
        raise HTTPException(status_code=404, detail="受控内容不存在")
    if (op.package_id not in _visible_pkg_ids(db, user)
            or o.factory_id not in _visible_factory_ids(db, user)):
        raise HTTPException(status_code=404, detail="受控内容不存在")
    return o, op, db.get(Package, op.package_id)


def _check_version(db: Session, user: User, params: dict):
    """受控区版本线的可见性与受控状态判定。"""
    v = db.get(PackageVersion, int(params.get("version_id") or 0))
    pkg_id = int(params.get("pkg_id") or 0)
    p = db.get(Package, pkg_id)
    if not v or v.package_id != pkg_id or v.status != VersionStatus.RELEASED:
        raise HTTPException(status_code=404, detail="受控版本不存在")
    if not p or p.id not in _visible_pkg_ids(db, user):
        raise HTTPException(status_code=404, detail="受控版本不存在")
    return p, v


# ---- 注册为异步导出作业类型（说明见 api/audit.py 末尾）----
def _co_zip_job(db, user, params):
    return exporter.controlled_order_zip(db, user, params, _check_order)


def _cv_zip_job(db, user, params):
    return exporter.controlled_version_zip(db, user, params, _check_version)


# 直接用本模块的 controlled_access（它就定义在上面），不要在函数内延迟导入：
# 延迟导入的错误**预检看不见**——preflight.sh 只做模块导入，函数体内的 import
# 要到真正调用时才炸。第一版写成从 app.core.rbac 导入（那里根本没有这个名字），
# 预检通过、部署上去、提交作业时才 500。
def _co_check(db, user, params):
    controlled_access(user)
    _check_order(db, user, params)


def _cv_check(db, user, params):
    controlled_access(user)
    _check_version(db, user, params)


export_jobs.register("controlled_order_zip", _co_zip_job, _co_check)
export_jobs.register("controlled_version_zip", _cv_zip_job, _cv_check)
