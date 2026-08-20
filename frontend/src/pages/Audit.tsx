import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../store'

interface Log { id: number; event_domain: string; action: string; actor_name: string; actor_role: string; ip: string; target: string; detail: string; created_at: string }

async function downloadCsv() {
  const blob = await api<Blob>('/audit/export', { method: 'GET' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = 'audit_logs.csv'; a.click()
  URL.revokeObjectURL(url)
}

export default function Audit() {
  const { t, user } = useApp()
  const [logs, setLogs] = useState<Log[] | null>(null)

  useEffect(() => { api<Log[]>('/audit/logs?limit=300').then(setLogs).catch(() => setLogs([])) }, [])

  if (logs === null) return <div className="loading">...</div>

  return (
    <div className="card">
      <div className="row">
        <h2 style={{ margin: 0 }}>{t('audit')}</h2>
        <div className="spacer" />
        {(user!.role === 'coo_reviewer' || user!.role === 'admin') && (
          <button className="btn-ghost btn-sm" onClick={downloadCsv}>{t('export_csv')}</button>
        )}
      </div>
      <table style={{ marginTop: 12 }}>
        <thead><tr><th>时间</th><th>域.动作</th><th>操作人</th><th>IP</th><th>目标</th><th>说明</th></tr></thead>
        <tbody>
          {logs.map((l) => (
            <tr key={l.id}>
              <td>{l.created_at?.replace('T', ' ').slice(0, 19)}</td>
              <td>{l.event_domain}.{l.action}</td>
              <td>{l.actor_name}</td>
              <td>{l.ip}</td>
              <td>{l.target}</td>
              <td className="muted">{l.detail}</td>
            </tr>
          ))}
          {logs.length === 0 && <tr><td colSpan={6} className="muted">{t('no_data')}</td></tr>}
        </tbody>
      </table>
    </div>
  )
}
