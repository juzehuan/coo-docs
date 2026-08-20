import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../store'
import { STATUS_LABELS } from '../i18n'

interface Row { package_code: string; package_name: string; version: any; attachment_count: number; locked: boolean }

export default function Controlled() {
  const { t, lang } = useApp()
  const [rows, setRows] = useState<Row[] | null>(null)

  useEffect(() => { api<Row[]>('/controlled').then(setRows).catch(() => setRows([])) }, [])

  if (rows === null) return <div className="loading">...</div>

  return (
    <div className="card">
      <h2>{t('controlled')}</h2>
      <div className="muted" style={{ marginBottom: 10 }}>仅展示 COO 已终审放行的版本（只读受控）</div>
      <table>
        <thead><tr><th>COO</th><th>{t('packages')}</th><th>{t('version')}</th><th>{t('status')}</th><th>{t('attachment')}</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>{r.package_code}</td>
              <td>{r.package_name}</td>
              <td>{r.version.version_no}</td>
              <td><span className="tag released">{STATUS_LABELS.released[lang]}</span></td>
              <td>{r.attachment_count}</td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={5} className="muted">{t('no_data')}</td></tr>}
        </tbody>
      </table>
    </div>
  )
}
