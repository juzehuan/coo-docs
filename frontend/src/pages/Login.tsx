import { FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../store'

export default function Login() {
  const { login, t } = useApp()
  const nav = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setErr('')
    setBusy(true)
    try {
      await login(username.trim(), password)
      nav('/')
    } catch (e: any) {
      setErr(e.message || 'login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={onSubmit}>
        <h1>{t('app_name')}</h1>
        <div className="field">
          <label>{t('username')}</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
        </div>
        <div className="field">
          <label>{t('password')}</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        {err && <div className="err">{err}</div>}
        <button className="btn" style={{ width: '100%', marginTop: 12 }} disabled={busy}>
          {t('login')}
        </button>
        <div className="muted" style={{ marginTop: 14, textAlign: 'center' }}>
          管理员 admin / admin123 · COO coo / coo123
        </div>
      </form>
    </div>
  )
}
