import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Layout, Menu, Avatar, Dropdown, Button, theme as antdTheme } from 'antd'
import {
  DashboardOutlined, FolderOpenOutlined, SafetyOutlined, FileSearchOutlined,
  AuditOutlined, TeamOutlined, DatabaseOutlined, LogoutOutlined, UserOutlined, ShoppingCartOutlined, BellOutlined, MenuFoldOutlined, MenuUnfoldOutlined,
} from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '@/store/AuthContext'
import { useI18n } from '@/i18n'
import { SERIF } from '@/theme'
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
  { key: '/controlled', icon: <SafetyOutlined />, label: 'controlled', roles: ['dept_reviewer', 'coo_reviewer', 'admin'] },
  { key: '/nas', icon: <DatabaseOutlined />, label: 'nas', roles: ['coo_reviewer', 'auditor', 'admin'] },
  { key: '/audit', icon: <FileSearchOutlined />, label: 'audit', roles: ['auditor', 'admin'] },
  { key: '/org', icon: <TeamOutlined />, label: 'users', roles: ['admin'] },
]

export default function AppLayout({ children }: { children?: ReactNode }) {
  const { user, logout } = useAuth()
  const { t } = useI18n()
  const navigate = useNavigate()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const contentRef = useRef<HTMLElement>(null)
  // 路由切换时内容滚动容器回到顶部，避免新页面停留在旧滚动位置
  useEffect(() => {
    contentRef.current?.scrollTo({ top: 0, left: 0 })
  }, [location.pathname])
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
    <Layout style={{ height: '100vh', overflow: 'hidden' }}>
      <Sider collapsible collapsed={collapsed} onCollapse={setCollapsed} theme="dark" width={224} trigger={null}
        style={{ height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* 品牌区：黄铜徽标 + 宋体标题（固定顶部） */}
        <div style={{
          height: 60, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 11,
          borderBottom: '1px solid rgba(245, 241, 228, 0.12)',
          background: 'linear-gradient(180deg, rgba(168,131,60,0.10), transparent 70%)',
          position: 'relative',
        }}>
          <span style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 30, height: 30, borderRadius: 7,
            fontFamily: SERIF, fontWeight: 900, fontSize: 15, color: '#f7e9c9',
            background: 'linear-gradient(135deg, #16263f, #2a3d5c)',
            border: '1px solid rgba(201, 176, 106, 0.55)',
            boxShadow: '0 2px 8px rgba(0,0,0,0.35)',
          }}>C</span>
          {!collapsed && (
            <span style={{
              fontFamily: SERIF, color: '#f5f1e4', fontWeight: 700, fontSize: 15,
              letterSpacing: 3, lineHeight: 1.15,
            }}>
              COO 平台
            </span>
          )}
        </div>
        {/* 菜单区：独立滚动 */}
        <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
          <Menu theme="dark" mode="inline" selectedKeys={[selectedKey]} items={items} onClick={(e) => navigate(e.key)} />
        </div>
        {/* 侧栏底部品牌注记（固定底部） */}
        {!collapsed && (
          <div style={{
            flexShrink: 0, padding: '12px 0 14px', textAlign: 'center',
            fontSize: 10.5, letterSpacing: 1.5, color: 'rgba(245, 241, 228, 0.35)',
            fontFamily: SERIF,
          }}>
            Bintelli · COO Dossier
          </div>
        )}
      </Sider>
      <Layout style={{ height: '100vh', overflow: 'hidden' }}>
        <Header style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 20px 0 12px', background: '#fffdf7',
          borderBottom: '1px solid #e8e1d3',
          boxShadow: '0 1px 3px rgba(34,42,51,0.04)',
          position: 'sticky', top: 0, zIndex: 10,
        }}>
          <Button
            type="text" aria-label="toggle-menu"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <NotificationBell />
            <LanguageSwitcher />
            <Dropdown
              menu={{
                items: [{ key: 'logout', icon: <LogoutOutlined />, label: t('logout'), onClick: () => { logout(); navigate('/login') } }],
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 9, cursor: 'pointer', padding: '4px 8px', borderRadius: 8 }}>
                <Avatar size="small" style={{ background: '#16263f', color: '#f7e9c9' }} icon={<UserOutlined />} />
                <span style={{ fontWeight: 600, color: '#232a33' }}>{user.display_name || user.username}</span>
                <RoleTag role={user.role} />
              </div>
            </Dropdown>
          </div>
        </Header>
        <Content ref={contentRef} style={{ flex: 1, minWidth: 0, overflow: 'auto', padding: 22 }}>
          {children ?? <Outlet />}
        </Content>
      </Layout>
    </Layout>
  )
}
