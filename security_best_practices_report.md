# COO 资料收集平台 · 后端安全与越权审查报告

- 审查范围：`backend/app/api/*`（auth/audit/controlled/dashboard/factories/nas/notifications/orders/org/packages/todo）
- 权限核心：`backend/app/core/rbac.py`、`backend/app/core/security.py`
- 配套审查：`backend/app/core/{config,storage,audit,security_headers}.py`、`backend/app/services/{nas_sync,notify,s3}.py`、`backend/app/models.py`、`backend/app/schemas.py`、`backend/requirements.txt`、`backend/Dockerfile`、`docker-compose.yml`、`frontend/nginx.conf`
- 日期：2026-08-21

## 执行摘要

整体框架较好：所有业务端点均通过 `get_current_user` / `require_roles` 依赖鉴权；数据库访问全部走 SQLAlchemy ORM（未发现原始 SQL 拼接 / 命令注入 / 不安全反序列化）；密码使用 bcrypt(12) 存储，JWT 校验强制算法白名单并校验 `exp`，角色校验基于 DB 实时读取而非信任 token 内 role 声明，这些基础防护扎实。

但存在若干**越权 / 信息泄露 / 文件路径**问题，其中 3 处高危（受控区 ZIP 下载越权、NAS 本地归档路径穿越、默认口令与默认 JWT 密钥），建议优先修复。

严重级：严重 > 高 > 中 > 低。

---

## 严重级：严重 / 高

### S-01（高）默认账号 + 无条件的种子数据导致默认弱口令账号必然存在
- 位置：`backend/app/services/seed.py:68-83`、`backend/app/main.py:44-45`
- 描述：`main.py` 启动时无条件调用 `seed(db)`，seed 中硬编码创建了 `admin/admin123`、`coo/coo123`、`dept_wai/dept123`、`submit_eng/user123`、`auditor/audit123` 等 14 个已知口令账号，且幂等（已存在也补授权），不会自动清理。任何部署（含生产）若未手工删除这些账号，攻击者可直接用公开弱口令登录，获取 `admin`（全权限）或 `coo`（终审）角色。
- 影响：默认口令登录即完全接管系统。
- 修复：种子仅限本地/测试环境（用环境变量如 `SEED_DEMO_DATA=false` 开关），生产禁用；或首启强制改密。

### S-02（高）JWT 签名密钥为公开默认值（可伪造任意用户 token）
- 位置：`backend/app/core/config.py:20`（默认 `change-me-in-production-please-use-a-long-random-string`）、`docker-compose.yml:50`（硬编码 `change-me-in-production`）
- 描述：HS256 签名密钥若未通过环境变量覆盖，即使用公开已知字符串。攻击者可自行签发任意 `sub` 的 token（rbac.py:22 直接用 `sub` 查用户），实现任意账号冒充与角色越权。
- 影响：密钥泄露即全量账户接管 / 权限提升。
- 修复：生产强制通过环境变量注入随机强密钥；`docker-compose.yml` 移除默认值，改为必填/随机生成；应用启动时可校验 `SECRET_KEY` 不等于默认值并拒绝启动。

### S-03（高）受控区 ZIP 下载越权（IDOR/鉴权绕过）
- 位置：`backend/app/api/controlled.py:60-63, 69`
- 描述：`GET /controlled/{pkg_id}/versions/{vid}/export/zip` 使用 `Depends(get_current_user)` 而非列表页使用的 `controlled_access`（controlled.py:22，仅 dept_reviewer/coo_reviewer/admin）。且 `_visible_pkg_ids`（controlled.py:25-30）仅对 `dept_reviewer` 按部门过滤，对 `submitter`/`auditor` 等角色返回**全部**资料包 id。于是任何登录用户（含提交人）只需遍历 pkg_id/vid 即可下载任意资料包已放行的全部真实附件。
- 影响：提交人可下载全组织 COO 合规资料（财务/合同/资质等敏感文件）。
- 修复：改为 `Depends(controlled_access)`；`_visible_pkg_ids` 对所有非 COO/管理员角色严格过滤。

### S-04（高）NAS 本地归档路径穿越（任意文件写入）
- 位置：`backend/app/services/nas_sync.py:74-78`（`version_target`/`order_target`）、`42-48`（`_order_parts` 含 order_no）；上传扩展名校验 `packages.py:207-210`、`orders.py:354-357`、白名单 `constants.py:74-78`
- 描述：NAS 本地回退模式（S3 未配置，即默认开发/回退配置）下，同步目标路径用 `os.path.join(base, att.original_name)`，`original_name` 是用户上传原始文件名（仅校验扩展名，`..\\..\\evil.txt` 等可绕过）。同步时将 `shutil.copy2(src, target)` 写入该路径，可用 `../`/`..\\` 逃逸 `NAS_ROOT` 目录，实现任意路径文件写入（文件内容=上传内容，攻击者可控）。
- 影响：在本地回退部署下可越界写文件，若可写至启动脚本/cron 等位置，可升级为 RCE。
- 修复：写入路径前对 `original_name`/`order_no` 做白名单清洗（如 `re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]", "_", ...)`），并校验最终路径 `os.path.realpath` 必须位于 `NAS_ROOT` 之下。

---

## 严重级：中

### M-01（中）CSV 导出存在公式注入（CSV Injection）
- 位置：`orders.py:426-439`（`_q` 仅转义双引号）、`dashboard.py:99-110`（连双引号都未转义）、`audit.py:48-62`、`controlled.py:74-84`
- 描述：订单号、资料包名、审计 detail/target、附件原名等用户可控字段拼入 CSV，未对以 `= + - @` 开头的单元格做前缀防护。用户（如提交人）创建含 `=HYPERLINK(...)`、`=cmd|...` 的订单号/文件名后，管理员/审计员导出 Excel 打开即触发公式执行。
- 影响：对导出者的主机执行 / 数据外带。
- 修复：导出前对单元格值做公式前缀转义（前缀 `'` 或禁用公式），并统一封装转义函数。

### M-02（中）看板向提交人泄露全组织数据（可见性隔离不一致）
- 位置：`backend/app/api/dashboard.py:15-88`
- 描述：`GET /dashboard` 对所有登录用户（含 submitter）返回**全部**资料包的 `package_progress`（状态/附件数）、`need_attention`（含 `dept_reject_reason`/`coo_reject_reason`）、全局完成率与附件总数，未复用 `packages.py:32-39` 的 `_visible_packages` 可见性逻辑。
- 影响：提交人可窥探其它部门/责任人的资料包进度与内部退回意见（跨部门信息泄露）。
- 修复：看板统计按角色过滤可见范围（与 `can_view_package` 对齐），或对非 COO/管理员仅返回"待我处理"部分。

### M-03（中）NAS 状态/同步记录对任意登录用户开放（内部信息泄露）
- 位置：`backend/app/api/nas.py:15-25, 36-38`
- 描述：`/nas/status`、`/nas/records` 使用 `Depends(get_current_user)`（任意登录用户），返回 `nas_root`（内部存储路径或 `s3://coo-nas@endpoint`）、待同步数量、`SyncRecordOut.details`（含同步失败原因、可能的内部错误串）。而触发同步 `/nas/sync` 已正确限 `coo_or_admin`。
- 影响：提交人可获取基础设施内部路径与后端运行细节。
- 修复：三个端点统一收敛到 `coo_or_admin`（或 `require_roles("coo_reviewer","auditor","admin")`）。

### M-04（中）登录缺少 IP 级限流 + 按用户锁定可被利用为账号 DoS + 用户名枚举
- 位置：`backend/app/api/auth.py:19-38`
- 描述：登录无任何 IP 限流/验证码；失败 5 次按**用户名**锁定 30 分钟（`auth.py:31-34`），攻击者可对他人账号连续 5 次错误输入制造锁定（DoS）；`423 "账号已锁定"` 响应与"锁定期间不累计"逻辑可确认账号存在；对不存在的用户不执行 bcrypt，存在时序侧信道可枚举用户名。
- 影响：账号可用性攻击 + 用户名枚举（为后续撞库/社工铺路）。
- 修复：增加 IP 级限流（配合锁用户）；锁定时返回与"密码错误"一致（或延迟）；对不存在的用户也执行一次 bcrypt 消耗以消除时序差。

### M-05（中）重置密码为固定弱口令并在响应中明文返回
- 位置：`backend/app/api/org.py:103-112`
- 描述：管理员重置密码直接 `hash_password("user123")`，且响应明文返回"密码已重置为 user123"。该弱口令同时是 seed 默认口令，若用户未再修改即被接管。
- 修复：生成随机强密码（`secrets.token_urlsafe`），仅一次性返回给管理员，并提示用户首登改密。

### M-06（中）上传仅校验扩展名，未做内容/大小一致性校验，文件名无长度限制
- 位置：`packages.py:207-221`、`orders.py:353-367`、`constants.py:74-78`
- 描述：仅按扩展名白名单放行，未校验文件魔数/MIME 与内容一致性（可上传伪装扩展的 HTML/脚本/宏文档，或任意内容文件）；`f.filename` 无长度与字符限制（>255 字符写入 `original_name` 会触发 DB DataError → 500；含 CRLF/`..` 亦未限制）。
- 影响：存储"伪装文件"（低，因下载默认 attachment）、异常文件名导致 500、与 M-01/S-04 形成组合利用面。
- 修复：服务端校验内容签名（至少校验常见类型魔数）、限制 `original_name` 长度（≤255）并清洗控制字符。

### M-07（中）依赖版本存在已知漏洞（multipart/FileResponse）
- 位置：`backend/requirements.txt:1`（fastapi==0.115.0 → starlette 0.38.x）
- 描述：Starlette 0.38.x 受 CVE-2024-47874（multipart/form-data DoS）影响；FileResponse 的 Range 头 DoS（CVE-2025-62727，修复于 0.49.1）亦未覆盖。本项目大量使用 multipart 上传与 `FileResponse` 下载。
- 影响：内存/CPU 型 DoS。
- 修复：升级 fastapi/starlette 至已修复版本并回归上传/下载。

### M-08（中）OpenAPI 文档在生产默认开放
- 位置：`backend/app/main.py:16-17`
- 描述：`FastAPI(...)` 未设置 `docs_url/redoc_url/openapi_url=None`，`/docs`、`/redoc`、`/openapi.json` 对公网开放，完整暴露全部端点结构、参数与安全方案。
- 影响：信息泄露，辅助攻击者枚举攻击面。
- 修复：生产按 `DEBUG` 条件关闭 docs 或加鉴权。

### M-09（中）订单 ZIP 归档条目标使用未清洗的 order_no（zip-slip 面）
- 位置：`backend/app/api/orders.py:469`（`arc = f"{fac_code}/{o.order_no}/{safe_code}/{safe_name}"`）
- 描述：归档目录名 `fac_code` 与 `o.order_no` 直接拼接进 zip 条目标，未清洗（`safe_no` 仅用于下载文件名 orders.py:478）。order_no 由用户创建订单时控制，可含 `../`，解压时条目标将越界写入提取目录之外（经典 zip-slip）。
- 影响：导出包被受害者解压时在本地越界写文件。
- 修复：对 `fac_code`/`o.order_no` 复用 `safe_*` 清洗后再入 zip。

---

## 严重级：低

### L-01（低）导出 CSV 的 Content-Disposition 文件名直接拼接 order_no
- 位置：`orders.py:439`（`filename=order_{o.order_no}.csv`）
- 描述：order_no 用户可控，未转义即拼入响应头；若含 `"`/CRLF 可能造成响应头注入或畸形头。
- 修复：使用清洗后的 `safe_no` 并加引号。

### L-02（低）审计 IP 直接信任 X-Forwarded-For
- 位置：`backend/app/core/audit.py:8-14`
- 描述：`client_ip` 直接取 `X-Forwarded-For` 首段，若后端非仅经受信代理暴露，攻击者可伪造审计 IP。
- 修复：仅信任受信代理（同 FASTAPI-PROXY-001），或在边缘校验。

### L-03（低）get_current_user 对非数字 sub 未捕获异常
- 位置：`backend/app/core/rbac.py:22`
- 描述：`int(payload["sub"])` 若为非法整数会抛 ValueError → 500（仅在签名密钥泄露、能构造 token 时才可达，但属于健壮性/信息面问题）。
- 修复：捕获异常统一返回 401。

### L-04（低）部分审计事件 IP 传 None 导致记录为空
- 位置：`audit.py:57`、`dashboard.py:108`（`log_event(..., ip=client_ip(None))`）
- 描述：导出类操作的审计记录 IP 恒为空，审计完整性受损。
- 修复：传入 request 获取真实 IP。

### L-05（低）订单归属/责任人可被提交人任意指定
- 位置：`orders.py:130`（OrderUpdate.owner_user_id）、`orders.py:190`（OrderInstanceCreate.owner_user_id）
- 描述：提交人创建/编辑订单、实例化资料包时可把 `owner_user_id` 设为任意用户 id，可将工作与通知定向到任意账号（骚扰/责任甩锅），且 `add_order_package` 未校验目标资料包模板的可见性（orders.py:180-183）。
- 修复：owner_user_id 仅允许 COO/管理员指定，或校验目标用户与资料包可见性。

### L-06（低）审计列表/导出角色不一致
- 位置：`audit.py:16-24`（`audit_viewer`=auditor/admin）vs `audit.py:38-43`（`coo_or_admin`）
- 描述：COO 可通过 `/audit/export` 导出全部审计日志但无法通过 `/audit/logs` 列表查看，行为不一致（非漏洞，属策略缺口）。
- 修复：统一角色口径。

### L-07（低）health 端点与应用信息
- 位置：`main.py:35-37`
- 描述：`/health` 返回应用名（轻微信息泄露）。
- 修复：可省略 app 名称或置于内网。

---

## 未发现问题项（确认合规）

- SQL 注入：全部使用 SQLAlchemy ORM 参数化查询，未发现字符串拼接/原生 SQL（已全局检索 `execute(`/`text(`）。
- 命令注入 / 不安全反序列化：无 `subprocess`/`os.system`/`shell=True`/`eval`/`pickle` 等。
- 密码存储：bcrypt(12) 哈希，`UserOut`/各响应模型均不含 `password_hash`（schemas.py:76-88 已剔除）。
- JWT：`decode` 强制 `algorithms=[HS256]` 白名单并校验 `exp`；鉴权基于 DB 用户而非 token 内 role 声明，避免 role 篡改。
- 附件下载路径：下载使用服务端生成的 sha256 存储名拼接 `UPLOAD_DIR`（非用户输入），无路径穿越；下载/预览默认 attachment，`filename` 由 Starlette 引号化。
- CORS：显式来源白名单 + credentials，未见 `*`。
- 安全响应头：后端 `SecurityHeadersMiddleware`（security_headers.py）与 nginx 均设置了 nosniff/X-Frame-Options 等。
- 常规端点对象级鉴权：packages/orders 详情的可见性（`can_view_package`/工厂隔离）与版本/附件 ID 绑定校验（`att.version_id != vid or v.package_id != pkg_id`）到位。
