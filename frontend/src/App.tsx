import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { Button, Result, Spin } from 'antd'
import { useAuth } from './store/AuthContext'
import { useI18n } from './i18n'
import { canAccess } from './routes'
import AppLayout from './components/AppLayout'
import ErrorBoundary from './components/ErrorBoundary'
import Login from './pages/Login'
// 业务页面按路由懒加载：此前全部静态引入，主包 1.86MB（gzip 594KB）一次下发，
// 4G 网络下首屏 4.9 秒才出现登录框。登录页不在此列——它是首屏必需的。
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Todo = lazy(() => import('./pages/Todo'))
const Orders = lazy(() => import('./pages/Orders'))
const OrderDetail = lazy(() => import('./pages/OrderDetail'))
const Packages = lazy(() => import('./pages/Packages'))
const PackageDetail = lazy(() => import('./pages/PackageDetail'))
const Controlled = lazy(() => import('./pages/Controlled'))
const Audit = lazy(() => import('./pages/Audit'))
const Org = lazy(() => import('./pages/Org'))
const Nas = lazy(() => import('./pages/Nas'))
const Notifications = lazy(() => import('./pages/Notifications'))

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
  // 显式取路由 location：用全局 window.location 虽然也能读到 pathname，
  // 但本组件不会订阅路由变化，客户端跳转时 key 不一定重算
  const routeLoc = useLocation()
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
              {/* 切页时分块尚未到达的短暂等待态，避免白屏 */}
              {/* 内层边界：只兜住页面内容，出错时侧边栏与顶栏仍在，
                  用户可以直接切到别的页面，而不是被困在一片空白里。
                  key 绑定路径——换页即重建边界，否则一次出错会让后续页面
                  一直停留在错误态 */}
              <ErrorBoundary key={routeLoc.pathname}>
              <Suspense fallback={<div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>}>
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
              </Suspense>
              </ErrorBoundary>
              </RequireRole>
            </AppLayout>
          </RequireAuth>
        }
      />
    </Routes>
  )
}
