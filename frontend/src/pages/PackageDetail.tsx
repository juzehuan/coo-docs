import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { App, Button, Card, Descriptions, Divider, Space, Tabs, Tag, Typography } from 'antd'
import { ArrowLeftOutlined, PlusOutlined, SendOutlined, UndoOutlined } from '@ant-design/icons'
import { packages } from '@/api/endpoints'
import { useAuth } from '@/store/AuthContext'
import { useI18n } from '@/i18n'
import StatusTag from '@/components/StatusTag'
import AttachmentList from '@/components/AttachmentList'
import ReviewPanel from '@/components/ReviewPanel'
import { formatTime } from '@/utils/format'
import type { PackageDetailResp, Version } from '@/types'

export default function PackageDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const { t, lang } = useI18n()
  const nav = useNavigate()
  const { message, modal } = App.useApp()
  const [pkg, setPkg] = useState<PackageDetailResp | null>(null)
  const [activeVid, setActiveVid] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    if (!id) return
    setLoading(true)
    packages.detail(id).then((p) => {
      setPkg(p)
      setActiveVid(p.versions[0]?.id ?? null)
    }).catch(() => setPkg(null)).finally(() => setLoading(false))
  }, [id])

  useEffect(() => { load() }, [load])

  if (loading) return <Card variant="borderless" loading />
  if (!pkg) return <Card variant="borderless">{t('no_data')}</Card>

  const ver: Version | undefined = pkg.versions.find((v) => v.id === activeVid) || pkg.versions[0]

  // 权限：管理员/审核人/COO 可编辑任意；提交人仅本人负责包
  const isStaff = user!.role === 'admin' || user!.role === 'dept_reviewer' || user!.role === 'coo_reviewer'
  const ownerOk = user!.role === 'submitter' && pkg.owner_user_id === user!.id
  const canEdit = ver && (isStaff || ownerOk) && ver.status !== 'released'
  const canReviewDept = ver && user!.role === 'dept_reviewer' && ver.status === 'pending_dept'
  const canReviewCoo = ver && (user!.role === 'coo_reviewer' || user!.role === 'admin') && ver.status === 'pending_coo'
  const canWithdraw = ver && !!(user!.role === 'admin' || ownerOk) &&
    (ver.status === 'pending_dept' || ver.status === 'pending_coo')

  async function newVersion() {
    await packages.createVersion(pkg!.id, '')
    message.success(t('new_version'))
    load()
  }
  function submitVersion() {
    if (!ver) return
    modal.confirm({ title: t('submit'), content: t('submit_confirm'), onOk: async () => { await packages.submit(pkg!.id, ver.id); message.success(t('submit_success')); load() } })
  }
  function withdrawVersion() {
    if (!ver) return
    modal.confirm({ title: t('withdraw'), content: t('withdraw_confirm'), onOk: async () => { await packages.withdraw(pkg!.id, ver.id); message.success(t('withdraw_success')); load() } })
  }

  return (
    <div>
      <Space style={{ marginBottom: 12 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => nav('/packages')}>{t('back')}</Button>
      </Space>

      <Card variant="borderless">
        <Space style={{ justifyContent: 'space-between', width: '100%' }}>
          <Typography.Title level={4} style={{ margin: 0 }}>{pkg.code} · {lang === 'en' ? pkg.name_en : lang === 'th' ? pkg.name_th : pkg.name_zh}</Typography.Title>
          <Space>
            <Button icon={<PlusOutlined />} onClick={newVersion}>{t('new_version')}</Button>
            {canWithdraw && <Button danger icon={<UndoOutlined />} onClick={withdrawVersion}>{t('withdraw')}</Button>}
            {ver && canEdit && ver.attachments.length > 0 && <Button type="primary" icon={<SendOutlined />} onClick={submitVersion}>{t('submit')}</Button>}
          </Space>
        </Space>
        <Descriptions column={2} size="small" style={{ marginTop: 12 }}>
          <Descriptions.Item label="COO">{pkg.code}</Descriptions.Item>
          <Descriptions.Item label={t('required')}>{pkg.required ? t('required') : '-'}</Descriptions.Item>
          <Descriptions.Item label={t('review_focus')} span={2}>{pkg.review_focus || '-'}</Descriptions.Item>
          <Descriptions.Item label={t('due_date')}>{pkg.due_date || '-'}</Descriptions.Item>
          <Descriptions.Item label={t('status')}>{ver ? <StatusTag status={ver.status} /> : '-'}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card variant="borderless" style={{ marginTop: 16 }} title={t('version')}>
        <Tabs
          activeKey={String(ver?.id ?? '')}
          onChange={(k) => setActiveVid(k)}
          items={pkg.versions.map((v) => ({
            key: String(v.id),
            label: <span>{v.version_no} <StatusTag status={v.status} /></span>,
            children: (
              <div>
                <Descriptions size="small" column={3} style={{ marginBottom: 12 }}>
                  <Descriptions.Item label="变更">{v.change_note || '-'}</Descriptions.Item>
                  <Descriptions.Item label="提交">{formatTime(v.submitted_at)}</Descriptions.Item>
                  <Descriptions.Item label="锁定">{v.locked ? <Tag color="green">✓</Tag> : '-'}</Descriptions.Item>
                </Descriptions>
                <AttachmentList pkgId={pkg.id} version={v} canEdit={!!canEdit} onChanged={load} />
                <Divider />
                {canReviewDept && <ReviewPanel pkgId={pkg.id} version={v} level="dept" onDone={load} />}
                {canReviewCoo && <ReviewPanel pkgId={pkg.id} version={v} level="coo" onDone={load} />}
                {v.status === 'rejected' && (v.dept_reject_reason || v.coo_reject_reason) && (
                  <Card variant="borderless" style={{ background: '#fff1f0', borderColor: '#ffccc7' }}>
                    <Typography.Text type="danger">{t('reject_reason')}：{v.dept_reject_reason || v.coo_reject_reason}</Typography.Text>
                  </Card>
                )}
              </div>
            ),
          }))}
        />
      </Card>
    </div>
  )
}
