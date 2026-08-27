"""初始化种子数据：工厂、部门、18 个资料包、角色账号与示例订单。

SEED_DEMO_DATA=false（生产）时：不创建演示账号与示例订单，仅确保 admin 存在，
且 admin 初始密码随机生成、只在启动日志打印一次。
"""
import logging

from sqlalchemy.orm import Session

from app.constants import Role
from app.core.config import settings
from app.core.security import generate_temp_password, hash_password
from app.models import Department, Factory, Order, Package, User, PackageVersion
from app.core.snowflake import next_id

logger = logging.getLogger("app.seed")

# 工厂（数据隔离边界）
FACTORIES = [
    ("RMA", "RMA 工厂", "RMA Factory", "โรงงาน RMA"),
    ("WEV", "WEV 工厂", "WEV Factory", "โรงงาน WEV"),
]

# 内置 18 个资料包（COO-01 ~ COO-18），对齐 RMA 美国审查资料分类（docs/美国审查资料）
# 元组：编号 / 中文名 / 英文名 / 泰文名 / 责任部门code / 核查重点
# 公司级资料包：跨订单不变，只在资料包线维护一份，加进订单时引用最新已放行版本。
# 其余按"随单"处理（采购订单、发票、提单、付款证明、生产记录……一票一套）。
# 交付现场可在「资料包」页逐个改，这里只是一份合理的出厂默认值。
COMPANY_LEVEL = {
    "COO-13",   # 生产设备、工装及产能资料
    "COO-14",   # SOP、作业指导书及工艺流程
    "COO-15",   # 工厂、生产现场照片及视频证据
    "COO-16",   # 公司资质、许可证及登记资料
}

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
    ("dept_wai", "外贸合规经理", Role.DEPT_REVIEWER, "WAI", "dept123"),
    ("dept_eng", "工程采购经理", Role.DEPT_REVIEWER, "ENG", "dept123"),
    ("dept_sal", "销售经理", Role.DEPT_REVIEWER, "SAL", "dept123"),
    ("dept_fin", "财务经理", Role.DEPT_REVIEWER, "FIN", "dept123"),
    ("dept_log", "物流经理", Role.DEPT_REVIEWER, "LOG", "dept123"),
    ("dept_prd", "生产经理", Role.DEPT_REVIEWER, "PRD", "dept123"),
    ("dept_adm", "行政经理", Role.DEPT_REVIEWER, "ADM", "dept123"),
    ("dept_qal", "质量经理", Role.DEPT_REVIEWER, "QAL", "dept123"),
    # 每个部门都要有提交人：资料包责任人若只能落在部门经理身上，上传人与审核人
    # 就成了同一个人，职责分离形同虚设（代码在本部门无第二名审核人时不阻止，
    # 否则流程会死锁）。八个部门一一对应。
    ("submit_wai", "外贸专员", Role.SUBMITTER, "WAI", "user123"),
    ("submit_eng", "采购专员", Role.SUBMITTER, "ENG", "user123"),
    ("submit_sal", "销售专员", Role.SUBMITTER, "SAL", "user123"),
    ("submit_fin", "财务专员", Role.SUBMITTER, "FIN", "user123"),
    ("submit_log", "物流专员", Role.SUBMITTER, "LOG", "user123"),
    ("submit_prd", "生产专员", Role.SUBMITTER, "PRD", "user123"),
    ("submit_qal", "质量专员", Role.SUBMITTER, "QAL", "user123"),
    ("submit_adm", "行政专员", Role.SUBMITTER, "ADM", "user123"),
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
            per_order=code not in COMPANY_LEVEL,
        )
        db.add(pkg)

    # 账号（admin/coo/auditor 授权全部工厂；业务账号授权 RMA）
    # 幂等：已存在账号也同步工厂授权，避免历史库/重建时授权缺失。
    demo = settings.SEED_DEMO_DATA
    accounts = ACCOUNTS if demo else [a for a in ACCOUNTS if a[0] == "admin"]
    if demo:
        logger.warning("SEED_DEMO_DATA 已启用：将创建公开已知密码的演示账号（admin/admin123 等），生产环境请设置 SEED_DEMO_DATA=false")
    for username, name, role, dept_code, pwd in accounts:
        u = db.query(User).filter(User.username == username).first()
        if not u:
            if username == "admin" and not demo:
                pwd = generate_temp_password()
                logger.warning("首次初始化：已创建 admin 账号，初始密码仅此一次打印，请立即登录修改 —— admin / %s", pwd)
            u = User(
                id=next_id(),
                username=username,
                password_hash=hash_password(pwd),
                display_name=name,
                dept_id=dept_map[dept_code].id if dept_code else None,
                role=role.value if isinstance(role, Role) else role,
                status="active",
                # 生产初始化的 admin 初始密码打印在日志里，首次登录必须换掉；演示账号不强制
                must_change_password=(username == "admin" and not demo),
            )
            db.add(u)
            db.flush()
        want = list(factory_map.values()) if role in (Role.ADMIN, Role.COO_REVIEWER, Role.AUDITOR) else (
            [factory_map["RMA"]] if factory_map else [])
        cur = {f.id for f in u.factories}
        for f in want:
            if f.id not in cur:
                u.factories.append(f)

    # 资料包责任人 = 本部门**提交人**；只有该部门没有提交人时才回退到部门审核人。
    #
    # 原来一律指给部门审核人，两个后果：①上传人与审核人成了同一个人，职责分离
    # 形同虚设（代码在本部门无第二名审核人时不阻止，否则流程会死锁）；②资料包
    # 可见性按责任人过滤，于是提交人的「资料包」页面永远是空的，而规格 §2.4 写明
    # 提交人的核心权限就是"上传/替换本人负责资料包的文件"。
    # 顺序无关：提交人直接覆盖，审核人只用 setdefault 兜底。
    owner_by_dept = {}
    for username, _name, role, dept_code, _pwd in ACCOUNTS:
        if not dept_code:
            continue
        u = db.query(User).filter(User.username == username).first()
        if not u:
            continue
        if role == Role.SUBMITTER:
            owner_by_dept[dept_code] = u.id
        elif role == Role.DEPT_REVIEWER:
            owner_by_dept.setdefault(dept_code, u.id)
    for code, _zh, _en, _th, dept_code, _focus in PACKAGE_SEED:
        p = db.query(Package).filter(Package.code == code).first()
        if p and p.owner_user_id is None and dept_code in owner_by_dept:
            p.owner_user_id = owner_by_dept[dept_code]

    # 示例订单（每厂 1 单，供快速验收；生产不创建）
    sample = [
        ("RMA", "ORD-RMA-001", "Bintelli Motors", "高尔夫球车 RMA-X1", 120, "2026-10-15"),
        ("WEV", "ORD-WEV-001", "Toyha East", "城市电动小车 WEV-C2", 40, "2026-11-01"),
    ] if demo else []
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
