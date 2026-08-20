import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../store'

interface Rec { id: number; run_type: string; total: number; success: number; failed: number; status: string; started_at: string }
interface Status { nas_root: string; nas_reachable: boolean; last_sync: Rec | null; pending_count: number }

export default function Nas() {
  const { t, user } = useApp()
  const [st, setSt] = useState<Status | null>(null)
  const [recs, setRecs] = useState<Rec[]>([])
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    const [s, r] = await Promise.all([api<Status>('/nas/status'), api<Rec[]>('/nas/records')])
    setSt(s); setRecs(r)
  }, [])
  useEffect(() => { load() }, [load])

  async function sync() {
    setBusy(true)
    try { await api('/nas/sync', { method: 'POST' }); await load() } finally { setBusy(false) }
  }

  if (!st) return <div className="loading">...</div>
  const canSync = user!.role === 'coo_reviewer' || user!.role === 'admin'

  return (
    <div className="grid cols-2">
      <div className="card">
        <h2>{t('sync_status')}</h2>
        <div className="row">
          <span className={`tag ${st.nas_reachable ? 'released' : 'rejected'}`}>{st.nas_reachable ? t('all_ok') : t('nas_unreachable')}</span>
          <div className="spacer" />
          {canSync && <button className="btn btn-sm" onClick={sync} disabled={busy}>{t('sync_now')}</button>}
        </div>
        <p className="muted" style={{ marginTop: 10 }}>NAS 根目录：{st.nas_root}</p>
        <p>{t('last_sync')}：{st.last_sync ? `${st.last_sync.started_at?.replace('T', ' ').slice(0, 19)} (${st.last_sync.success}/${st.last_sync.total})` : t('no_data')}</p>
        <p>{t('pending_sync')}：{st.pending_count}</p>
      </div>
      <div className="card">
        <h2>{t('sync_status')}</h2>
        <table>
          <thead><tr><th>ID</th><th>类型</th><th>成功/总数</th><th>状态</th><th>时间</th></tr></thead>
          <tbody>
            {recs.map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td><td>{r.run_type}</td><td>{r.success}/{r.total}</td>
                <td><span className={`tag ${r.status}`}>{r.status}</span></td>
                <td className="muted">{r.started_at?.replace('T', ' ').slice(0, 19)}</td>
              </tr>
            ))}
            {recs.length === 0 && <tr><td colSpan={5} className="muted">{t('no_data')}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
