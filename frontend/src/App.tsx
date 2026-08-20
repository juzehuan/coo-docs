import { Navigate, Route, Routes } from 'react-router-dom'
import { useApp } from './store'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Packages from './pages/Packages'
import PackageDetail from './pages/PackageDetail'
import Controlled from './pages/Controlled'
import Audit from './pages/Audit'
import Org from './pages/Org'
import Nas from './pages/Nas'

function RequireAuth({ children }: { children: JSX.Element }) {
  const { user } = useApp()
  if (!user) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  const { user } = useApp()
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
      <Route
        path="/*"
        element={
          <RequireAuth>
            <Layout>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/packages" element={<Packages />} />
                <Route path="/packages/:id" element={<PackageDetail />} />
                <Route path="/controlled" element={<Controlled />} />
                <Route path="/audit" element={<Audit />} />
                <Route path="/org" element={<Org />} />
                <Route path="/nas" element={<Nas />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Layout>
          </RequireAuth>
        }
      />
    </Routes>
  )
}
