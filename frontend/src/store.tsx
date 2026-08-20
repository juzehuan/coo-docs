import React, { createContext, useContext, useEffect, useState } from 'react'
import { api, clearToken, getToken, setToken } from './api'
import { dicts, Lang } from './i18n'

export interface User {
  id: number
  username: string
  display_name: string
  email: string
  phone: string
  dept_id: number | null
  role: string
  status: string
  last_login_at: string | null
  created_at: string | null
}

interface Ctx {
  user: User | null
  lang: Lang
  setLang: (l: Lang) => void
  t: (k: string) => string
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AppCtx = createContext<Ctx | null>(null)

export function useApp(): Ctx {
  const c = useContext(AppCtx)
  if (!c) throw new Error('useApp outside provider')
  return c
}

const LANG_KEY = 'coo_lang'

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [lang, setLangState] = useState<Lang>(
    (localStorage.getItem(LANG_KEY) as Lang) || 'zh',
  )

  useEffect(() => {
    const token = getToken()
    if (token) {
      api<User>('/auth/me')
        .then(setUser)
        .catch(() => clearToken())
    }
  }, [])

  function setLang(l: Lang) {
    setLangState(l)
    localStorage.setItem(LANG_KEY, l)
  }

  function t(k: string): string {
    return dicts[lang][k] ?? dicts.zh[k] ?? k
  }

  async function login(username: string, password: string) {
    const data = await api<{ access_token: string; user: User }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    setToken(data.access_token)
    setUser(data.user)
  }

  function logout() {
    clearToken()
    setUser(null)
    location.href = '/login'
  }

  return (
    <AppCtx.Provider value={{ user, lang, setLang, t, login, logout }}>
      {children}
    </AppCtx.Provider>
  )
}
