import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { Button, Result, Spin } from 'antd'
import { useAuth } from './store/AuthContext'
import { useI18n } from './i18n'
import { canAccess } from './routes'
import AppLayout from './components/AppLayout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Todo from './pages/Todo'
import Orders from './pages/Orders'
import OrderDetail from './pages/OrderDetail'
import Packages from './pages/Packages'
import PackageDetail from './pages/PackageDetail'
import Controlled from './pages/Controlled'
import Audit from './pages/Audit'
import Org from './pages/Org'
import Nas from './pages/Nas'
import Notifications from './pages/Notifications'

function RequireAuth({ children }: { children: JSX.Element }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  return children
}

/** 路由级角色守卫。
 *
 * 侧边菜单只是隐藏入口，收藏链接、手输地址或角色被调整后仍能进入无权页面；
 * 那些页面的加载请求会拿到 403 并抛出未捕获异常，渲染中断后用户看到的是空白页
 * （实测提交人访问 /nas 即为白屏）。此处按同一份角色映射直接给出明确的无权提示。
 */
function RequireRole({ children }: { children: JSX.Element }) {
  const { user } = useAuth()
  const { t } = useI18n()
  const nav = useNavigate()
  const { pathname } = useLocation()
  if (!canAccess(user?.role, pathname)) {
    return (
      <Result
        status="403"
        title="403"
        subTitle={t('no_permission')}
        extra={<Button type="primary" onClick={() => nav('/')}>{t('dashboard')}</Button>}
      />
    )
  }
  return children
}

export default function App() {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin size="large" />
      </div>
    )
  }
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
      <Route
        path="/*"
        element={
          <RequireAuth>
            <AppLayout>
              <RequireRole>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/todo" element={<Todo />} />
                <Route path="/orders" element={<Orders />} />
                <Route path="/orders/:id" element={<OrderDetail />} />
                <Route path="/packages" element={<Packages />} />
                <Route path="/packages/:id" element={<PackageDetail />} />
                <Route path="/controlled" element={<Controlled />} />
                <Route path="/nas" element={<Nas />} />
                <Route path="/audit" element={<Audit />} />
                <Route path="/org" element={<Org />} />
                <Route path="/notifications" element={<Notifications />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
              </RequireRole>
            </AppLayout>
          </RequireAuth>
        }
      />
    </Routes>
  )
}
