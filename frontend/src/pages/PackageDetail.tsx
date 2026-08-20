import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import { useApp } from '../store'
import { STATUS_LABELS } from '../i18n'

interface Att { id: number; original_name: string; file_size: number; order_no: string; batch_no: string; uploaded_at: string; nas_synced: boolean }
interface Ver { id: number; version_no: string; status: string; change_note: string; locked: boolean; attachments: Att[]; submitted_by: number | null }
interface Pkg { id: number; code: string; name_zh: string; name_en: string; name_th: string; review_focus: string; required: boolean; versions: Ver[] }

function fmtSize(n: number) {
  if (n < 1024) return n + ' B'
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB'
  return (n / 1024 / 1024).toFixed(1) + ' MB'
}

export default function PackageDetail() {
  const { id } = useParams()
  const { t, lang, user } = useApp()
  const [pkg, setPkg] = useState<Pkg | null>(null)
  const [vid, setVid] = useState<number | null>(null)
  const [files, setFiles] = useState<FileList | null>(null)
  const [orderNo, setOrderNo] = useState('')
  const [batchNo, setBatchNo] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  const load = useCallback(() => {
    api<Pkg>(`/packages/${id}`).then((p) => {
      setPkg(p)
      setVid(p.versions[0]?.id ?? null)
    })
  }, [id])

  useEffect(() => { load() }, [load])

  if (!pkg) return <div className="loading">...</div>
  const ver = pkg.versions.find((v) => v.id === vid) || pkg.versions[0]
  const canEdit = ver && (user!.role === 'admin' || user!.role === 'dept_reviewer' || user!.role === 'coo_reviewer' || (user!.role === 'submitter'))
    && ver.status !== 'released'
  const canReviewDept = ver && user!.role === 'dept_reviewer' && ver.status === 'pending_dept'
  const canReviewCoo = ver && (user!.role === 'coo_reviewer' || user!.role === 'admin') && ver.status === 'pending_coo'

  async function upload() {
    if (!files || !ver) return
    setBusy(true); setMsg('')
    try {
      const fd = new FormData()
      for (const f of Array.from(files)) fd.append('files', f)
      fd.append('order_no', orderNo)
      fd.append('batch_no', batchNo)
      await api(`/packages/${id}/versions/${ver.id}/attachments`, { method: 'POST', body: fd })
      setFiles(null); setOrderNo(''); setBatchNo('')
      load()
    } catch (e: any) { setMsg(e.message) } finally { setBusy(false) }
  }
  async function delAtt(aid: number) {
    if (!ver) return
    await api(`/packages/${id}/versions/${ver.id}/attachments/${aid}`, { method: 'DELETE' })
    load()
  }
  async function submit() {
    if (!ver) return
    await api(`/packages/${id}/versions/${ver.id}/submit`, { method: 'POST' })
    load()
  }
  async function review(decision: string, level: string) {
    if (!ver) return
    setBusy(true); setMsg('')
    try {
      await api(`/packages/${id}/versions/${ver.id}/review`, {
        method: 'POST', body: JSON.stringify({ decision, level, reason }),
      })
      setReason(''); load()
    } catch (e: any) { setMsg(e.message) } finally { setBusy(false) }
  }
  async function newVersion() {
    await api(`/packages/${id}/versions`, { method: 'POST', body: JSON.stringify({ change_note: '' }) })
    load()
  }

  return (
    <div>
      <div className="card">
        <div className="row">
          <h2 style={{ margin: 0 }}>{pkg.code} · {lang === 'en' ? pkg.name_en : lang === 'th' ? pkg.name_th : pkg.name_zh}</h2>
          <span className={`tag ${ver?.status}`}>{ver ? STATUS_LABELS[ver.status]?.[lang] ?? ver.status : ''}</span>
          <div className="spacer" />
          <button className="btn-ghost btn-sm" onClick={newVersion}>{t('new_version')}</button>
        </div>
        <div className="muted" style={{ marginTop: 8 }}>{t('dept')}：{pkg.review_focus}</div>
      </div>

      <div className="card">
        <h2>{t('version')}</h2>
        <div className="row">
          {pkg.versions.map((v) => (
            <button key={v.id} className={v.id === vid ? 'btn btn-sm' : 'btn-ghost btn-sm'} onClick={() => setVid(v.id)}>
              {v.version_no} <span className={`tag ${v.status}`}>{STATUS_LABELS[v.status]?.[lang]}</span>
            </button>
          ))}
        </div>
      </div>

      {ver && (
        <div className="card">
          <h2>{t('attachment')}</h2>
          <table>
            <thead><tr><th>{t('attachment')}</th><th>{t('order_no')}</th><th>{t('batch_no')}</th><th>MD5/NAS</th><th></th></tr></thead>
            <tbody>
              {ver.attachments.map((a) => (
                <tr key={a.id}>
                  <td>
                    <a href={`/api/packages/${id}/versions/${ver.id}/attachments/${a.id}/file`} target="_blank" rel="noreferrer">{a.original_name}</a>
                    <div className="muted">{fmtSize(a.file_size)}</div>
                  </td>
                  <td>{a.order_no}</td>
                  <td>{a.batch_no}</td>
                  <td>{a.nas_synced ? '✅' : '⏳'}</td>
                  <td>{canEdit && <button className="btn-danger btn-sm" onClick={() => delAtt(a.id)}>{t('cancel')}</button>}</td>
                </tr>
              ))}
              {ver.attachments.length === 0 && <tr><td colSpan={5} className="muted">{t('no_data')}</td></tr>}
            </tbody>
          </table>

          {canEdit && (
            <div className="card" style={{ marginTop: 14, background: '#fafcff' }}>
              <h2>{t('upload')}</h2>
              <div className="row">
                <input type="file" multiple onChange={(e) => setFiles(e.target.files)} />
                <input placeholder={t('order_no')} value={orderNo} onChange={(e) => setOrderNo(e.target.value)} />
                <input placeholder={t('batch_no')} value={batchNo} onChange={(e) => setBatchNo(e.target.value)} />
                <button className="btn btn-sm" onClick={upload} disabled={busy || !files}>{t('upload')}</button>
                {ver.attachments.length > 0 && <button className="btn-ok btn-sm" onClick={submit}>{t('submit')}</button>}
              </div>
              {msg && <div className="err">{msg}</div>}
            </div>
          )}

          {canReviewDept && (
            <div className="card" style={{ marginTop: 14, background: '#fffbeb' }}>
              <h2>{t('review')}</h2>
              <textarea placeholder={t('change_note')} value={reason} onChange={(e) => setReason(e.target.value)} style={{ width: '100%' }} />
              <div className="row" style={{ marginTop: 8 }}>
                <button className="btn-ok btn-sm" onClick={() => review('approve', 'dept')} disabled={busy}>{t('approve')}</button>
                <button className="btn-danger btn-sm" onClick={() => review('reject', 'dept')} disabled={busy || !reason}>{t('reject')}</button>
              </div>
              {msg && <div className="err">{msg}</div>}
            </div>
          )}

          {canReviewCoo && (
            <div className="card" style={{ marginTop: 14, background: '#eff6ff' }}>
              <h2>{t('review')}</h2>
              <textarea placeholder={t('change_note')} value={reason} onChange={(e) => setReason(e.target.value)} style={{ width: '100%' }} />
              <div className="row" style={{ marginTop: 8 }}>
                <button className="btn-ok btn-sm" onClick={() => review('approve', 'coo')} disabled={busy}>{t('approve')}</button>
                <button className="btn-danger btn-sm" onClick={() => review('reject', 'coo')} disabled={busy || !reason}>{t('reject')}</button>
              </div>
              {msg && <div className="err">{msg}</div>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
