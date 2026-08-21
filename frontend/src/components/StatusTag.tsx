import { Tag } from 'antd'
import { STATUS_LABELS } from '@/i18n/messages'
import { useI18n } from '@/i18n'
import type { Lang } from '@/types'

// 每个状态：纯色圆点 + 浅色胶囊背景，暖色调档案风。
const STYLE: Record<string, { bg: string; fg: string; dot: string }> = {
  draft:       { bg: '#f2efe6', fg: '#7a7468', dot: '#a49e8c' },       // 草稿
  pending_dept:{ bg: '#faf0dc', fg: '#a67c1e', dot: '#c9a23c' },       // 待部门
  pending_coo: { bg: '#f5ead2', fg: '#8a6d2f', dot: '#a8833c' },       // 待COO
  released:    { bg: '#eaf2ec', fg: '#2f6b4a', dot: '#3f7d5c' },       // 已放行
  rejected:    { bg: '#f9ece9', fg: '#9c4134', dot: '#b04a3a' },       // 已退回
  withdrawn:   { bg: '#eee9df', fg: '#6b6355', dot: '#8f8777' },       // 已撤回
  active:      { bg: '#e9eff8', fg: '#1f5fa8', dot: '#2f7fd6' },       // 进行中
  completed:   { bg: '#eaf2ec', fg: '#2f6b4a', dot: '#3f7d5c' },       // 已完成
  closed:      { bg: '#f2efe6', fg: '#7a7468', dot: '#a49e8c' },       // 已关闭
  none:        { bg: '#f2efe6', fg: '#7a7468', dot: '#a49e8c' },
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
