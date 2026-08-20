# COO 资料收集平台

面向新能源车企（如 Bintelli）出口合规的 COO（Certificate of Origin）资料收集与核查平台。
覆盖 12 个资料包（COO-01 ~ COO-13）的资料收集、版本管理、两级审核（部门 → COO 终审）、
受控区归档、NAS 同步与全量审计。

## 技术栈
- 后端：FastAPI + SQLAlchemy + MySQL 8.0（开发可切 SQLite）
- 前端：React + TypeScript + Vite
- 归档：云端主存 → 工厂本地 NAS（经加密隧道挂载，开发以本地目录模拟）
- 部署：Docker Compose（MySQL + Backend + Nginx 前端）

## 目录
```
backend/      FastAPI 应用（app/）
frontend/     React 前端
docs/         需求与方案资料
docker-compose.yml
```

## 快速开始（本地开发）
### 后端
```bash
cd backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # 默认使用 SQLite，开箱即用
python -m uvicorn app.main:app --reload --port 8000
```
- API 文档：http://localhost:8000/docs
- 首次启动自动建表并写入种子数据（部门 / 12 资料包 / 角色账号）。

### 前端
```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

### 演示账号
| 角色 | 用户名 | 密码 |
| --- | --- | --- |
| 系统管理员 | admin | admin123 |
| COO 终审人 | coo | coo123 |
| 部门审核人（工程） | dept_eng | dept123 |
| 部门审核人（财务） | dept_fin | dept123 |
| 提交人（采购） | submit_eng | user123 |
| 提交人（财务） | submit_fin | user123 |
| 提交人（物流） | submit_log | user123 |
| 审计查看人 | auditor | audit123 |

## 核心流程
1. 提交人上传资料包附件（支持订单号/批次号标注），提交进入「待部门审核」。
2. 部门审核人（仅限责任部门）审核：通过 →「待 COO 终审」；退回 → 提交人整改后重新提交。
3. COO 终审人终审：通过 →「已放行」并锁定（仅可发起新版本）；退回 → 重新提交。
4. 已放行版本进入「受控区」，供核查调阅；附件经隧道同步至 NAS 并写 manifest。
5. 全部登录 / 上传 / 替换 / 审核 / 退回 / 放行 / 下载 / 导出均记入审计日志。

## 生产部署
```bash
docker compose up -d --build
```
- NAS 挂载点：将加密隧道客户端挂载目录映射到宿主机 `./nas_mount`，容器映射到 `/app/data/nas`。
- 务必修改 `SECRET_KEY` 与各账号默认密码。

## 功能映射（需求规格 F-01 ~ F-11）
- F-01 登录与权限：5 角色、密码错误锁定、会话超时
- F-02 用户与部门管理
- F-03 工作概览看板
- F-04 资料包配置（12 个）
- F-05 附件上传（格式/大小校验、订单/批次标注、预览）
- F-06 NAS 归档同步（每日定时 + 手动，状态可查）
- F-07 版本管理（V1.0 / V1.1 …，变更重走流程）
- F-08 两级审核（部门 / COO，任一节点可退回）
- F-09 受控区（仅放行版本只读）
- F-10 操作日志与 CSV 导出
- F-11 中 / 英 / 泰 三语界面
