import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Badge, Button, Dropdown, Empty, List, Typography } from 'antd'
import { BellOutlined, CheckOutlined } from '@ant-design/icons'
import { notifications } from '@/api/endpoints'
import { useI18n } from '@/i18n'
import { formatTime } from '@/utils/format'
import type { NotificationItem } from '@/types'

export default function NotificationBell() {
  const { t } = useI18n()
  const nav = useNavigate()
  const [unread, setUnread] = useState(0)
  const [items, setItems] = useState<NotificationItem[]>([])
  const timer = useRef<number | undefined>(undefined)

  const load = async () => {
    try {
      const d = await notifications.list(20)
      setUnread(d.unread)
      setItems(d.items)
    } catch {
      /* 网络/登录态异常时静默 */
    }
  }

  useEffect(() => {
    load()
    timer.current = window.setInterval(load, 30000)
    return () => window.clearInterval(timer.current)
  }, [])

  const markAll = async () => {
    await notifications.markAllRead()
    setUnread(0)
    setItems((prev) => prev.map((n) => ({ ...n, is_read: true })))
  }

  const openItem = (n: NotificationItem) => {
    if (!n.is_read) {
      notifications.markRead(n.id)
      setUnread((u) => Math.max(0, u - 1))
      setItems((prev) => prev.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)))
    }
    if (n.link) nav(n.link)
  }

  return (
    <Dropdown
      trigger={['click']}
      placement="bottomRight"
      dropdownRender={() => (
        <div style={{
          width: 380, background: '#fff', borderRadius: 12,
          boxShadow: '0 6px 24px rgba(11,37,69,0.14)', border: '1px solid #e6ebf2', overflow: 'hidden',
        }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '10px 14px', borderBottom: '1px solid #f0f3f8',
          }}>
            <Typography.Text strong>{t('notifications')}</Typography.Text>
            {unread > 0 && (
              <Button size="small" type="link" icon={<CheckOutlined />} onClick={markAll}>
                {t('mark_all_read')}
              </Button>
            )}
          </div>
          {items.length === 0
            ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={t('no_notifications')}
                style={{ padding: 24 }}
              />
            )
            : (
              <List
                dataSource={items.slice(0, 10)}
                renderItem={(n) => (
                  <List.Item
                    onClick={() => openItem(n)}
                    style={{
                      padding: '10px 14px', cursor: 'pointer',
                      background: n.is_read ? '#fff' : '#f0f6ff',
                      borderBottom: '1px solid #f5f7fa',
                    }}
                  >
                    <List.Item.Meta
                      title={
                        <span style={{
                          fontSize: 13, fontWeight: n.is_read ? 400 : 600,
                          color: n.is_read ? '#5c6b82' : '#14233c',
                        }}>{n.title}</span>
                      }
                      description={
                        <span style={{ fontSize: 12, color: '#8a97a8' }}>
                          {n.body ? `${n.body} · ` : ''}{formatTime(n.created_at)}
                        </span>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
        </div>
      )}
    >
      <Badge count={unread} size="small" offset={[-2, 2]}>
        <span style={{ fontSize: 18, cursor: 'pointer', color: '#14233c', display: 'inline-flex', padding: 4 }}>
          <BellOutlined />
        </span>
      </Badge>
    </Dropdown>
  )
}
