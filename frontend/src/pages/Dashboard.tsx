import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useApp } from '../store'
import { STATUS_LABELS } from '../i18n'

interface Dash {
  package_completion: number
  total_attachments: number
  pending_mine: number
  released: number
  overdue: number
  package_progress: { code: string; name: string; status: string; percent: number; attachments: number }[]
  need_attention: { code: string; name: string; issue: string; reason: string }[]
}

export default function Dashboard() {
  const { t, lang } = useApp()
  const nav = useNavigate()
  const [d, setD] = useState<Dash | null>(null)

  useEffect(() => { api<Dash>('/dashboard').then(setD).catch(() => {}) }, [])

  if (!d) return <div className="loading">...</div>

  return (
    <div>
      <div className="grid cols-4">
        <div className="stat"><div className="num">{d.package_completion}%</div><div className="label">{t('progress')}</div></div>
        <div className="stat"><div className="num">{d.pending_mine}</div><div className="label">{t('pending_mine')}</div></div>
        <div className="stat"><div className="num">{d.released}</div><div className="label">{t('released')}</div></div>
        <div className="stat"><div className="num">{d.total_attachments}</div><div className="label">{t('attachment')}</div></div>
      </div>

      <div className="grid cols-2" style={{ marginTop: 18 }}>
        <div className="card">
          <h2>{t('packages')}</h2>
          <table>
            <thead><tr><th>COO</th><th>{t('packages')}</th><th>{t('status')}</th><th>{t('attachment')}</th><th></th></tr></thead>
            <tbody>
              {d.package_progress.map((p) => (
                <tr key={p.code}>
                  <td>{p.code}</td>
                  <td>{p.name}</td>
                  <td><span className={`tag ${p.status}`}>{STATUS_LABELS[p.status]?.[lang] ?? p.status}</span></td>
                  <td>{p.attachments}</td>
                  <td><button className="btn-ghost btn-sm" onClick={() => nav('/packages')}>{t('detail')}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card">
          <h2>{t('need_attention')}</h2>
          {d.need_attention.length === 0 ? <div className="muted">{t('no_data')}</div> : (
            <table>
              <thead><tr><th>COO</th><th>{t('packages')}</th><th>{t('issue') ?? '事项'}</th></tr></thead>
              <tbody>
                {d.need_attention.map((n, i) => (
                  <tr key={i}><td>{n.code}</td><td>{n.name}</td><td>{n.issue}{n.reason ? `：${n.reason}` : ''}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
