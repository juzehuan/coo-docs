import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Alert, App, Button, Form, Input, Typography } from 'antd'
import { LockOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons'
import { errMessage } from '@/api/client'
import { auth } from '@/api/endpoints'
import { useAuth } from '@/store/AuthContext'
import { useI18n } from '@/i18n'
import { ROLE_LABELS } from '@/i18n/messages'
import { SERIF } from '@/theme'
import LanguageSwitcher from '@/components/LanguageSwitcher'
import type { Lang, Role } from '@/types'

// 演示账号的公开口令，与后端 api/auth.py 的 DEMO_CREDENTIALS 一一对应。
// 按钮渲染与否由后端 /auth/demo-accounts 据实回答：它逐个校验口令是否仍为演示值，
// 生产部署返回空数组、入口自然消失，不会出现点下去必然 401 的假按钮。
const DEMO_PASSWORDS: Record<string, string> = {
  admin: 'admin123',
  coo: 'coo123',
  auditor: 'audit123',
  dept_wai: 'dept123',
  dept_eng: 'dept123',
  dept_sal: 'dept123',
  dept_fin: 'dept123',
  dept_log: 'dept123',
  dept_prd: 'dept123',
  dept_qal: 'dept123',
  dept_adm: 'dept123',
  dept_eng2: 'dept123',
  submit_eng: 'user123',
  submit_fin: 'user123',
  submit_log: 'user123',
}

export default function Login() {
  const { login } = useAuth()
  const { t, lang } = useI18n()
  const nav = useNavigate()
  const { message } = App.useApp()
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()
  // 会话失效的原因由拦截器通过查询串传来：整页跳转会让 toast 一起消失，
  // 只有落在登录页上的提示才能真正被用户看到
  const sessionReason = new URLSearchParams(location.search).get('reason')
  // 仅当这些演示账号在当前环境真实存在时才显示快捷登录
  const [demoAccounts, setDemoAccounts] = useState<{ username: string; display_name: string; role: Role }[]>([])
  useEffect(() => {
    auth.demoAccounts()
      .then((list) => setDemoAccounts(list.filter((a) => DEMO_PASSWORDS[a.username])))
      .catch(() => setDemoAccounts([]))   // 拿不到就不显示，宁可少一个入口也不给坏按钮
  }, [])

  async function onFinish(values: { username: string; password: string }) {
    setLoading(true)
    try {
      await login(values.username.trim(), values.password)
      nav('/')
    } catch (e: unknown) {
      // 必须用 errMessage 取后端 detail：直接读 e.message 拿到的是 axios 的
      // "Request failed with status code 401" —— 英文、且丢掉了后端说明。
      // 账号锁定（423「账号已锁定，请稍后重试」）尤其致命：用户看不到需要等待。
      message.error(errMessage(e) || t('login_failed'))
    } finally {
      setLoading(false)
    }
  }

  function quickLogin(username: string, password: string) {
    form.setFieldsValue({ username, password })
    onFinish({ username, password })
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex',
      background: '#f5f2ea',
      backgroundImage: 'radial-gradient(circle at 12% 88%, rgba(168,131,60,0.05) 0, transparent 38%), radial-gradient(circle at 92% 8%, rgba(22,38,63,0.04) 0, transparent 42%)',
    }}>
      {/* 左栏：品牌陈述（桌面端显示） */}
      <div style={{
        flex: '1 1 46%', display: 'none',
        flexDirection: 'column', justifyContent: 'space-between',
        padding: '48px 56px', position: 'relative', overflow: 'hidden',
        background: 'linear-gradient(160deg, #101d31 0%, #16263f 55%, #20324e 100%)',
        color: '#f5f1e4',
      }} className="coo-login-brand">
        {/* 装饰纹理 */}
        <div style={{
          position: 'absolute', inset: 0, opacity: 0.5,
          backgroundImage: 'linear-gradient(rgba(245,241,228,0.045) 1px, transparent 1px), linear-gradient(90deg, rgba(245,241,228,0.045) 1px, transparent 1px)',
          backgroundSize: '42px 42px',
        }} />
        {/* zIndex 需高于下方品牌标题块（同为 zIndex:1 时 DOM 靠后者会盖住此按钮导致无法点击） */}
        <div style={{ position: 'absolute', top: 48, right: 56, zIndex: 2 }}>
          <LanguageSwitcher />
        </div>

        <div style={{ position: 'relative', zIndex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 13 }}>
            <span style={{
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              width: 40, height: 40, borderRadius: 9,
              fontFamily: SERIF, fontWeight: 900, fontSize: 20, color: '#f7e9c9',
              background: 'linear-gradient(135deg, #20324e, #2a3d5c)',
              border: '1px solid rgba(201, 176, 106, 0.6)',
              boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
            }}>C</span>
            <span style={{ fontFamily: SERIF, fontSize: 20, fontWeight: 700, letterSpacing: 4 }}>{t('brand_short')}</span>
          </div>

          <div style={{ marginTop: 120, maxWidth: 420 }}>
            <div style={{ width: 46, height: 2, background: 'linear-gradient(90deg,#c9b06a,#a8833c)', marginBottom: 26 }} />
            <Typography.Title style={{
              fontFamily: SERIF, color: '#f5f1e4', fontWeight: 700, fontSize: 34,
              lineHeight: 1.45, letterSpacing: 2, margin: 0, marginBottom: 18,
            }}>
              {t('login_brand_title1')}
              <br />
              {t('login_brand_title2')}
            </Typography.Title>
            <Typography.Paragraph style={{ color: 'rgba(245,241,228,0.6)', fontSize: 14, lineHeight: 2, letterSpacing: 0.5, marginBottom: 0 }}>
              {t('login_brand_desc')}
            </Typography.Paragraph>
          </div>
        </div>

        <div style={{ position: 'relative', zIndex: 1, display: 'flex', gap: 34, fontSize: 12, letterSpacing: 1.5, color: 'rgba(245,241,228,0.5)' }}>
          <span>DEPARTMENT REVIEW</span>
          <span>COO FINAL</span>
          <span>CONTROLLED RELEASE</span>
        </div>
      </div>

      {/* 右栏：暖纸表单 */}
      <div style={{
        flex: '1 1 54%', display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: '24px 24px 24px', position: 'relative',
      }}>
        <div style={{ position: 'absolute', top: 24, right: 24, display: 'none' }} className="coo-login-lang-mobile">
          <LanguageSwitcher />
        </div>

        <div style={{ width: '100%', maxWidth: 380, animation: 'coo-rise 0.5s ease both' }}>
          <div style={{ marginBottom: 30 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 18 }}>
              <span style={{
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                width: 42, height: 42, borderRadius: 10,
                background: 'linear-gradient(135deg,#16263f,#2a3d5c)',
                border: '1px solid rgba(201,176,106,0.5)',
              }}>
                <SafetyCertificateOutlined style={{ fontSize: 20, color: '#f7e9c9' }} />
              </span>
              <span style={{ fontFamily: SERIF, fontSize: 20, fontWeight: 700, letterSpacing: 3, color: '#16263f' }}>{t('app_name')}</span>
            </div>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0, fontSize: 13, letterSpacing: 0.5, color: '#75705f' }}>
              {t('subtitle')}
            </Typography.Paragraph>
            <div style={{ width: 46, height: 2, background: 'linear-gradient(90deg,#c9b06a,#a8833c)', marginTop: 16 }} />
          </div>

          {sessionReason && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 16 }}
              message={sessionReason === 'disabled' ? t('session_disabled')
                : sessionReason === 'logged_out' ? t('session_logged_out')
                : t('session_expired')}
            />
          )}

          <Form form={form} layout="vertical" onFinish={onFinish} initialValues={{ username: '', password: '' }}>
            <Form.Item name="username" rules={[{ required: true, message: t('username') }]}>
              <Input prefix={<UserOutlined style={{ color: '#a8833c' }} />} placeholder={t('username')} size="large" autoFocus variant="filled" style={{ background: '#fffef8' }} />
            </Form.Item>
            <Form.Item name="password" rules={[{ required: true, message: t('password') }]}>
              <Input.Password prefix={<LockOutlined style={{ color: '#a8833c' }} />} placeholder={t('password')} size="large" variant="filled" style={{ background: '#fffef8' }} />
            </Form.Item>
            <Button type="primary" htmlType="submit" size="large" block loading={loading} className="coo-btn-hero">{t('login')}</Button>
          </Form>

          {/* 演示账号一键登录：仅演示环境显示 */}
          {demoAccounts.length > 0 && (
          <div style={{ marginTop: 26 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <div style={{ flex: 1, height: 1, background: '#e5dfd0' }} />
              <span style={{ fontSize: 12, color: '#a49e8c', letterSpacing: 0.5 }}>{t('demo_login')}</span>
              <div style={{ flex: 1, height: 1, background: '#e5dfd0' }} />
            </div>
            {/* 按钮文字用姓名而非角色名：15 个账号里 8 个都是「部门审核人」，
                只给角色名会出现 8 个一模一样的按钮。角色与账号名放进 title。
                auto-fill 网格：账号数量随环境变化，写死列数会在换行处留下空位。 */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(92px, 1fr))', gap: 8 }}>
              {demoAccounts.map((a) => (
                <Button
                  key={a.username}
                  size="small"
                  disabled={loading}
                  onClick={() => quickLogin(a.username, DEMO_PASSWORDS[a.username])}
                  style={{ background: '#fffef8', borderColor: '#e5dfd0', color: '#75705f', fontSize: 12, padding: '0 6px' }}
                  title={`${a.username} · ${ROLE_LABELS[a.role]?.[lang as Lang] ?? a.role}`}
                >
                  {a.display_name || ROLE_LABELS[a.role]?.[lang as Lang] || a.role}
                </Button>
              ))}
            </div>
          </div>
          )}
        </div>
      </div>
    </div>
  )
}
