import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../store'
import { ROLE_LABELS } from '../i18n'

interface Dept { id: number; code: string; name_zh: string; name_en: string; name_th: string }
interface U { id: number; username: string; display_name: string; role: string; dept_id: number | null; status: string }

const ROLES = ['submitter', 'dept_reviewer', 'coo_reviewer', 'auditor', 'admin']

export default function Org() {
  const { t, lang } = useApp()
  const [depts, setDepts] = useState<Dept[]>([])
  const [users, setUsers] = useState<U[]>([])

  async function load() {
    const [d, u] = await Promise.all([api<Dept[]>('/org/departments'), api<U[]>('/org/users')])
    setDepts(d); setUsers(u)
  }
  useEffect(() => { load() }, [])

  const [code, setCode] = useState(''); const [nz, setNz] = useState(''); const [ne, setNe] = useState('')
  const [uname, setUname] = useState(''); const [disp, setDisp] = useState(''); const [role, setRole] = useState('submitter'); const [udept, setUdept] = useState<number | ''>(''); const [pwd, setPwd] = useState('user123')

  async function addDept(e: any) { e.preventDefault(); await api('/org/departments', { method: 'POST', body: JSON.stringify({ code, name_zh: nz, name_en: ne, name_th: nz }) }); setCode(''); setNz(''); setNe(''); load() }
  async function addUser(e: any) { e.preventDefault(); await api('/org/users', { method: 'POST', body: JSON.stringify({ username: uname, display_name: disp, role, dept_id: udept || null, password: pwd }) }); setUname(''); setDisp(''); load() }
  async function resetPwd(id: number) { await api(`/org/users/${id}/reset-password`, { method: 'POST' }); alert('已重置为 user123') }

  const deptName = (id: number | null) => depts.find((d) => d.id === id)?.name_zh || '-'

  return (
    <div className="grid cols-2">
      <div className="card">
        <h2>{t('departments')}</h2>
        <table>
          <tbody>{depts.map((d) => <tr key={d.id}><td>{d.code}</td><td>{d.name_zh}</td><td>{d.name_en}</td></tr>)}</tbody>
        </table>
        <form onSubmit={addDept} className="row" style={{ marginTop: 12 }}>
          <input placeholder="CODE" value={code} onChange={(e) => setCode(e.target.value)} />
          <input placeholder={t('packages') + 'ZH'} value={nz} onChange={(e) => setNz(e.target.value)} />
          <input placeholder="EN" value={ne} onChange={(e) => setNe(e.target.value)} />
          <button className="btn btn-sm">{t('create')}</button>
        </form>
      </div>

      <div className="card">
        <h2>{t('users')}</h2>
        <table>
          <thead><tr><th>{t('username')}</th><th>{t('role')}</th><th>{t('dept')}</th><th></th></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.display_name || u.username}</td>
                <td>{ROLE_LABELS[u.role]?.[lang]}</td>
                <td>{deptName(u.dept_id)}</td>
                <td><button className="btn-ghost btn-sm" onClick={() => resetPwd(u.id)}>{t('reset_pwd')}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <form onSubmit={addUser} className="row" style={{ marginTop: 12, flexWrap: 'wrap' }}>
          <input placeholder={t('username')} value={uname} onChange={(e) => setUname(e.target.value)} />
          <input placeholder={t('display_name')} value={disp} onChange={(e) => setDisp(e.target.value)} />
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]?.[lang]}</option>)}
          </select>
          <select value={String(udept)} onChange={(e) => setUdept(e.target.value === '' ? '' : Number(e.target.value))}>
            <option value="">-</option>
            {depts.map((d) => <option key={d.id} value={d.id}>{d.name_zh}</option>)}
          </select>
          <input placeholder={t('password')} value={pwd} onChange={(e) => setPwd(e.target.value)} style={{ width: 110 }} />
          <button className="btn btn-sm">{t('create')}</button>
        </form>
      </div>
    </div>
  )
}
