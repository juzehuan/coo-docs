import { Tag } from 'antd'
import { ROLE_LABELS } from '@/i18n/messages'
import { useI18n } from '@/i18n'
import type { Lang, Role } from '@/types'

const COLOR: Record<string, string> = {
  submitter: 'blue',
  dept_reviewer: 'cyan',
  coo_reviewer: 'geekblue',
  auditor: 'purple',
  admin: 'volcano',
}

export default function RoleTag({ role }: { role: string }) {
  const { lang } = useI18n()
  const color = COLOR[role] ?? 'default'
  const label = (ROLE_LABELS[role as Role]?.[lang as Lang] ?? role) as string
  return <Tag color={color}>{label}</Tag>
}
