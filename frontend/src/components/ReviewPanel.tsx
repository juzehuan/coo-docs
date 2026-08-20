import { useState } from 'react'
import { App, Alert, Button, Input, Space, Tag, Typography } from 'antd'
import { CheckOutlined, CloseOutlined } from '@ant-design/icons'
import { packages } from '@/api/endpoints'
import { useI18n } from '@/i18n'
import type { Version } from '@/types'

interface Props {
  pkgId: string
  version: Version
  level: 'dept' | 'coo'
  onDone: () => void
}

export default function ReviewPanel({ pkgId, version, level, onDone }: Props) {
  const { t } = useI18n()
  const { message } = App.useApp()
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  const rejected = version.status === 'rejected'
  const rejectReason = level === 'dept' ? version.dept_reject_reason : version.coo_reject_reason

  async function act(decision: string) {
    setBusy(true)
    try {
      await packages.review(pkgId, version.id, decision, level, reason)
      message.success(decision === 'approve' ? t('approve') : t('reject'))
      setReason('')
      onDone()
    } catch (e: any) {
      message.error(e?.message || '操作失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ padding: 16, borderRadius: 8, background: level === 'dept' ? '#fffbeb' : '#eff6ff', border: `1px solid ${level === 'dept' ? '#fde68a' : '#bfdbfe'}` }}>
      <Space style={{ marginBottom: 10 }}>
        <Tag color={level === 'dept' ? 'gold' : 'geekblue'}>{level === 'dept' ? t('dept_review') : t('coo_review')}</Tag>
        {rejected && rejectReason && <Typography.Text type="danger">{t('reject_reason')}：{rejectReason}</Typography.Text>}
      </Space>
      {version.status === 'rejected' && !rejected && null}
      <Alert type="info" showIcon style={{ marginBottom: 10 }} message={`${level === 'dept' ? t('dept_review') : t('coo_review')} · ${version.version_no}`} />
      <Input.TextArea
        rows={3}
        placeholder={t('change_note')}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        style={{ marginBottom: 10 }}
      />
      <Space>
        <Button type="primary" icon={<CheckOutlined />} loading={busy} onClick={() => act('approve')}>{t('approve')}</Button>
        <Button danger icon={<CloseOutlined />} loading={busy} disabled={!reason.trim()} onClick={() => act('reject')}>{t('reject')}</Button>
      </Space>
    </div>
  )
}
