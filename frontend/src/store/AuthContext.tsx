import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { clearToken, getToken, setToken } from '@/api/client'
import { auth } from '@/api/endpoints'
import type { User } from '@/types'

interface AuthCtx {
  user: User | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const Ctx = createContext<AuthCtx | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)

  useEffect(() => {
    if (getToken()) {
      auth.me().then(setUser).catch(() => clearToken())
    }
  }, [])

  const login = async (username: string, password: string) => {
    const data = await auth.login(username, password)
    setToken(data.access_token)
    setUser(data.user)
  }

  const logout = () => {
    clearToken()
    setUser(null)
  }

  return <Ctx.Provider value={{ user, login, logout }}>{children}</Ctx.Provider>
}

export function useAuth(): AuthCtx {
  const c = useContext(Ctx)
  if (!c) throw new Error('useAuth must be used within AuthProvider')
  return c
}
