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

  // 身份复核：角色/工厂授权在服务端改动后，已登录的这个会话不会自己知道。
  //
  // 第 73 轮实测：管理员把某提交人改为审计查看人后，**后端立刻生效**（第 63 轮已验证），
  // 而浏览器里的菜单纹丝不动、仍是旧角色；点进去得到的是一张空表、没有任何说明。
  // 整页刷新后才会更正（那时会重新取 /auth/me）——也就是说不一致只存在于
  // "不刷新的这段 SPA 会话"里，属显示层问题、不涉及越权（后端每次都按实时角色判定）。
  //
  // 因此按低频复核处理即可：60 秒一次 + 标签页重新可见时各取一次。
  // 角色变更是人事级别的低频事件，没必要跟着 30 秒的通知轮询走得更勤。
  // 只有真的变了才 setUser，避免每次复核都触发整棵树重渲染。
  // 依赖 user 而不是 []：挂载那一刻还没登录，getToken() 为空会直接 return，
  // 监听器压根装不上，登录后又不会重跑——第一版就是这么写错的，实测复核从不触发。
  useEffect(() => {
    if (!user) return
    let stopped = false
    const recheck = () => {
      if (!getToken() || document.hidden) return
      auth.me()
        .then((fresh) => {
          if (stopped) return
          setUser((prev) => {
            if (!prev) return prev
            const changed = prev.role !== fresh.role
              || prev.status !== fresh.status
              || JSON.stringify(prev.factory_ids) !== JSON.stringify(fresh.factory_ids)
            return changed ? fresh : prev
          })
        })
        // 失败不处理：401 由 axios 拦截器统一登出，其余（断网等）下次再试
        .catch(() => undefined)
    }
    const timer = window.setInterval(recheck, 60000)
    document.addEventListener('visibilitychange', recheck)
    return () => {
      stopped = true
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', recheck)
    }
    // 只关心"有没有登录"，不要跟着 user 的每次刷新反复重建定时器
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [!!user])

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
