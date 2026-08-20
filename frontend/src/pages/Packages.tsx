import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useApp } from '../store'
import { STATUS_LABELS } from '../i18n'

interface PkgRow {
  id: number
  code: string
  name_zh: string
  name_en: string
  name_th: string
  current_status: string
  current_version: string
  attachment_count: number
  editable: boolean
  reviewable_dept: boolean
  reviewable_coo: boolean
}

export default function Packages() {
  const { t, lang } = useApp()
  const nav = useNavigate()
  const [rows, setRows] = useState<PkgRow[] | null>(null)

  useEffect(() => { api<PkgRow[]>('/packages').then(setRows).catch(() => setRows([])) }, [])

  if (rows === null) return <div className="loading">...</div>

  return (
    <div className="card">
      <h2>{t('packages')}</h2>
      <table>
        <thead>
          <tr><th>COO</th><th>{t('packages')}</th><th>{t('version')}</th><th>{t('status')}</th><th>{t('attachment')}</th><th></th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.code}</td>
              <td>{lang === 'en' ? r.name_en || r.name_zh : lang === 'th' ? r.name_th || r.name_zh : r.name_zh}</td>
              <td>{r.current_version || '-'}</td>
              <td><span className={`tag ${r.current_status}`}>{STATUS_LABELS[r.current_status]?.[lang] ?? r.current_status}</span></td>
              <td>{r.attachment_count}</td>
              <td><button className="btn-ghost btn-sm" onClick={() => nav(`/packages/${r.id}`)}>{t('detail')}</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
