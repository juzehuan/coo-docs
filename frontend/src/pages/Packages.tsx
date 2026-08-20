import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Input, Table } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import { packages } from '@/api/endpoints'
import { useI18n } from '@/i18n'
import StatusTag from '@/components/StatusTag'
import type { PackageRow } from '@/types'

export default function Packages() {
  const { t, lang } = useI18n()
  const nav = useNavigate()
  const [rows, setRows] = useState<PackageRow[]>([])
  const [kw, setKw] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    packages.list().then(setRows).catch(() => setRows([])).finally(() => setLoading(false))
  }, [])

  const data = rows.filter((r) =>
    (lang === 'en' ? r.name_en : lang === 'th' ? r.name_th : r.name_zh).toLowerCase().includes(kw.toLowerCase()) ||
    r.code.toLowerCase().includes(kw.toLowerCase()),
  )

  return (
    <Card variant="borderless" title={t('packages')} extra={<Input prefix={<SearchOutlined />} placeholder={t('packages')} value={kw} onChange={(e) => setKw(e.target.value)} style={{ width: 240 }} allowClear />}>
      <Table
        rowKey="id"
        loading={loading}
        dataSource={data}
        pagination={{ pageSize: 10 }}
        columns={[
          { title: 'COO', dataIndex: 'code', width: 90 },
          { title: t('packages'), render: (_, r) => lang === 'en' ? r.name_en || r.name_zh : lang === 'th' ? r.name_th || r.name_zh : r.name_zh },
          { title: t('version'), dataIndex: 'current_version', width: 90, render: (v: string) => v || '-' },
          { title: t('status'), dataIndex: 'current_status', width: 130, render: (s: string) => <StatusTag status={s} /> },
          { title: t('attachment'), dataIndex: 'attachment_count', width: 90 },
          { title: '', key: 'act', width: 80, render: (_, r) => <a onClick={() => nav(`/packages/${r.id}`)}>{t('detail')}</a> },
        ]}
      />
    </Card>
  )
}
