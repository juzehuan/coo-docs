"""工厂管理（数据隔离边界）。"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.audit import client_ip, log_event
from app.core.rbac import admin_only, get_current_user
from app.db import get_db
from app.models import AuditDomain, Factory, User
from app.schemas import FactoryCreate, FactoryOut, FactoryUpdate

router = APIRouter(prefix="/factories", tags=["factories"])


@router.get("", response_model=list[FactoryOut])
def list_factories(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Factory).order_by(Factory.sort_order, Factory.code).all()


@router.post("", response_model=FactoryOut, status_code=status.HTTP_201_CREATED)
def create_factory(payload: FactoryCreate, request: Request, db: Session = Depends(get_db),
                   _: User = Depends(admin_only)):
    if db.query(Factory).filter(Factory.code == payload.code).first():
        raise HTTPException(status_code=400, detail="工厂编码已存在")
    f = Factory(**payload.model_dump())
    db.add(f)
    db.commit()
    db.refresh(f)
    log_event(db, AuditDomain.ORG, "factory_create", actor=_, ip=client_ip(request), target=f.code)
    return f


@router.patch("/{factory_id}", response_model=FactoryOut)
def update_factory(factory_id: int, payload: FactoryUpdate, request: Request,
                   db: Session = Depends(get_db), _: User = Depends(admin_only)):
    f = db.get(Factory, factory_id)
    if not f:
        raise HTTPException(status_code=404, detail="工厂不存在")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(f, k, v)
    db.commit()
    db.refresh(f)
    log_event(db, AuditDomain.ORG, "factory_update", actor=_, ip=client_ip(request), target=f.code)
    return f