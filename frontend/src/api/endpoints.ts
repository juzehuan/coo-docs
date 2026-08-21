import {
  del, downloadBlob, get, patch, post, upload,
} from './client'
import type {
  Attachment, AuditLog, ControlledItem, Dashboard, Department, Factory, NasStatus, NotificationItem,
  NotificationList, Order, OrderAttachment,
  OrderDetail, OrderPackage, Package, PackageDetailResp, PackageRow, PasswordResetOut, SyncRecord, TodoItem, User, Version,
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

// ---------- 工厂 ----------
export const factories = {
  list: () => get<Factory[]>('/factories'),
  create: (data: Partial<Factory>) => post<Factory>('/factories', data),
}

// ---------- 订单 ----------
export const orders = {
  list: () => get<Order[]>('/orders'),
  detail: (id: string) => get<OrderDetail>(`/orders/${id}`),
  create: (data: Partial<Order>) => post<Order>('/orders', data),
  update: (id: string, data: Partial<Order>) => patch<Order>(`/orders/${id}`, data),
  remove: (id: string) => del(`/orders/${id}`),
  addPackage: (id: string, data: { package_id: string; owner_user_id?: string | null; required?: boolean; due_date?: string }) =>
    post<OrderPackage>(`/orders/${id}/packages`, data),
  removePackage: (id: string, opId: string) => del(`/orders/${id}/packages/${opId}`),
  submit: (id: string, opId: string) => post<OrderPackage>(`/orders/${id}/packages/${opId}/submit`),
  withdraw: (id: string, opId: string) => post<OrderPackage>(`/orders/${id}/packages/${opId}/withdraw`),
  review: (id: string, opId: string, decision: string, level: string, reason: string) =>
    post<OrderPackage>(`/orders/${id}/packages/${opId}/review`, { decision, level, reason }),
  uploadAttachments: (id: string, opId: string, files: File[], batch_no: string) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    form.append('batch_no', batch_no)
    return upload<OrderAttachment[]>(`/orders/${id}/packages/${opId}/attachments`, form)
  },
  deleteAttachment: (id: string, opId: string, aid: string) =>
    del(`/orders/${id}/packages/${opId}/attachments/${aid}`),
  attachmentUrl: (id: string, opId: string, aid: string, preview = false) =>
    `/api/orders/${id}/packages/${opId}/attachments/${aid}/file${preview ? '?preview=true' : ''}`,
  // 导出通过 axios 携带 Bearer token 下载，避免 window.location.href 无法带认证头而 401
  exportCsv: (id: string, orderNo: string) =>
    downloadBlob(`/orders/${id}/export`).then((blob) => {
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `order_${orderNo}.csv`
      a.click()
      URL.revokeObjectURL(url)
    }),
  exportZip: (id: string, orderNo: string) =>
    downloadBlob(`/orders/${id}/export/zip`).then((blob) => {
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `order_${orderNo}_archive.zip`
      a.click()
      URL.revokeObjectURL(url)
    }),
}

// ---------- 组织 ----------
export const org = {
  listDepartments: () => get<Department[]>('/org/departments'),
  createDepartment: (data: { code: string; name_zh: string; name_en?: string; name_th?: string }) =>
    post<Department>('/org/departments', data),
  listUsers: (dept_id?: string) => get<User[]>('/org/users', dept_id ? { dept_id } : undefined),
  createUser: (data: { username: string; password: string; display_name?: string; email?: string; phone?: string; dept_id?: string | null; role?: string; factory_ids?: number[] }) =>
    post<User>('/org/users', data),
  resetPassword: (id: string) => post<PasswordResetOut>(`/org/users/${id}/reset-password`),
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
  withdraw: (pkgId: string, vid: string) => post<Version>(`/packages/${pkgId}/versions/${vid}/withdraw`),
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

// ---------- 待办队列 ----------
export const todo = {
  list: () => get<TodoItem[]>('/todo'),
}

// ---------- 通知中心 ----------
export const notifications = {
  list: (limit?: number) => get<NotificationList>('/notifications', limit ? { limit } : undefined),
  unreadCount: () => get<{ count: number }>('/notifications/unread-count'),
  markRead: (id: string) => post(`/notifications/${id}/read`),
  markAllRead: () => post('/notifications/read-all'),
}

export const controlled = {
  list: () => get<ControlledItem[]>('/controlled'),
  exportZip: (pkgId: string, vid: string, filename: string) =>
    downloadBlob(`/controlled/${pkgId}/versions/${vid}/export/zip`).then((blob) => {
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    }),
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
