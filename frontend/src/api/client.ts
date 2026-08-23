import axios, { type AxiosRequestConfig, type AxiosError } from 'axios'
import { tOutside } from '@/i18n/messages'

const TOKEN_KEY = 'coo_token'

export const getToken = (): string | null => localStorage.getItem(TOKEN_KEY)
export const setToken = (t: string) => localStorage.setItem(TOKEN_KEY, t)
export const clearToken = () => localStorage.removeItem(TOKEN_KEY)

const client = axios.create({ baseURL: '/api', timeout: 30000 })

client.interceptors.request.use((config) => {
  const t = getToken()
  if (t) config.headers.Authorization = `Bearer ${t}`
  return config
})

client.interceptors.response.use(
  (r) => r,
  (err: AxiosError<{ detail?: unknown }>) => {
    // 401 = 凭证失效（过期 / 密钥轮换 / 账号被停用）：清除本地令牌并回登录页。
    // 403 一般是权限不足（应停留在原页面显示错误），但后端若以 403 表达"账号已停用"，
    // 同样属于会话失效，此处一并兜底，避免用户卡在数据全空却无提示的界面里。
    const st = err.response?.status
    const detail = err.response?.data?.detail
    const sessionGone = st === 401 || (st === 403 && typeof detail === 'string' && detail.includes('停用'))
    if (sessionGone) {
      clearToken()
      if (location.pathname !== '/login') {
        // 带上原因跳转：这里是整页跳转，toast 会随页面一起消失，
        // 用户只会看到自己"莫名其妙被踢回登录页、填了一半的内容也没了"。
        // 通知轮询每 30s 一次，所以即便用户只是在填表没点任何按钮，
        // 令牌一过期也会被后台请求触发登出 —— 更需要说清原因。
        const reason = typeof detail === 'string' && detail.includes('停用') ? 'disabled' : 'expired'
        location.href = `/login?reason=${reason}`
      }
    }
    return Promise.reject(err)
  },
)

export function errMessage(err: unknown): string {
  const e = err as AxiosError<{ detail?: unknown }>
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail) return JSON.stringify(detail)
  return e?.message || tOutside('request_failed')
}

export async function get<T>(url: string, params?: unknown): Promise<T> {
  const r = await client.get<T>(url, { params })
  return r.data
}

export async function post<T>(url: string, data?: unknown, params?: unknown): Promise<T> {
  const r = await client.post<T>(url, data, { params })
  return r.data
}

export async function patch<T>(url: string, data?: unknown): Promise<T> {
  const r = await client.patch<T>(url, data)
  return r.data
}

export async function del<T>(url: string): Promise<T> {
  const r = await client.delete<T>(url)
  return r.data
}

export async function upload<T>(url: string, form: FormData): Promise<T> {
  const r = await client.post<T>(url, form, { headers: { 'Content-Type': 'multipart/form-data' } })
  return r.data
}

export async function downloadBlob(url: string): Promise<Blob> {
  const r = await client.get(url, { responseType: 'blob' })
  return r.data
}

/** 附件下载：原生 fetch 携带 token，url 需为完整 /api/... 路径（浏览器导航无法带 Bearer 头）。 */
export async function downloadFile(url: string, filename: string): Promise<void> {
  const res = await fetch(url, { headers: { Authorization: `Bearer ${getToken()}` } })
  if (!res.ok) throw new Error(`${tOutside('download_failed')}（HTTP ${res.status}）`)
  const blob = await res.blob()
  const u = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = u
  a.download = filename
  a.click()
  URL.revokeObjectURL(u)
}

export type { AxiosRequestConfig }
