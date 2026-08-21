import { Tag } from 'antd'
import { ROLE_LABELS } from '@/i18n/messages'
import { useI18n } from '@/i18n'
import type { Lang, Role } from '@/types'

// 角色徽章：纯色圆点 + 浅色胶囊背景，暖色调档案风。
const STYLE: Record<string, { bg: string; fg: string; dot: string }> = {
  submitter:    { bg: '#e9eff8', fg: '#1f5fa8', dot: '#2f7fd6' },
  dept_reviewer:{ bg: '#eaf2ec', fg: '#2f6b4a', dot: '#3f7d5c' },
  coo_reviewer: { bg: '#f5ead2', fg: '#8a6d2f', dot: '#a8833c' },
  auditor:      { bg: '#ede9f6', fg: '#5b4b8f', dot: '#7560b8' },
  admin:        { bg: '#f9ece9', fg: '#9c4134', dot: '#b04a3a' },
}

export default function RoleTag({ role }: { role: string }) {
  const { lang } = useI18n()
  const s = STYLE[role] ?? { bg: '#f2efe6', fg: '#7a7468', dot: '#a49e8c' }
  const label = (ROLE_LABELS[role as Role]?.[lang as Lang] ?? role) as string
  return (
    <Tag className="coo-tag" style={{ background: s.bg, color: s.fg, border: 'none' }}>
      <span className="coo-dot" style={{ background: s.dot }} />
      {label}
    </Tag>
  )
}
