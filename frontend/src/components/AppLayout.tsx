import { useEffect, useRef, useState, type ReactNode } from 'react'
import { App, Layout, Menu, Avatar, Dropdown, Button, Form, Input, Modal, theme as antdTheme } from 'antd'
import {
  DashboardOutlined, FolderOpenOutlined, SafetyOutlined, FileSearchOutlined,
  AuditOutlined, TeamOutlined, DatabaseOutlined, LogoutOutlined, UserOutlined, ShoppingCartOutlined, BellOutlined, MenuFoldOutlined, MenuUnfoldOutlined, KeyOutlined,
} from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { errMessage } from '@/api/client'
import { auth } from '@/api/endpoints'
import { useAuth } from '@/store/AuthContext'
import { useI18n } from '@/i18n'
import { useSubmit } from '@/hooks/useSubmit'
import { ROUTE_ROLES } from '@/routes'
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

const ICONS: Record<string, React.ReactNode> = {
  '/': <DashboardOutlined />,
  '/todo': <BellOutlined />,
  '/orders': <ShoppingCartOutlined />,
  '/packages': <FolderOpenOutlined />,
  '/controlled': <SafetyOutlined />,
  '/nas': <DatabaseOutlined />,
  '/audit': <FileSearchOutlined />,
  '/org': <TeamOutlined />,
}

// 角色映射来自 routes.ts，与路由守卫共用同一份定义，避免菜单与守卫各写一套而失配
const MENU: MenuItem[] = ROUTE_ROLES.map((r) => ({ key: r.key, icon: ICONS[r.key], label: r.label, roles: r.roles }))

export default function AppLayout({ children }: { children?: ReactNode }) {
  const { user, logout } = useAuth()
  const { t } = useI18n()
  const { loading: submitting, run: submitRun } = useSubmit()
  const navigate = useNavigate()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const contentRef = useRef<HTMLElement>(null)
  // 路由切换时内容滚动容器回到顶部，避免新页面停留在旧滚动位置
  useEffect(() => {
    contentRef.current?.scrollTo({ top: 0, left: 0 })
  }, [location.pathname])
  const { token } = antdTheme.useToken()
  const { message } = App.useApp()
  // 修改密码：规格 F-01 与用户手册都写明"登录后在右上角修改密码"，
  // 后端 /auth/change-password 一直存在，但界面此前没有任何入口
  const [pwdOpen, setPwdOpen] = useState(false)
  const [pwdForm] = Form.useForm()
  async function submitPwd() {
    const v = await pwdForm.validateFields().catch(() => null)
    if (!v) return
    // 连点尤其要防：第二次请求的"原密码"已经失效，用户会在成功之后紧接着看到一条报错
    if (await submitRun(() => auth.changePassword(v.old_password, v.new_password), t('save'))) {
      setPwdOpen(false); pwdForm.resetFields()
    }
  }

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
              {t('brand_short')}
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
                items: [
                  { key: 'pwd', icon: <KeyOutlined />, label: t('change_password'), onClick: () => setPwdOpen(true) },
                  { key: 'logout', icon: <LogoutOutlined />, label: t('logout'), onClick: () => { logout(); navigate('/login') } },
                ],
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

      <Modal title={t('change_password')} open={pwdOpen} onOk={submitPwd} confirmLoading={submitting}
             onCancel={() => { setPwdOpen(false); pwdForm.resetFields() }}
             okText={t('save')} cancelText={t('cancel')} destroyOnHidden>
        <Form form={pwdForm} layout="vertical">
          <Form.Item name="old_password" label={t('old_password')} rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="new_password" label={t('new_password')}
                     rules={[{ required: true }, { min: 6, message: t('v_too_short').replace('{n}', '6') }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="confirm" label={t('confirm_password')} dependencies={['new_password']}
            rules={[{ required: true }, ({ getFieldValue }) => ({
              validator: (_, value) => (!value || getFieldValue('new_password') === value)
                ? Promise.resolve() : Promise.reject(new Error(t('v_invalid'))),
            })]}>
            <Input.Password />
          </Form.Item>
        </Form>
      </Modal>
    </Layout>
  )
}
