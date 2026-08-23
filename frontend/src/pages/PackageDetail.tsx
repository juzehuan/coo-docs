import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { App, Button, Card, Descriptions, Divider, Space, Tabs, Tag, Typography } from 'antd'
import { ArrowLeftOutlined, PlusOutlined, SendOutlined, UndoOutlined } from '@ant-design/icons'
import { errMessage } from '@/api/client'
import { packages } from '@/api/endpoints'
import { useAuth } from '@/store/AuthContext'
import { useI18n } from '@/i18n'
import StatusTag from '@/components/StatusTag'
import PageHeader from '@/components/PageHeader'
import ReviewSteps from '@/components/ReviewSteps'
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
  const [busy, setBusy] = useState(false)
  // ref 而非 state：state 要等重渲染才生效，同一批次内的连点可能全都读到旧值
  const busyRef = useRef(false)

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
  const canReviewDept = ver && user!.role === 'dept_reviewer' && pkg.dept_id != null && pkg.dept_id === user!.dept_id && ver.status === 'pending_dept'
  const canReviewCoo = ver && (user!.role === 'coo_reviewer' || user!.role === 'admin') && ver.status === 'pending_coo'
  const canWithdraw = ver && !!(user!.role === 'admin' || ownerOk) &&
    (ver.status === 'pending_dept' || ver.status === 'pending_coo')

  // 统一补齐错误提示：原先失败时静默无反馈（如"请先上传至少一个附件""当前状态不可提交"）
  // busy 防重：OrderDetail 的同名函数早有此保护，这里此前遗漏——而「发起新版本」
  // 恰恰不是幂等操作，实测连点三次真的创建了 V1.0/V1.1/V1.2 三个版本。
  async function run(fn: () => Promise<unknown>, okMsg: string) {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    try {
      await fn()
      message.success(okMsg)
      load()
    } catch (e) {
      message.error(errMessage(e))
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  const newVersion = () => run(() => packages.createVersion(pkg!.id, ''), t('new_version'))
  function submitVersion() {
    if (!ver) return
    modal.confirm({ title: t('submit'), content: t('submit_confirm'),
      onOk: () => run(() => packages.submit(pkg!.id, ver.id), t('submit_success')) })
  }
  function withdrawVersion() {
    if (!ver) return
    modal.confirm({ title: t('withdraw'), content: t('withdraw_confirm'),
      onOk: () => run(() => packages.withdraw(pkg!.id, ver.id), t('withdraw_success')) })
  }

  return (
    <div>
      <Button icon={<ArrowLeftOutlined />} onClick={() => nav('/packages')} style={{ marginBottom: 12 }}>{t('back')}</Button>

      <PageHeader
        title={`${pkg.code} · ${lang === 'en' ? pkg.name_en : lang === 'th' ? pkg.name_th : pkg.name_zh}`}
        desc={pkg.review_focus ? `${t('review_focus')}：${pkg.review_focus}` : undefined}
        extra={<Space>
          <Button icon={<PlusOutlined />} onClick={newVersion} loading={busy} disabled={busy}>{t('new_version')}</Button>
          {canWithdraw && <Button danger icon={<UndoOutlined />} onClick={withdrawVersion}>{t('withdraw')}</Button>}
          {ver && canEdit && ver.attachments.length > 0 && <Button type="primary" icon={<SendOutlined />} onClick={submitVersion}>{t('submit')}</Button>}
        </Space>}
      />

      <Card variant="borderless" className="coo-card">
        <Descriptions column={2} size="small">
          <Descriptions.Item label="COO">{pkg.code}</Descriptions.Item>
          <Descriptions.Item label={t('required')}>{pkg.required ? t('required') : '-'}</Descriptions.Item>
          <Descriptions.Item label={t('review_focus')} span={2}>{pkg.review_focus || '-'}</Descriptions.Item>
          <Descriptions.Item label={t('due_date')}>{pkg.due_date || '-'}</Descriptions.Item>
          <Descriptions.Item label={t('status')}>{ver ? <StatusTag status={ver.status} /> : '-'}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card variant="borderless" className="coo-card" style={{ marginTop: 16 }} title={t('version')}>
        <Tabs
          activeKey={String(ver?.id ?? '')}
          onChange={(k) => setActiveVid(k)}
          items={pkg.versions.map((v) => ({
            key: String(v.id),
            label: <span>{v.version_no} <StatusTag status={v.status} /></span>,
            children: (
              <div>
                <ReviewSteps status={v.status} />
                <Descriptions size="small" column={3} style={{ marginTop: 12, marginBottom: 12 }}>
                  <Descriptions.Item label={t('change_note')}>{v.change_note || '-'}</Descriptions.Item>
                  <Descriptions.Item label={t('submit_time')}>{formatTime(v.submitted_at)}</Descriptions.Item>
                  <Descriptions.Item label={t('locked')}>{v.locked ? <Tag className="coo-tag" style={{ background: '#eaf2ec', color: '#2f6b4a', border: 'none' }}>✓</Tag> : '-'}</Descriptions.Item>
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
