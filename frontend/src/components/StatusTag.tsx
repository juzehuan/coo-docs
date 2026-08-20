import { Tag } from 'antd'
import { STATUS_LABELS } from '@/i18n/messages'
import { useI18n } from '@/i18n'
import type { Lang } from '@/types'

// 每个状态：纯色圆点 + 浅色胶囊背景，提升扫视可读性。
const STYLE: Record<string, { bg: string; fg: string; dot: string }> = {
  draft:       { bg: '#f1f4f9', fg: '#5a6b85', dot: '#93a2b7' },       // 草稿
  pending_dept:{ bg: '#fff7e6', fg: '#d48806', dot: '#faad14' },       // 待部门
  pending_coo: { bg: '#fff1e8', fg: '#d46b08', dot: '#ff8c3b' },       // 待COO
  released:    { bg: '#f0f9f4', fg: '#2f9e5f', dot: '#34b573' },       // 已放行
  rejected:    { bg: '#fff1f0', fg: '#cf4444', dot: '#f4504b' },       // 已退回
  active:      { bg: '#eaf1fb', fg: '#1f5fa8', dot: '#2f7fd6' },       // 进行中
  completed:   { bg: '#f0f9f4', fg: '#2f9e5f', dot: '#34b573' },       // 已完成
  closed:      { bg: '#f1f4f9', fg: '#5a6b85', dot: '#93a2b7' },       // 已关闭
  none:        { bg: '#f1f4f9', fg: '#5a6b85', dot: '#93a2b7' },
}

export default function StatusTag({ status }: { status: string }) {
  const { lang } = useI18n()
  const s = STYLE[status] ?? STYLE.none
  const label = (STATUS_LABELS[status]?.[lang as Lang] ?? status) as string
  return (
    <Tag className="coo-tag" style={{ background: s.bg, color: s.fg, border: 'none' }}>
      <span className="coo-dot" style={{ background: s.dot }} />
      {label}
    </Tag>
  )
}