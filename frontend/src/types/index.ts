export interface User {
  id: string
  username: string
  display_name: string
  email: string
  phone: string
  dept_id: string | null
  role: string
  status: string
  factory_ids: string[]
  last_login_at: string | null
  created_at: string | null
}

export interface PasswordResetOut {
  msg: string
  password: string
}

export interface AuditQuery {
  domain?: string
  actor_id?: string
  actor?: string
  target?: string
  start?: string
  end?: string
}

export interface AuditLogList {
  total: number
  items: AuditLog[]
}

export interface NasConfig {
  mode: 's3' | 'local'
  endpoint_url: string
  access_key: string
  /** 读取时为掩码；提交时留空表示保持不变 */
  secret_key: string
  bucket: string
  region: string
  use_ssl: boolean
  local_root: string
  sync_time: string
  auto_sync: boolean
}

export interface Factory {
  id: string
  code: string
  name_zh: string
  name_en: string
  name_th: string
  status: string
  sort_order: number
  created_at: string | null
}

export interface OrderAttachment {
  id: string
  original_name: string
  file_name: string
  md5: string
  batch_no: string
  uploaded_at: string | null
}

export interface OrderPackage {
  id: string
  order_id: string
  package_id: string
  project_code: string
  status: string
  owner_user_id: string | null
  required: boolean
  due_date: string
  locked: boolean
  created_at: string | null
  package_code: string
  package_name: string
  package_dept_id: string | null
  /** 是否可进行部门审核（含职责分离判定，由后端下发） */
  reviewable_dept?: boolean
  attachment_count: number
  attachments?: OrderAttachment[]
}

export interface Order {
  id: string
  factory_id: string
  factory_code: string
  factory_name: string
  order_no: string
  customer: string
  product: string
  quantity: number
  export_date: string
  status: string
  note: string
  owner_user_id: string | null
  created_at: string | null
  package_count: number
  released_count: number
  completion: number
}

export interface OrderDetail extends Order {
  packages: OrderPackage[]
}

export interface Department {
  id: string
  code: string
  name_zh: string
  name_en: string
  name_th: string
  created_at: string | null
}

export interface Attachment {
  id: string
  version_id: string
  file_name: string
  original_name: string
  file_size: number
  md5: string
  mime_type: string
  order_no: string
  batch_no: string
  uploaded_by: string | null
  uploaded_at: string | null
  nas_synced: boolean
  nas_synced_at: string | null
}

export interface Version {
  id: string
  package_id: string
  project_code: string
  version_no: string
  status: string
  change_note: string
  locked: boolean
  submitted_by: string | null
  submitted_at: string | null
  dept_reviewer_id: string | null
  dept_reviewed_at: string | null
  dept_reject_reason: string
  coo_reviewer_id: string | null
  coo_reviewed_at: string | null
  coo_reject_reason: string
  created_at: string | null
  attachments: Attachment[]
}

export interface Package {
  id: string
  code: string
  name_zh: string
  name_en: string
  name_th: string
  dept_id: string | null
  owner_user_id: string | null
  review_focus: string
  due_date: string
  required: boolean
  status: string
  sort_order: number
  created_at: string | null
}

export interface PackageRow extends Package {
  current_status: string
  current_version: string
  attachment_count: number
  editable: boolean
  reviewable_dept: boolean
  reviewable_coo: boolean
}

export interface PackageDetailResp extends Package {
  versions: Version[]
}

export interface Dashboard {
  package_completion: number
  total_attachments: number
  pending_mine: number
  released: number
  overdue: number
  package_progress: { code: string; name: string; status: string; percent: number; attachments: number; overdue?: boolean }[]
  need_attention: { code: string; name: string; issue_code: string; due_date?: string; reason: string; overdue?: boolean }[]
}

export interface AuditLog {
  id: string
  event_domain: string
  action: string
  actor_id: string | null
  actor_role: string
  actor_name: string
  ip: string
  target: string
  detail: string
  created_at: string | null
}

export interface SyncRecord {
  id: string
  run_type: string
  triggered_by: string | null
  total: number
  success: number
  failed: number
  status: string
  details: { tunnel_ok?: boolean; failures?: any[] } | null
  started_at: string | null
  finished_at: string | null
}

export interface NasStatus {
  nas_root: string
  nas_reachable: boolean
  last_sync: SyncRecord | null
  pending_count: number
}

export interface ControlledItem {
  /** version=资料包版本线；order=订单资料包实例线（两条线都属受控内容） */
  kind: 'version' | 'order'
  key: string
  package_code: string
  package_name: string
  /** 版本号或订单号 */
  subject: string
  attachment_count: number
  locked: boolean
  released_at: string | null
  ids: { pkg_id?: string; version_id?: string; order_id?: string; op_id?: string }
  attachments: Attachment[]
}

export interface OrderList {
  total: number
  items: Order[]
}

export interface ControlledList {
  total: number
  items: ControlledItem[]
}

export interface TodoItem {
  kind: 'package' | 'order'
  package_id: string
  package_code: string
  package_name: string
  order_id: string | null
  version_id: string | null
  version_no: string
  status: string
  dept_name: string
  owner_name: string
  submitter_name: string
  submitted_at: string | null
  reject_reason: string
  attachments: number
  review_focus: string
  due_date: string
  overdue?: boolean
  /** 责任部门无在岗审核人：该条已落入部门审核人视野之外，由 COO/管理员兜底 */
  no_reviewer?: boolean
}

export interface NotificationItem {
  id: string
  /** 中文成品串；仅在没有 params 的历史记录上使用 */
  title: string
  body: string
  type: string
  link: string
  /** 结构化参数 JSON：{subject, name_zh, name_en, name_th}；有它就按收件人语言渲染 */
  params?: string
  is_read: boolean
  created_at: string | null
}

export interface NotificationList {
  total: number
  unread: number
  items: NotificationItem[]
}

export type Lang = 'zh' | 'en' | 'th'

export const ROLES = ['submitter', 'dept_reviewer', 'coo_reviewer', 'auditor', 'admin'] as const
export type Role = (typeof ROLES)[number]

export interface ExportJob {
  id: string
  kind: string
  status: 'pending' | 'running' | 'done' | 'failed'
  file_name: string
  file_size: number
  error: string
  created_at: string
  finished_at: string | null
}
