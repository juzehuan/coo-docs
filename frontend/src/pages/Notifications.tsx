import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { App, Button, Card, Empty, List, Tag, Typography } from 'antd'
import { CheckOutlined } from '@ant-design/icons'
import { errMessage } from '@/api/client'
import { notifications } from '@/api/endpoints'
import { useI18n } from '@/i18n'
import { useSubmit } from '@/hooks/useSubmit'
import { formatTime } from '@/utils/format'
import PageHeader from '@/components/PageHeader'
import type { NotificationItem } from '@/types'

const PAGE_SIZE = 20

/** 只允许跳转站内相对路径（与 NotificationBell 同一规则）。 */
function isSafeInternalPath(link: string | null | undefined): link is string {
  if (!link) return false
  return /^\/(?!\/)[\w\-/]*$/.test(link)
}

/**
 * 通知中心。
 *
 * 铃铛下拉只渲染前 10 条且没有任何"查看更多"入口：实测某部门审核人有 140 条
 * 未读，角标显示 99+，点开却只能看到 10 条，其余 130 条待审通知在界面上
 * 完全无法触达——而通知正是跳转到待办订单的入口，看不到就等于漏办。
 */
export default function Notifications() {
  const { t } = useI18n()
  const nav = useNavigate()
  const { message } = App.useApp()
  const { loading: marking, run: markRun } = useSubmit()
  const [items, setItems] = useState<NotificationItem[]>([])
  const [total, setTotal] = useState(0)
  const [unread, setUnread] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async (p: number) => {
    setLoading(true)
    try {
      const d = await notifications.list(PAGE_SIZE, (p - 1) * PAGE_SIZE)
      setItems(d.items); setTotal(d.total); setUnread(d.unread)
    } catch (e) {
      // 静默失败会让用户以为"没有通知"，与真的没有通知无法区分
      setItems([]); message.error(errMessage(e))
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => { load(page) }, [load, page])

  async function open(n: NotificationItem) {
    if (!n.is_read) {
      try {
        await notifications.markRead(n.id)
        setItems((prev) => prev.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)))
        setUnread((u) => Math.max(0, u - 1))
      } catch (e) {
        message.error(errMessage(e))   // 标记失败要说清楚，否则界面显示已读、服务端仍未读
      }
    }
    if (isSafeInternalPath(n.link)) nav(n.link)
  }

  async function markAll() {
    if (await markRun(() => notifications.markAllRead(), t('mark_all_read'))) load(page)
  }

  return (
    <>
      <PageHeader
        title={t('notifications')}
        desc={t('notifications_desc')}
        extra={unread > 0 && (
          <Button icon={<CheckOutlined />} loading={marking} onClick={markAll}>{t('mark_all_read')}</Button>
        )}
      />
      <Card variant="borderless" className="coo-card">
        <List
          loading={loading}
          dataSource={items}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('no_notifications')} /> }}
          pagination={total > PAGE_SIZE ? {
            current: page, pageSize: PAGE_SIZE, total, showSizeChanger: false,
            onChange: setPage,
            showTotal: (n) => t('audit_total').replace('{total}', String(n)),
          } : false}
          renderItem={(n) => (
            <List.Item
              onClick={() => open(n)}
              style={{ cursor: 'pointer', background: n.is_read ? undefined : '#faf0dc', padding: '12px 16px' }}
            >
              <List.Item.Meta
                title={
                  <span style={{ fontWeight: n.is_read ? 400 : 600, color: n.is_read ? '#6f685a' : '#16263f' }}>
                    {!n.is_read && <Tag className="coo-tag" style={{ background: '#b97a1e', color: '#fff', border: 'none', marginRight: 8 }}>{t('unread')}</Tag>}
                    {n.title}
                  </span>
                }
                description={
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {n.body ? `${n.body} · ` : ''}{formatTime(n.created_at)}
                  </Typography.Text>
                }
              />
            </List.Item>
          )}
        />
      </Card>
    </>
  )
}
