import { useEffect, useState } from 'react'
import { Card, Table, Tag, Typography } from 'antd'
import { LockOutlined } from '@ant-design/icons'
import { controlled } from '@/api/endpoints'
import { useI18n } from '@/i18n'
import type { ControlledItem } from '@/types'

export default function Controlled() {
  const { t } = useI18n()
  const [rows, setRows] = useState<ControlledItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    controlled.list().then(setRows).catch(() => setRows([])).finally(() => setLoading(false))
  }, [])

  return (
    <Card
      variant="borderless"
      title={<span><LockOutlined /> {t('controlled')}</span>}
      extra={<Typography.Text type="secondary">仅展示 COO 已终审放行的版本（只读受控）</Typography.Text>}
    >
      <Table
        rowKey={(_, i) => String(i)}
        loading={loading}
        dataSource={rows}
        pagination={{ pageSize: 10 }}
        columns={[
          { title: 'COO', dataIndex: 'package_code', width: 90 },
          { title: t('packages'), dataIndex: 'package_name' },
          { title: t('version'), dataIndex: ['version', 'version_no'], width: 90 },
          { title: t('status'), width: 110, render: () => <Tag color="green">{t('released')}</Tag> },
          { title: t('attachment'), dataIndex: 'attachment_count', width: 90 },
          { title: '', key: 'lock', width: 70, render: () => <Tag color="green"><LockOutlined /></Tag> },
        ]}
      />
    </Card>
  )
}
