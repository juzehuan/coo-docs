"""受控区：仅展示 COO 已终审放行的版本（F-09）。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.constants import VersionStatus
from app.core.rbac import get_current_user
from app.db import get_db
from app.models import Package, PackageVersion, User
from app.schemas import VersionOut

router = APIRouter(prefix="/controlled", tags=["controlled"])


@router.get("", response_model=list[dict])
def controlled_area(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # 审计查看人只读受控区；其余角色也可查看
    released = (
        db.query(PackageVersion)
        .filter(PackageVersion.status == VersionStatus.RELEASED)
        .order_by(PackageVersion.package_id, PackageVersion.version_no)
        .all()
    )
    pkgs = {p.id: p for p in db.query(Package).all()}
    out = []
    for v in released:
        p = pkgs.get(v.package_id)
        if not p:
            continue
        out.append({
            "package_code": p.code,
            "package_name": p.name_zh,
            "version": VersionOut.model_validate(v).model_dump(),
            "attachment_count": len(v.attachments),
            "locked": v.locked,
        })
    return out
