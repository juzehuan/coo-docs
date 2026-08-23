import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Badge, Button, Dropdown, Empty, List, Typography } from 'antd'
import { BellOutlined, CheckOutlined } from '@ant-design/icons'
import { notifications } from '@/api/endpoints'
import { useI18n } from '@/i18n'
import { formatTime } from '@/utils/format'
import type { NotificationItem } from '@/types'

/** 只允许跳转站内相对路径。
 *
 * 这是全站唯一以动态值为目标的导航（通知的 link 字段）。当前 link 均由后端硬编码
 * 生成（/orders/{id}、/packages/{id}），不含用户输入；此处仍做白名单校验，
 * 以免将来该字段变为可写时演变成开放重定向（react-router 的
 * GHSA-wrjc-x8rr-h8h6 正是反斜杠绕过导致的同类问题）。
 */
function isSafeInternalPath(link: string | null | undefined): link is string {
  if (!link) return false
  // 必须以单个 / 开头，且不含反斜杠、协议头或协议相对写法（//evil.com）
  return /^\/(?!\/)[\w\-/]*$/.test(link)
}

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
    if (isSafeInternalPath(n.link)) nav(n.link)
  }

  return (
    <Dropdown
      trigger={['click']}
      placement="bottomRight"
      dropdownRender={() => (
        <div style={{
          width: 380, background: '#fffdf7', borderRadius: 12,
          boxShadow: '0 6px 24px rgba(34,42,51,0.14)', border: '1px solid #e8e1d3', overflow: 'hidden',
        }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '10px 14px', borderBottom: '1px solid #e8e1d3',
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
                      background: n.is_read ? '#fffdf7' : '#faf0dc',
                      borderBottom: '1px solid #e8e1d3',
                    }}
                  >
                    <List.Item.Meta
                      title={
                        <span style={{
                          fontSize: 13, fontWeight: n.is_read ? 400 : 600,
                          color: n.is_read ? '#6f685a' : '#16263f',
                        }}>{n.title}</span>
                      }
                      description={
                        <span style={{ fontSize: 12, color: '#a49e8c' }}>
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
        <span style={{ fontSize: 18, cursor: 'pointer', color: '#16263f', display: 'inline-flex', padding: 4 }}>
          <BellOutlined />
        </span>
      </Badge>
    </Dropdown>
  )
}
