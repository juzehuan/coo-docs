import axios, { type AxiosRequestConfig, type AxiosError } from 'axios'

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
  (err: AxiosError) => {
    if (err.response?.status === 401) {
      clearToken()
      if (location.pathname !== '/login') location.href = '/login'
    }
    return Promise.reject(err)
  },
)

export function errMessage(err: unknown): string {
  const e = err as AxiosError<{ detail?: unknown }>
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail) return JSON.stringify(detail)
  return e?.message || '请求失败'
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

export type { AxiosRequestConfig }
