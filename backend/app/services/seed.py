"""初始化种子数据：工厂、部门、12 个资料包、角色账号与示例订单。"""
from sqlalchemy.orm import Session

from app.constants import Role
from app.core.security import hash_password
from app.models import Department, Factory, Order, Package, User, PackageVersion
from app.core.snowflake import next_id

# 工厂（数据隔离边界）
FACTORIES = [
    ("RMA", "RMA 工厂", "RMA Factory", "โรงงาน RMA"),
    ("WEV", "WEV 工厂", "WEV Factory", "โรงงาน WEV"),
]

# 内置 12 个资料包（COO-01 ~ COO-13）
PACKAGE_SEED = [
    ("COO-01", "成品原产地证", "Certificate of Origin", "ใบรับรองถิ่นกำเนิด"),
    ("COO-02", "BOM 物料清单", "BOM", "BOM"),
    ("COO-03", "客户订单与付款", "Customer PO & Payment", "คำสั่งซื้อและชำระเงิน"),
    ("COO-04", "原材料采购订单", "Raw Material PO", "ใบสั่งซื้อวัตถุดิบ"),
    ("COO-05", "原材料及零部件采购订单（供方）", "Supplier PO", "ใบสั่งซื้อซัพพลายเออร์"),
    ("COO-06", "原材料发票", "Raw Material Invoice", "ใบแจ้งหนี้วัตถุดิบ"),
    ("COO-07", "提单", "Bill of Lading", "ใบตราส่ง"),
    ("COO-08", "付款证明", "Payment Proof", "หลักฐานการชำระเงิน"),
    ("COO-09", "生产记录", "Production Records", "บันทึกการผลิต"),
    ("COO-10", "设备清单", "Equipment List", "รายการอุปกรณ์"),
    ("COO-11", "SOP 工艺文件", "SOP Documents", "เอกสาร SOP"),
    ("COO-12", "公司资质", "Company Qualification", "คุณสมบัติบริษัท"),
    ("COO-13", "其他支撑材料", "Other Supporting Docs", "เอกสารสนับสนุนอื่นๆ"),
]

DEPARTMENTS = [
    ("WAI", "外贸/合规", "Trade/Compliance", "การค้า/การปฏิบัติตาม"),
    ("ENG", "工程/采购", "Engineering/Procurement", "วิศวกรรม/จัดซื้อ"),
    ("SAL", "销售", "Sales", "ฝ่ายขาย"),
    ("FIN", "财务", "Finance", "การเงิน"),
    ("LOG", "物流", "Logistics", "โลจิสติกส์"),
    ("PRD", "生产", "Production", "การผลิต"),
    ("ADM", "行政", "Admin", "ธุรการ"),
]

# 账号：用户名 / 显示名 / 角色 / 部门code / 密码
ACCOUNTS = [
    ("admin", "系统管理员", Role.ADMIN, None, "admin123"),
    ("coo", "COO 终审人", Role.COO_REVIEWER, "WAI", "coo123"),
    ("dept_eng", "工程采购经理", Role.DEPT_REVIEWER, "ENG", "dept123"),
    ("dept_fin", "财务经理", Role.DEPT_REVIEWER, "FIN", "dept123"),
    ("submit_eng", "采购专员", Role.SUBMITTER, "ENG", "user123"),
    ("submit_fin", "财务专员", Role.SUBMITTER, "FIN", "user123"),
    ("submit_log", "物流专员", Role.SUBMITTER, "LOG", "user123"),
    ("auditor", "内审员", Role.AUDITOR, None, "audit123"),
]


def seed(db: Session):
    # 工厂
    factory_map = {}
    for i, (code, zh, en, th) in enumerate(FACTORIES):
        existing = db.query(Factory).filter(Factory.code == code).first()
        if existing:
            factory_map[code] = existing
            continue
        f = Factory(code=code, name_zh=zh, name_en=en, name_th=th, sort_order=i)
        db.add(f)
        db.flush()
        factory_map[code] = f

    # 部门
    dept_map = {}
    for code, zh, en, th in DEPARTMENTS:
        existing = db.query(Department).filter(Department.code == code).first()
        if existing:
            dept_map[code] = existing
            continue
        d = Department(code=code, name_zh=zh, name_en=en, name_th=th)
        db.add(d)
        db.flush()
        dept_map[code] = d

    # 资料包
    for i, (code, zh, en, th) in enumerate(PACKAGE_SEED):
        if db.query(Package).filter(Package.code == code).first():
            continue
        pkg = Package(
            code=code, name_zh=zh, name_en=en, name_th=th,
            dept_id=dept_map["ENG"].id if code.startswith("COO-0") else dept_map["WAI"].id,
            required=True, sort_order=i,
        )
        db.add(pkg)

    # 账号（admin/coo/auditor 授权全部工厂；业务账号授权 RMA）
    # 幂等：已存在账号也同步工厂授权，避免历史库/重建时授权缺失。
    for username, name, role, dept_code, pwd in ACCOUNTS:
        u = db.query(User).filter(User.username == username).first()
        if not u:
            u = User(
                id=next_id(),
                username=username,
                password_hash=hash_password(pwd),
                display_name=name,
                dept_id=dept_map[dept_code].id if dept_code else None,
                role=role.value if isinstance(role, Role) else role,
                status="active",
            )
            db.add(u)
            db.flush()
        want = list(factory_map.values()) if role in (Role.ADMIN, Role.COO_REVIEWER, Role.AUDITOR) else (
            [factory_map["RMA"]] if factory_map else [])
        cur = {f.id for f in u.factories}
        for f in want:
            if f.id not in cur:
                u.factories.append(f)

    # 示例订单（每厂 1 单，供快速验收）
    sample = [
        ("RMA", "ORD-RMA-001", "Bintelli Motors", "高尔夫球车 RMA-X1", 120, "2026-10-15"),
        ("WEV", "ORD-WEV-001", "Toyha East", "城市电动小车 WEV-C2", 40, "2026-11-01"),
    ]
    for fac_code, order_no, customer, product, qty, export_date in sample:
        if db.query(Order).filter(Order.order_no == order_no).first():
            continue
        fac = factory_map.get(fac_code)
        if not fac:
            continue
        db.add(Order(
            id=next_id(), factory_id=fac.id, order_no=order_no, customer=customer,
            product=product, quantity=qty, export_date=export_date, status="active",
        ))

    db.commit()
