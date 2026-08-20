import { NavLink } from 'react-router-dom'
import { ReactNode } from 'react'
import { useApp } from '../store'
import { LANG_LABELS, Lang } from '../i18n'

interface MenuItem {
  to: string
  key: string
  roles: string[]
}

const MENU: MenuItem[] = [
  { to: '/', key: 'dashboard', roles: ['submitter', 'dept_reviewer', 'coo_reviewer', 'auditor', 'admin'] },
  { to: '/packages', key: 'packages', roles: ['submitter', 'dept_reviewer', 'coo_reviewer', 'auditor', 'admin'] },
  { to: '/controlled', key: 'controlled', roles: ['submitter', 'dept_reviewer', 'coo_reviewer', 'auditor', 'admin'] },
  { to: '/nas', key: 'nas', roles: ['coo_reviewer', 'auditor', 'admin'] },
  { to: '/audit', key: 'audit', roles: ['dept_reviewer', 'coo_reviewer', 'auditor', 'admin'] },
  { to: '/org', key: 'users', roles: ['admin'] },
]

export default function Layout({ children }: { children: ReactNode }) {
  const { user, t, lang, setLang, logout } = useApp()
  if (!user) return null
  const items = MENU.filter((m) => m.roles.includes(user.role))

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">{t('app_name')}</div>
        <nav>
          {items.map((m) => (
            <NavLink key={m.to} to={m.to} end={m.to === '/'} className={({ isActive }) => (isActive ? 'nav-item active' : 'nav-item')}>
              {t(m.key)}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="top-user">
            {user.display_name || user.username}
            <span className="role-badge">{t('role')}: {user.role}</span>
          </div>
          <div className="top-actions">
            <select value={lang} onChange={(e) => setLang(e.target.value as Lang)} className="lang-select">
              {(Object.keys(LANG_LABELS) as Lang[]).map((l) => (
                <option key={l} value={l}>{LANG_LABELS[l]}</option>
              ))}
            </select>
            <button className="btn-ghost" onClick={logout}>{t('logout')}</button>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  )
}
