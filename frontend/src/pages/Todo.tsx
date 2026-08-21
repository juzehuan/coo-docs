import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Empty, Space, Table, Typography } from 'antd'
import { ArrowRightOutlined } from '@ant-design/icons'
import { todo } from '@/api/endpoints'
import { useAuth } from '@/store/AuthContext'
import { useI18n } from '@/i18n'
import StatusTag from '@/components/StatusTag'
import PageHeader from '@/components/PageHeader'
import ReviewSteps from '@/components/ReviewSteps'
import { formatTime } from '@/utils/format'
import type { TodoItem } from '@/types'

export default function Todo() {
  const { t } = useI18n()
  const { user } = useAuth()
  const nav = useNavigate()
  const [rows, setRows] = useState<TodoItem[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    todo.list().then(setRows).catch(() => setRows([])).finally(() => setLoading(false))
  }, [])
  useEffect(() => { load() }, [load])

  // 按钮文案：提交人→整改，部门审核→去审核，COO/管理员→去终审
  const actionLabel = (r: TodoItem) => {
    if (user?.role === 'submitter') return t('go_rework')
    if (user?.role === 'dept_reviewer') return t('go_review')
    return r.status === 'pending_coo' ? t('go_final') : t('go_review')
  }

  return (
    <>
      <PageHeader title={t('todo')} desc={t('todo_desc')} />
      <Card variant="borderless" className="coo-card">
      <Table
        rowKey={(r) => `${r.kind}-${r.package_id}`}
        loading={loading}
        dataSource={rows}
        locale={{ emptyText: <Empty description={t('todo_empty')} image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
        pagination={{ defaultPageSize: 10, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100] }}
        columns={[
          { title: 'COO', dataIndex: 'package_code', width: 90 },
          { title: t('packages'), dataIndex: 'package_name', ellipsis: true },
          { title: t('version'), dataIndex: 'version_no', width: 110, render: (v: string) => v || '-' },
          {
            title: t('status'), width: 170,
            render: (_, r) => (
              <>
                <StatusTag status={r.status} />
                <br />
                <ReviewSteps status={r.status} compact />
              </>
            ),
          },
          { title: t('dept'), dataIndex: 'dept_name', width: 120, render: (v: string) => v || '-' },
          { title: t('owner'), dataIndex: 'owner_name', width: 110, render: (v: string) => v || '-' },
          { title: t('attachment'), width: 90, render: (_, r) => r.attachments },
          { title: t('reject_reason'), dataIndex: 'reject_reason', ellipsis: true, render: (v: string) => (v ? <Typography.Text type="danger">{v}</Typography.Text> : '-') },
          { title: t('submit_time'), dataIndex: 'submitted_at', width: 170, render: (v: string) => (v ? formatTime(v) : '-') },
          {
            title: '', key: 'act', width: 100,
            render: (_, r) => (
              <Button size="small" type="primary" ghost icon={<ArrowRightOutlined />} onClick={() => nav(r.kind === 'order' && r.order_id ? `/orders/${r.order_id}` : `/packages/${r.package_id}`)}>
                {actionLabel(r)}
              </Button>
            ),
          },
        ]}
      />
      </Card>
    </>
  )
}