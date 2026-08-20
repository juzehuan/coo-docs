import { Tag } from 'antd'
import { ROLE_LABELS } from '@/i18n/messages'
import { useI18n } from '@/i18n'
import type { Lang, Role } from '@/types'

// 角色徽章：纯色圆点 + 浅色胶囊背景。
const STYLE: Record<string, { bg: string; fg: string; dot: string }> = {
  submitter:    { bg: '#eaf1fb', fg: '#1f5fa8', dot: '#2f7fd6' },
  dept_reviewer:{ bg: '#e6f7f9', fg: '#0e7490', dot: '#2aa8c0' },
  coo_reviewer: { bg: '#eef0fb', fg: '#4f46e5', dot: '#6366f1' },
  auditor:      { bg: '#f5f0fb', fg: '#7c3aed', dot: '#a855f7' },
  admin:        { bg: '#fff1ee', fg: '#c2410c', dot: '#f97316' },
}

export default function RoleTag({ role }: { role: string }) {
  const { lang } = useI18n()
  const s = STYLE[role] ?? { bg: '#f1f4f9', fg: '#5a6b85', dot: '#93a2b7' }
  const label = (ROLE_LABELS[role as Role]?.[lang as Lang] ?? role) as string
  return (
    <Tag className="coo-tag" style={{ background: s.bg, color: s.fg, border: 'none' }}>
      <span className="coo-dot" style={{ background: s.dot }} />
      {label}
    </Tag>
  )
}