import { useEffect, useState } from 'react'
import { App, Button, Card, Select, Space, Table } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
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
  const [loading, setLoading] = useState(true)

  const load = (d?: string) => {
    setLoading(true)
    audit.list(d ? { domain: d } : undefined).then(setLogs).catch(() => setLogs([])).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

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

  const canExport = user?.role === 'coo_reviewer' || user?.role === 'admin'

  return (
    <>
      <PageHeader
        title={t('audit')}
        desc={t('audit_desc')}
        extra={
          <Space>
            <Select allowClear placeholder={t('status')} style={{ width: 160 }} value={domain} onChange={(v) => { setDomain(v); load(v) }}
              options={DOMAINS.map((d) => ({ label: d, value: d }))} />
            {canExport && <Button icon={<DownloadOutlined />} onClick={exportCsv}>{t('export_csv')}</Button>}
          </Space>
        }
      />
      <Card variant="borderless" className="coo-card">
      <Table
        rowKey="id"
        loading={loading}
        dataSource={logs}
        pagination={{ pageSize: 15 }}
        columns={[
          { title: '时间', dataIndex: 'created_at', width: 170, render: (v: string) => formatTime(v) },
          { title: '域.动作', render: (_, r) => `${r.event_domain}.${r.action}`, width: 200 },
          { title: '操作人', dataIndex: 'actor_name', width: 120 },
          { title: 'IP', dataIndex: 'ip', width: 130 },
          { title: '目标', dataIndex: 'target' },
          { title: '说明', dataIndex: 'detail' },
        ]}
      />
      </Card>
    </>
  )
}
