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
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'linear-gradient(135deg, #1f5fa8, #0b2545)' }}>
      <div style={{ position: 'absolute', top: 24, right: 24 }}><LanguageSwitcher /></div>
      <Card variant="borderless" style={{ width: 380, boxShadow: '0 10px 40px rgba(0,0,0,.25)' }}>
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <SafetyCertificateOutlined style={{ fontSize: 40, color: '#1f5fa8' }} />
          <Typography.Title level={4} style={{ marginTop: 8, marginBottom: 0 }}>{t('app_name')}</Typography.Title>
        </div>
        <Form form={form} layout="vertical" onFinish={onFinish} initialValues={{ username: '', password: '' }}>
          <Form.Item name="username" rules={[{ required: true, message: t('username') }]}>
            <Input prefix={<UserOutlined />} placeholder={t('username')} size="large" autoFocus />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: t('password') }]}>
            <Input.Password prefix={<LockOutlined />} placeholder={t('password')} size="large" />
          </Form.Item>
          <Button type="primary" htmlType="submit" size="large" block loading={loading}>{t('login')}</Button>
        </Form>
        <Typography.Paragraph type="secondary" style={{ textAlign: 'center', marginTop: 16, marginBottom: 0, fontSize: 12 }}>
          admin / admin123 · coo / coo123
        </Typography.Paragraph>
      </Card>
    </div>
  )
}
