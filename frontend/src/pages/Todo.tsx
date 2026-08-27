import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { App, Card, Empty, Table, Typography, Tag } from 'antd'
import { ArrowRightOutlined } from '@ant-design/icons'
import { errMessage } from '@/api/client'
import { todo } from '@/api/endpoints'
import { useAuth } from '@/store/AuthContext'
import { useI18n } from '@/i18n'
import StatusTag from '@/components/StatusTag'
import PageHeader from '@/components/PageHeader'
import ReviewSteps from '@/components/ReviewSteps'
import RowActions, { ActionButton } from '@/components/RowActions'
import { ELLIPSIS, actionWidth } from '@/utils/table'
import { formatTime } from '@/utils/format'
import type { TodoItem } from '@/types'

export default function Todo() {
  const { t } = useI18n()
  const { user } = useAuth()
  const { message } = App.useApp()
  const nav = useNavigate()
  const [rows, setRows] = useState<TodoItem[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    // 失败要提示：空列表会被误读为"没有待办",掩盖真正的加载失败
    todo.list().then(setRows)
      .catch((e) => { setRows([]); message.error(errMessage(e)) })
      .finally(() => setLoading(false))
  }, [message])
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
        // 列宽之和；不够宽时整表横向滚动，列宽不被挤压，字段就不会折行
        scroll={{ x: 1410 + actionWidth(1) }}
        columns={[
          { title: 'COO', dataIndex: 'package_code', width: 90 },
          { title: t('packages'), dataIndex: 'package_name', width: 200, ellipsis: ELLIPSIS },
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
          {
            title: t('dept'), dataIndex: 'dept_name', width: 150,
            // 标出"责任部门无在岗审核人"：这类条目原本落在所有人待办之外，
            // 现由 COO/管理员兜底显示；不标注的话它看起来就是一条普通待审，
            // 兜底的人不会意识到部门那一环已经没人了
            render: (v: string, r) => (
              <>
                {v || '-'}
                {r.no_reviewer && <><br /><Tag color="volcano">{t('no_reviewer')}</Tag></>}
              </>
            ),
          },
          { title: t('owner'), dataIndex: 'owner_name', width: 110, render: (v: string) => v || '-' },
          {
            title: t('due_date'), dataIndex: 'due_date', width: 120,
            render: (v: string, r) => (v
              ? (r.overdue
                ? <Typography.Text type="danger" strong>{v}（{t('overdue')}）</Typography.Text>
                : v)
              : '-'),
          },
          { title: t('attachment'), width: 90, render: (_, r) => r.attachments },
          { title: t('reject_reason'), dataIndex: 'reject_reason', width: 200, ellipsis: ELLIPSIS, render: (v: string) => (v ? <Typography.Text type="danger">{v}</Typography.Text> : '-') },
          { title: t('submit_time'), dataIndex: 'submitted_at', width: 170, render: (v: string) => (v ? formatTime(v) : '-') },
          {
            title: t('actions'), key: 'act', width: actionWidth(1), fixed: 'right',
            render: (_, r) => (
              <RowActions>
                {/* 文案随角色变化（整改 / 去审核 / 去终审），放进悬浮提示 */}
                <ActionButton label={actionLabel(r)} icon={<ArrowRightOutlined />}
                  onClick={() => nav(r.kind === 'order' && r.order_id ? `/orders/${r.order_id}` : `/packages/${r.package_id}`)} />
              </RowActions>
            ),
          },
        ]}
      />
      </Card>
    </>
  )
}