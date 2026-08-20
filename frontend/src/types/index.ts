export interface User {
  id: string
  username: string
  display_name: string
  email: string
  phone: string
  dept_id: string | null
  role: string
  status: string
  last_login_at: string | null
  created_at: string | null
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
  package_progress: { code: string; name: string; status: string; percent: number; attachments: number }[]
  need_attention: { code: string; name: string; issue: string; reason: string }[]
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
  package_code: string
  package_name: string
  version: Version
  attachment_count: number
  locked: boolean
}

export type Lang = 'zh' | 'en' | 'th'

export const ROLES = ['submitter', 'dept_reviewer', 'coo_reviewer', 'auditor', 'admin'] as const
export type Role = (typeof ROLES)[number]
