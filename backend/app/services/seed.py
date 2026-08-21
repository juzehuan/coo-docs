"""初始化种子数据：工厂、部门、18 个资料包、角色账号与示例订单。"""
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

# 内置 18 个资料包（COO-01 ~ COO-18），对齐 RMA 美国审查资料分类（docs/美国审查资料）
# 元组：编号 / 中文名 / 英文名 / 泰文名 / 责任部门code / 核查重点
PACKAGE_SEED = [
    ("COO-01", "成品原产地证及制造商声明", "Certificate of Origin & Manufacturer Declaration",
     "ใบรับรองถิ่นกำเนิดและคำรับรองผู้ผลิต", "WAI", "证书、车型/批次与出口批次一一对应，制造商声明完整"),
    ("COO-02", "BOM、物料清单及原产地/价值信息", "BOM & Origin/Value Information",
     "BOM และข้อมูลถิ่นกำเนิด/มูลค่า", "ENG", "部件国别、价值、供应商及加工实质转型可追溯"),
    ("COO-03", "客户采购订单 / 商务合同", "Customer PO / Commercial Contract",
     "คำสั่งซื้อลูกค้า / สัญญาทางการค้า", "SAL", "PO、合同、修订及卖方确认完整对应"),
    ("COO-04", "成品销售发票及客户付款证明", "Finished Goods Invoice & Payment Proof",
     "ใบแจ้งหนี้สินค้าสำเร็จรูปและหลักฐานการชำระเงิน", "FIN", "成品发票、付款凭证与交易参与方信息可验证"),
    ("COO-05", "原材料/零部件采购订单", "Raw Material / Component PO",
     "ใบสั่งซื้อวัตถุดิบ/ชิ้นส่วน", "ENG", "按每个供应商对应订单逐份上传 PO"),
    ("COO-06", "原材料/零部件供应商发票", "Supplier Invoice (Raw Material / Component)",
     "ใบแจ้งหนี้ซัพพลายเออร์ (วัตถุดิบ/ชิ้นส่วน)", "ENG", "按每个供应商对应订单逐份上传供应商发票"),
    ("COO-07", "原材料/零部件付款证明", "Payment Proof (Raw Material / Component)",
     "หลักฐานการชำระเงิน (วัตถุดิบ/ชิ้นส่วน)", "FIN", "按每个供应商对应订单逐份上传付款证明"),
    ("COO-08", "原材料/零部件进口提单及运输凭证", "Bill of Lading & Transport Docs (Import)",
     "ใบตราส่งและเอกสารขนส่ง (นำเข้า)", "LOG", "按船运批次归档提单及运输凭证"),
    ("COO-09", "原材料采购全链路凭证", "Raw Material Full-Chain Evidence",
     "หลักฐานห่วงโซ่การจัดซื้อวัตถุดิบครบวงจร", "ENG", "原料 PO/发票/提单/付款/清关/入库全链路可追溯"),
    ("COO-10", "生产计划、装配及车间生产记录", "Production Plan, Assembly & Floor Records",
     "แผนการผลิต การประกอบ และบันทึกการผลิตหน้างาน", "PRD", "生产计划、装配及车间日/班次记录完整"),
    ("COO-11", "生产检验及质量记录", "Production Inspection & Quality Records",
     "บันทึกการตรวจสอบและการควบคุมคุณภาพการผลิต", "QAL", "检验、扭矩/终检等质量记录完整"),
    ("COO-12", "包装、装柜及出货记录", "Packing, Container Loading & Shipment Records",
     "บันทึกการบรรจุ การโหลดตู้ และการส่งออก", "LOG", "按批次/柜号归档装柜及出货记录（含装柜照片）"),
    ("COO-13", "生产设备、工装及产能资料", "Production Equipment, Tooling & Capacity",
     "ข้อมูลอุปกรณ์ แม่พิมพ์ และกำลังการผลิต", "PRD", "生产设备、工装清单与产能匹配"),
    ("COO-14", "SOP、作业指导书及工艺流程", "SOP, Work Instructions & Process Flow",
     "SOP เอกสารขั้นตอนการทำงาน และกระบวนการผลิต", "ENG", "工艺流程、SOP 与作业指导书完整"),
    ("COO-15", "工厂、生产现场照片及视频证据", "Factory & Production Site Photo/Video Evidence",
     "หลักฐานภาพถ่าย/วิดีโอโรงงานและหน้างานผลิต", "PRD", "工厂内外部照片与关键工序视频证据"),
    ("COO-16", "公司资质、许可证及登记资料", "Company Qualifications, Licenses & Registration",
     "คุณสมบัติบริษัท ใบอนุญาต และทะเบียน", "ADM", "营业执照、资质及登记资料有效"),
    ("COO-17", "客户核查要求 / 内部对照清单", "Customer Audit Requirements / Internal Checklist",
     "ข้อกำหนดการตรวจสอบลูกค้า / รายการตรวจสอบภายใน", "WAI", "客户核查要求与内部对照清单逐项覆盖"),
    ("COO-18", "待人工确认的资料类型", "Pending Manual Confirmation",
     "รอการยืนยันด้วยคน", "WAI", "待人工核实的资料类型，由关务合规牵头确认归口"),
]

DEPARTMENTS = [
    ("WAI", "外贸/合规", "Trade/Compliance", "การค้า/การปฏิบัติตาม"),
    ("ENG", "工程/采购", "Engineering/Procurement", "วิศวกรรม/จัดซื้อ"),
    ("SAL", "销售", "Sales", "ฝ่ายขาย"),
    ("FIN", "财务", "Finance", "การเงิน"),
    ("LOG", "物流", "Logistics", "โลจิสติกส์"),
    ("PRD", "生产", "Production", "การผลิต"),
    ("ADM", "行政", "Admin", "ธุรการ"),
    ("QAL", "质量", "Quality", "คุณภาพ"),
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

    # 资料包（按 RMA 美国审查 18 类；dept 由种子显式指定）
    for i, (code, zh, en, th, dept_code, focus) in enumerate(PACKAGE_SEED):
        if db.query(Package).filter(Package.code == code).first():
            continue
        pkg = Package(
            code=code, name_zh=zh, name_en=en, name_th=th,
            dept_id=dept_map[dept_code].id,
            review_focus=focus, required=True, sort_order=i,
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
