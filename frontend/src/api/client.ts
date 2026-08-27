import axios, { type AxiosRequestConfig, type AxiosError } from 'axios'
import { tOutside } from '@/i18n/messages'

/** 令牌在 localStorage 中的键名。导出供跨标签页的 storage 事件比对，
 *  两处各写一份字面量迟早会改一处漏一处。 */
export const TOKEN_KEY = 'coo_token'

export const getToken = (): string | null => localStorage.getItem(TOKEN_KEY)
export const setToken = (t: string) => localStorage.setItem(TOKEN_KEY, t)
export const clearToken = () => localStorage.removeItem(TOKEN_KEY)

const client = axios.create({ baseURL: '/api', timeout: 30000 })

client.interceptors.request.use((config) => {
  const t = getToken()
  if (t) config.headers.Authorization = `Bearer ${t}`
  // 界面语言随请求带给后端：资料包名/部门名/工厂名是后端扁平化后下发的，
  // 后端不知道语言就只能一律给中文，英文与泰文界面下的清单会全是中文。
  config.headers['X-Lang'] = localStorage.getItem('coo_lang') || 'zh'
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

/** FastAPI 422 的结构化校验错误（数组形式）。 */
interface ValidationItem {
  type?: string
  loc?: (string | number)[]
  msg?: string
  ctx?: Record<string, unknown>
}

/** 把 Pydantic 校验错误转成可读中文。
 *
 * 直接 JSON.stringify 会把整条结构（含 type/loc/ctx）糊到用户脸上，
 * 中文用户根本看不懂；更糟的是其中的 `input` 字段会**回显用户的原始输入**，
 * 密码这类敏感值会直接显示在错误提示里。
 */
function formatValidation(items: ValidationItem[]): string {
  const first = items[0]
  if (!first) return tOutside('request_failed')
  const rawField = (first.loc || []).filter((x) => x !== 'body' && x !== 'query' && x !== 'path').join('.')
  // 字段名尽量用界面上的标签（order_no → 订单号）；没有对应词条时才退回原始键名。
  // 第 98 轮浏览器实测，此前提示是 "order_no: 至少需要 1 个字符"、
  // "username: String should match pattern '^\S+$'" —— 键名与 pydantic 原文直接给了用户
  const field = rawField && tOutside(rawField) !== rawField ? tOutside(rawField) : rawField
  const ctx = first.ctx || {}
  const t = first.type || ''
  let what: string
  if (t.includes('too_short')) {
    // 后端对必填文本用 min_length=1（去空白后非空）：对用户而言就是"必填"，而不是"至少 1 个字符"
    what = Number(ctx.min_length) <= 1 ? tOutside('v_required') : tOutside('v_too_short').replace('{n}', String(ctx.min_length ?? ''))
  } else if (t.includes('too_long')) what = tOutside('v_too_long').replace('{n}', String(ctx.max_length ?? ''))
  else if (t.includes('greater_than')) what = tOutside('v_min').replace('{n}', String(ctx.ge ?? ctx.gt ?? ''))
  else if (t.includes('less_than')) what = tOutside('v_max').replace('{n}', String(ctx.le ?? ctx.lt ?? ''))
  else if (t.includes('pattern')) what = tOutside('v_invalid_chars')
  else if (t.includes('missing')) what = tOutside('v_required')
  else if (t.includes('parsing') || t.includes('type') || t.includes('enum') || t.includes('literal')) what = tOutside('v_invalid')
  else what = first.msg || tOutside('v_invalid')
  return field ? `${field}: ${what}` : what
}

export function errMessage(err: unknown): string {
  const e = err as AxiosError<{ detail?: unknown }>
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return formatValidation(detail as ValidationItem[])
  if (detail) return tOutside('request_failed')   // 不回显未知结构，避免泄露原始输入
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

export async function put<T>(url: string, data?: unknown): Promise<T> {
  const r = await client.put<T>(url, data)
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

export async function upload<T>(url: string, form: FormData,
                                onProgress?: (percent: number) => void): Promise<T> {
  const r = await client.post<T>(url, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    // 上传大附件时若没有任何进度反馈，用户无法区分"正在传"与"卡死了"，
    // 很可能重复点击或刷新页面——而刷新会中断上传，前功尽弃
    onUploadProgress: onProgress
      ? (e) => onProgress(e.total ? Math.round((e.loaded / e.total) * 100) : 0)
      : undefined,
    // 大文件上传耗时远超默认 30s（工厂现场网络更慢），不能沿用全局超时
    timeout: 0,
  })
  return r.data
}

export async function downloadBlob(url: string, params?: unknown): Promise<Blob> {
  const r = await client.get(url, { responseType: 'blob', params })
  return r.data
}

/** 附件下载：先换一张短时效票据，再交给浏览器原生下载。
 *
 * 原实现用 `fetch → res.blob()`：整个文件要先在浏览器内存里缓冲完才落盘。
 * 实测 4Mbps 下载 40MB 附件，**85 秒内界面零反馈**、浏览器下载管理器也不显示，
 * 用户很可能以为没点上而反复点击（每次又重拉一遍）；连接一断则前功尽弃——
 * 服务端本就支持 Range（206），但这条路径用不上；内存占用还等于文件大小。
 *
 * 改为普通导航后，进度、暂停续传、边下边写盘都交回浏览器原生下载管理器。
 * ticketUrl 为空时回退旧的 blob 方式（如导出类小文件仍走 axios）。
 */
export async function downloadFile(url: string, filename: string, ticketUrl?: string): Promise<void> {
  if (ticketUrl) {
    const r = await client.post<{ ticket: string }>(ticketUrl)
    const sep = url.includes('?') ? '&' : '?'
    const a = document.createElement('a')
    a.href = `${url}${sep}ticket=${encodeURIComponent(r.data.ticket)}`
    a.download = filename          // 服务端已带 Content-Disposition，这里只作提示
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    a.remove()
    return
  }
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
