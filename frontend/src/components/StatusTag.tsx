import { Tag } from 'antd'
import { STATUS_LABELS } from '@/i18n/messages'
import { useI18n } from '@/i18n'
import type { Lang } from '@/types'

const COLOR: Record<string, string> = {
  draft: 'default',
  pending_dept: 'gold',
  pending_coo: 'orange',
  released: 'green',
  rejected: 'red',
  none: 'default',
}

export default function StatusTag({ status }: { status: string }) {
  const { lang } = useI18n()
  const color = COLOR[status] ?? 'default'
  const label = (STATUS_LABELS[status]?.[lang as Lang] ?? status) as string
  return <Tag color={color}>{label}</Tag>
}
