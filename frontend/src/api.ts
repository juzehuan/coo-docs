export const TOKEN_KEY = 'coo_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(t: string) {
  localStorage.setItem(TOKEN_KEY, t)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

export async function api<T = any>(
  path: string,
  opts: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    ...(opts.headers as Record<string, string>),
  }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  if (!(opts.body instanceof FormData) && opts.body) {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(`/api${path}`, { ...opts, headers })
  if (res.status === 401) {
    clearToken()
    if (location.pathname !== '/login') location.href = '/login'
    throw new Error('unauthorized')
  }
  if (!res.ok) {
    const text = await res.text()
    let msg = text
    try {
      msg = JSON.parse(text).detail || text
    } catch {
      /* ignore */
    }
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  if (res.status === 204) return undefined as T
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) return res.json()
  return res.blob() as unknown as T
}
