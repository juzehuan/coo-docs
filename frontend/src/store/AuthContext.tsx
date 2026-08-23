import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { TOKEN_KEY, clearToken, getToken, setToken } from '@/api/client'
import { auth } from '@/api/endpoints'
import type { User } from '@/types'

interface AuthCtx {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const Ctx = createContext<AuthCtx | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  // 跨标签页同步登录状态。
  //
  // localStorage 是同源共享的：一个标签页登出会清掉 token，但**另一个标签页
  // 毫无察觉**——实测标签页1 退出后，标签页2 仍完整显示 20 行订单，界面看起来
  // 一切正常，直到下一次请求（最长 30 秒的通知轮询）才 401 跳转。工厂现场多用
  // 共用电脑，操作员点了退出就离开，下一个人能直接看到订单号、客户与产品，
  // 而订单号本身就是客户 PO 等敏感信息。
  //
  // storage 事件只在**其他**标签页改动时触发，本标签页自身的登出不会重复处理。
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key !== TOKEN_KEY) return
      if (!e.newValue) {
        setUser(null)
        if (!location.pathname.startsWith('/login')) location.href = '/login?reason=logged_out'
      } else if (e.oldValue && e.newValue !== e.oldValue) {
        // 其他标签页换了账号：整页重载，避免本页继续用旧身份渲染数据
        location.reload()
      }
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  useEffect(() => {
    if (getToken()) {
      auth.me()
        .then(setUser)
        .catch(() => clearToken())
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
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

  return <Ctx.Provider value={{ user, loading, login, logout }}>{children}</Ctx.Provider>
}

export function useAuth(): AuthCtx {
  const c = useContext(Ctx)
  if (!c) throw new Error('useAuth must be used within AuthProvider')
  return c
}
