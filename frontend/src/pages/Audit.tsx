import { useEffect, useState } from 'react'
import { App, Button, Card, DatePicker, Input, Select, Space, Table } from 'antd'
import { DownloadOutlined, SearchOutlined } from '@ant-design/icons'
import type { Dayjs } from 'dayjs'
import { errMessage } from '@/api/client'
import { audit } from '@/api/endpoints'
import { useAuth } from '@/store/AuthContext'
import { useI18n } from '@/i18n'
import { formatTime } from '@/utils/format'
import PageHeader from '@/components/PageHeader'
import type { AuditLog } from '@/types'

const DOMAINS = ['auth', 'package', 'attachment', 'review', 'version', 'nas', 'export', 'org']

export default function Audit() {
  const { t } = useI18n()
  const { user } = useAuth()
  const { message } = App.useApp()
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [domain, setDomain] = useState<string | undefined>()
  const [actor, setActor] = useState('')
  const [target, setTarget] = useState('')
  const [range, setRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const [loading, setLoading] = useState(true)

  // d：undefined = 用当前 state；null = 明确清除（Select 的 allowClear 触发时 state 尚未更新）
  const load = (d?: string | null) => {
    setLoading(true)
    audit.list({
      limit: 1000,
      domain: d === null ? undefined : (d ?? domain),
      actor: actor.trim() || undefined,
      target: target.trim() || undefined,
      start: range?.[0]?.format('YYYY-MM-DD') || undefined,
      end: range?.[1]?.format('YYYY-MM-DD') || undefined,
    }).then(setLogs)
      .catch((e) => { setLogs([]); message.error(errMessage(e)) })   // 空列表不等于无日志，失败要说清楚
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  async function exportCsv() {
    try {
      const blob = await audit.exportCsv()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'audit_logs.csv'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e: any) {
      message.error(e?.message || 'export failed')
    }
  }

  const canExport = user?.role === 'auditor' || user?.role === 'admin'

  return (
    <>
      <PageHeader
        title={t('audit')}
        desc={t('audit_desc')}
        extra={
          <Space wrap>
            <Input allowClear placeholder={t('operator')} style={{ width: 130 }} value={actor}
              onChange={(e) => setActor(e.target.value)} onPressEnter={() => load()} />
            <Input allowClear placeholder={t('target')} style={{ width: 170 }} value={target}
              onChange={(e) => setTarget(e.target.value)} onPressEnter={() => load()} />
            <DatePicker.RangePicker value={range} onChange={(v) => setRange(v)} allowEmpty={[true, true]} />
            <Select allowClear placeholder={t('domain_action')} style={{ width: 140 }} value={domain} onChange={(v) => { setDomain(v); load(v ?? null) }}
              options={DOMAINS.map((d) => ({ label: d, value: d }))} />
            <Button type="primary" icon={<SearchOutlined />} onClick={() => load()}>{t('search')}</Button>
            {canExport && <Button icon={<DownloadOutlined />} onClick={exportCsv}>{t('export_csv')}</Button>}
          </Space>
        }
      />
      <Card variant="borderless" className="coo-card">
      <Table
        rowKey="id"
        loading={loading}
        dataSource={logs}
        pagination={{ defaultPageSize: 15, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100] }}
        columns={[
          { title: t('time'), dataIndex: 'created_at', width: 170, render: (v: string) => formatTime(v) },
          { title: t('domain_action'), render: (_, r) => `${r.event_domain}.${r.action}`, width: 200 },
          { title: t('operator'), dataIndex: 'actor_name', width: 120 },
          { title: t('ip'), dataIndex: 'ip', width: 130 },
          { title: t('target'), dataIndex: 'target' },
          { title: t('desc'), dataIndex: 'detail' },
        ]}
      />
      </Card>
    </>
  )
}
