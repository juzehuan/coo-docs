import { useState, type ReactNode } from 'react'
import { Layout, Menu, Avatar, Dropdown, Button, theme as antdTheme } from 'antd'
import {
  DashboardOutlined, FolderOpenOutlined, SafetyOutlined, FileSearchOutlined,
  AuditOutlined, TeamOutlined, DatabaseOutlined, LogoutOutlined, UserOutlined, ShoppingCartOutlined, BellOutlined,
} from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '@/store/AuthContext'
import { useI18n } from '@/i18n'
import LanguageSwitcher from './LanguageSwitcher'
import RoleTag from './RoleTag'
import NotificationBell from './NotificationBell'

const { Header, Sider, Content } = Layout

interface MenuItem {
  key: string
  icon: React.ReactNode
  label: string
  roles: string[]
}

const MENU: MenuItem[] = [
  { key: '/', icon: <DashboardOutlined />, label: 'dashboard', roles: ['submitter', 'dept_reviewer', 'coo_reviewer', 'auditor', 'admin'] },
  { key: '/todo', icon: <BellOutlined />, label: 'todo', roles: ['submitter', 'dept_reviewer', 'coo_reviewer', 'admin'] },
  { key: '/orders', icon: <ShoppingCartOutlined />, label: 'orders', roles: ['submitter', 'dept_reviewer', 'coo_reviewer', 'auditor', 'admin'] },
  { key: '/packages', icon: <FolderOpenOutlined />, label: 'packages', roles: ['submitter', 'dept_reviewer', 'coo_reviewer', 'auditor', 'admin'] },
  { key: '/controlled', icon: <SafetyOutlined />, label: 'controlled', roles: ['submitter', 'dept_reviewer', 'coo_reviewer', 'auditor', 'admin'] },
  { key: '/nas', icon: <DatabaseOutlined />, label: 'nas', roles: ['coo_reviewer', 'auditor', 'admin'] },
  { key: '/audit', icon: <FileSearchOutlined />, label: 'audit', roles: ['dept_reviewer', 'coo_reviewer', 'auditor', 'admin'] },
  { key: '/org', icon: <TeamOutlined />, label: 'users', roles: ['admin'] },
]

export default function AppLayout({ children }: { children?: ReactNode }) {
  const { user, logout } = useAuth()
  const { t } = useI18n()
  const navigate = useNavigate()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const { token } = antdTheme.useToken()

  if (!user) return null
  const items = MENU.filter((m) => m.roles.includes(user.role)).map((m) => ({
    key: m.key,
    icon: m.icon,
    label: t(m.label),
  }))

  const selectedKey = MENU.map((m) => m.key)
    .filter((k) => location.pathname === k || (k !== '/' && location.pathname.startsWith(k)))
    .sort((a, b) => b.length - a.length)[0] || '/'

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider collapsible collapsed={collapsed} onCollapse={setCollapsed} theme="dark">
        <div style={{
          height: 56, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 9,
          color: '#fff', fontWeight: 800, fontSize: 16, letterSpacing: 1,
          background: 'linear-gradient(135deg, #0b2545, #1f5fa8)', borderBottom: '1px solid rgba(255,255,255,0.10)',
        }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 26, height: 26, borderRadius: 7, background: 'linear-gradient(135deg,#2f7fd6,#1f5fa8)', fontWeight: 900, fontSize: 14, boxShadow: '0 2px 6px rgba(0,0,0,0.3)' }}>C</span>
          {!collapsed && <span>COO 平台</span>}
        </div>
        <Menu theme="dark" mode="inline" selectedKeys={[selectedKey]} items={items} onClick={(e) => navigate(e.key)} />
      </Sider>
      <Layout>
        <Header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px', background: '#fff', borderBottom: `1px solid ${token.colorBorderSecondary}`, boxShadow: '0 1px 3px rgba(11,37,69,0.05)' }}>
          <div />
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <NotificationBell />
            <LanguageSwitcher />
            <Dropdown
              menu={{
                items: [{ key: 'logout', icon: <LogoutOutlined />, label: t('logout'), onClick: () => { logout(); navigate('/login') } }],
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <Avatar size="small" icon={<UserOutlined />} />
                <span style={{ fontWeight: 600 }}>{user.display_name || user.username}</span>
                <RoleTag role={user.role} />
              </div>
            </Dropdown>
          </div>
        </Header>
        <Content style={{ margin: 20 }}>
          {children ?? <Outlet />}
        </Content>
      </Layout>
    </Layout>
  )
}
