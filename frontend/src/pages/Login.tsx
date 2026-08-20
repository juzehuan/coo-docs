import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { App, Button, Card, Form, Input, Typography } from 'antd'
import { LockOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons'
import { useAuth } from '@/store/AuthContext'
import { useI18n } from '@/i18n'
import LanguageSwitcher from '@/components/LanguageSwitcher'

export default function Login() {
  const { login } = useAuth()
  const { t } = useI18n()
  const nav = useNavigate()
  const { message } = App.useApp()
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()

  async function onFinish(values: { username: string; password: string }) {
    setLoading(true)
    try {
      await login(values.username.trim(), values.password)
      nav('/')
    } catch (e: any) {
      message.error(e?.message || t('login_failed'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(150deg, #0b2545 0%, #1f5fa8 55%, #2f7fd6 100%)',
    }}>
      {/* 环境光晕，营造纵深 */}
      <div style={{ position: 'absolute', top: -120, left: '10%', width: 420, height: 420, borderRadius: '50%', background: 'radial-gradient(circle, rgba(47,127,214,.55), transparent 70%)', filter: 'blur(20px)' }} />
      <div style={{ position: 'absolute', bottom: -140, right: '8%', width: 460, height: 460, borderRadius: '50%', background: 'radial-gradient(circle, rgba(11,37,69,.6), transparent 70%)', filter: 'blur(24px)' }} />
      <div style={{ position: 'absolute', top: 24, right: 24, zIndex: 2 }}><LanguageSwitcher /></div>
      <Card variant="borderless" style={{ width: 390, borderRadius: 14, boxShadow: '0 20px 60px rgba(0,0,0,.35)', border: '1px solid rgba(255,255,255,.3)', backdropFilter: 'blur(6px)' }}>
        <div style={{ textAlign: 'center', marginBottom: 22 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 60, height: 60, borderRadius: 16, background: 'linear-gradient(135deg,#2f7fd6,#1f5fa8)', boxShadow: '0 10px 24px rgba(31,95,168,.4)' }}>
            <SafetyCertificateOutlined style={{ fontSize: 30, color: '#fff' }} />
          </span>
          <Typography.Title level={4} style={{ marginTop: 14, marginBottom: 2 }}>{t('app_name')}</Typography.Title>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0, fontSize: 12 }}>
            {t('subtitle')}
          </Typography.Paragraph>
        </div>
        <Form form={form} layout="vertical" onFinish={onFinish} initialValues={{ username: '', password: '' }}>
          <Form.Item name="username" rules={[{ required: true, message: t('username') }]}>
            <Input prefix={<UserOutlined />} placeholder={t('username')} size="large" autoFocus variant="filled" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: t('password') }]}>
            <Input.Password prefix={<LockOutlined />} placeholder={t('password')} size="large" variant="filled" />
          </Form.Item>
          <Button type="primary" htmlType="submit" size="large" block loading={loading} className="coo-btn-hero">{t('login')}</Button>
        </Form>
        <Typography.Paragraph type="secondary" style={{ textAlign: 'center', marginTop: 18, marginBottom: 0, fontSize: 12 }}>
          admin / admin123 · coo / coo123
        </Typography.Paragraph>
      </Card>
    </div>
  )
}
