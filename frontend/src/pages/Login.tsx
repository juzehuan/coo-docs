import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { App, Button, Form, Input, Typography } from 'antd'
import { LockOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons'
import { useAuth } from '@/store/AuthContext'
import { useI18n } from '@/i18n'
import { SERIF } from '@/theme'
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
        <div style={{ position: 'absolute', top: 48, right: 56, zIndex: 1 }}>
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

          <Form form={form} layout="vertical" onFinish={onFinish} initialValues={{ username: '', password: '' }}>
            <Form.Item name="username" rules={[{ required: true, message: t('username') }]}>
              <Input prefix={<UserOutlined style={{ color: '#a8833c' }} />} placeholder={t('username')} size="large" autoFocus variant="filled" style={{ background: '#fffef8' }} />
            </Form.Item>
            <Form.Item name="password" rules={[{ required: true, message: t('password') }]}>
              <Input.Password prefix={<LockOutlined style={{ color: '#a8833c' }} />} placeholder={t('password')} size="large" variant="filled" style={{ background: '#fffef8' }} />
            </Form.Item>
            <Button type="primary" htmlType="submit" size="large" block loading={loading} className="coo-btn-hero">{t('login')}</Button>
          </Form>

          <Typography.Paragraph type="secondary" style={{ textAlign: 'center', marginTop: 22, marginBottom: 0, fontSize: 12, color: '#a49e8c', letterSpacing: 0.5 }}>
            admin / admin123 · coo / coo123
          </Typography.Paragraph>
        </div>
      </div>
    </div>
  )
}
