import {
  del, downloadBlob, get, patch, post, upload,
} from './client'
import type {
  AuditLog, ControlledItem, Dashboard, Department, NasStatus, Package, PackageDetailResp, PackageRow,
  SyncRecord, User, Version,
} from '@/types'

// ---------- 认证 ----------
export const auth = {
  login: (username: string, password: string) =>
    post<{ access_token: string; user: User }>('/auth/login', { username, password }),
  me: () => get<User>('/auth/me'),
  changePassword: (old_password: string, new_password: string) =>
    post('/auth/change-password', { old_password, new_password }),
  logout: () => post('/auth/logout'),
}

// ---------- 组织 ----------
export const org = {
  listDepartments: () => get<Department[]>('/org/departments'),
  createDepartment: (data: { code: string; name_zh: string; name_en?: string; name_th?: string }) =>
    post<Department>('/org/departments', data),
  listUsers: (dept_id?: string) => get<User[]>('/org/users', dept_id ? { dept_id } : undefined),
  createUser: (data: { username: string; password: string; display_name?: string; email?: string; phone?: string; dept_id?: string | null; role?: string }) =>
    post<User>('/org/users', data),
  resetPassword: (id: string) => post(`/org/users/${id}/reset-password`),
}

// ---------- 资料包 / 版本 / 附件 ----------
export const packages = {
  list: () => get<PackageRow[]>('/packages'),
  detail: (id: string) => get<PackageDetailResp>(`/packages/${id}`),
  create: (data: Partial<Package>) => post<Package>('/packages', data),
  update: (id: string, data: Partial<Package>) => patch<Package>(`/packages/${id}`, data),
  createVersion: (id: string, change_note: string, project_code?: string) =>
    post<Version>(`/packages/${id}/versions`, { change_note, project_code: project_code || '' }),
  submit: (pkgId: string, vid: string) => post<Version>(`/packages/${pkgId}/versions/${vid}/submit`),
  review: (pkgId: string, vid: string, decision: string, level: string, reason: string) =>
    post<Version>(`/packages/${pkgId}/versions/${vid}/review`, { decision, level, reason }),
  deleteVersion: (pkgId: string, vid: string) => del(`/packages/${pkgId}/versions/${vid}`),
  uploadAttachments: (pkgId: string, vid: string, files: File[], order_no: string, batch_no: string) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    form.append('order_no', order_no)
    form.append('batch_no', batch_no)
    return upload<Version['attachments']>(`/packages/${pkgId}/versions/${vid}/attachments`, form)
  },
  deleteAttachment: (pkgId: string, vid: string, aid: string) =>
    del(`/packages/${pkgId}/versions/${vid}/attachments/${aid}`),
  attachmentUrl: (pkgId: string, vid: string, aid: string, preview = false) =>
    `/api/packages/${pkgId}/versions/${vid}/attachments/${aid}/file${preview ? '?preview=true' : ''}`,
}

// ---------- 看板 / 受控区 / 审计 / NAS ----------
export const dashboard = {
  get: () => get<Dashboard>('/dashboard'),
}

export const controlled = {
  list: () => get<ControlledItem[]>('/controlled'),
}

export const audit = {
  list: (params?: { domain?: string; actor_id?: string }) => get<AuditLog[]>('/audit/logs', params),
  exportCsv: () => downloadBlob('/audit/export'),
}

export const nas = {
  status: () => get<NasStatus>('/nas/status'),
  sync: () => post<SyncRecord>('/nas/sync'),
  records: () => get<SyncRecord[]>('/nas/records'),
}
