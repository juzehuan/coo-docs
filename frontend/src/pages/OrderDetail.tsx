import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { App, Button, Card, Descriptions, Form, Input, Modal, Select, Space, Table, Tag, Typography, Upload,
} from 'antd'
import { ArrowLeftOutlined, CheckOutlined, CloseOutlined, DeleteOutlined, DownloadOutlined, FileZipOutlined, InboxOutlined, PlusOutlined, SendOutlined, UndoOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { downloadFile } from '@/api/client'
import { orders, packages as pkgApi } from '@/api/endpoints'
import { useAuth } from '@/store/AuthContext'
import { useI18n } from '@/i18n'
import StatusTag from '@/components/StatusTag'
import ReviewSteps from '@/components/ReviewSteps'
import AttachmentPreview from '@/components/AttachmentPreview'
import PageHeader from '@/components/PageHeader'
import { formatTime } from '@/utils/format'
import type { OrderAttachment, OrderDetail as OrderDetailResp, OrderPackage, Package, User } from '@/types'

const { Dragger } = Upload

// ---------- 单包：附件 / 上传 / 提审 ----------
function RowAttachments({ orderId, op, user, onChanged }: {
  orderId: string; op: OrderPackage; user: User; onChanged: () => void
}) {
  const { t } = useI18n()
  const { message } = App.useApp()
  const [batchNo, setBatchNo] = useState('')
  const [uploading, setUploading] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState<{ url: string; name: string } | null>(null)

  const atts = op.attachments || []
  // 可编辑（上传/删附件/提交）：COO/管理员任意；部门审核人仅本部门实例；提交人仅本人负责实例
  const isStaff = user.role === 'admin' || user.role === 'coo_reviewer' ||
    (user.role === 'dept_reviewer' && op.package_dept_id != null && op.package_dept_id === user.dept_id)
  const ownerOk = user.role === 'submitter' && op.owner_user_id === user.id
  const canEdit = (isStaff || ownerOk) && op.status !== 'released' && !op.locked
  const canReviewDept = user.role === 'dept_reviewer' && op.status === 'pending_dept'
  const canReviewCoo = (user.role === 'coo_reviewer' || user.role === 'admin') && op.status === 'pending_coo'
  const canWithdraw = (user.role === 'admin' || ownerOk) &&
    (op.status === 'pending_dept' || op.status === 'pending_coo')

  async function withdraw() {
    await orders.withdraw(orderId, op.id); message.success(t('withdraw_success')); onChanged()
  }

  async function doReview(decision: string, level: string) {
    setBusy(true)
    try {
      await orders.review(orderId, op.id, decision, level, reason)
      message.success(decision === 'approve' ? t('approve') : t('reject'))
      setReason(''); onChanged()
    } catch (e: any) { message.error(e?.message || t('op_failed')) } finally { setBusy(false) }
  }
  async function submit() {
    await orders.submit(orderId, op.id); message.success(t('submit_success')); onChanged()
  }

  const columns: ColumnsType<OrderAttachment> = [
    { title: t('attachment'), dataIndex: 'original_name', render: (n, r) => (
      <a onClick={() => setPreview({ url: orders.attachmentUrl(orderId, op.id, r.id, true), name: r.original_name || r.file_name })}>{n}</a>
    ) },
    { title: 'MD5', dataIndex: 'md5', ellipsis: true, render: (v: string) => <Typography.Text copyable={{ text: v }} style={{ fontSize: 12 }}>{v.slice(0, 12)}…</Typography.Text> },
    { title: t('batch_no'), dataIndex: 'batch_no', render: (v: string) => v || '-' },
    { title: t('upload_time'), dataIndex: 'uploaded_at', width: 160, render: (v: string) => formatTime(v) },
    { title: '', key: 'act', width: 160, render: (_, r: OrderAttachment) => (
      <Space size={4}>
        <Button size="small" icon={<DownloadOutlined />} onClick={() => downloadFile(orders.attachmentUrl(orderId, op.id, r.id, false), r.original_name || r.file_name)}>{t('download')}</Button>
        {canEdit && <Button size="small" danger icon={<DeleteOutlined />} onClick={async () => { await orders.deleteAttachment(orderId, op.id, r.id); message.success(t('deleted')); onChanged() }}>{t('cancel')}</Button>}
      </Space>
    )},
  ]

  return (
    <div>
      <Table rowKey="id" size="small" pagination={false} columns={columns} dataSource={atts} locale={{ emptyText: t('no_data') }} />

      {canEdit && (
        <div style={{ marginTop: 8, padding: 12, background: '#faf6ec', border: '1px dashed #d8cdb0', borderRadius: 8 }}>
          <Space style={{ marginBottom: 8 }}>
            <Input addonBefore={t('batch_no')} value={batchNo} onChange={(e) => setBatchNo(e.target.value)} style={{ width: 220 }} />
            <Button type="primary" icon={<SendOutlined />} disabled={atts.length === 0} onClick={submit}>{t('submit')}</Button>
            {canWithdraw && (
              <Button danger icon={<UndoOutlined />} onClick={withdraw}>{t('withdraw')}</Button>
            )}
          </Space>
          <Dragger
            multiple showUploadList={false} beforeUpload={() => false} disabled={uploading}
            onChange={async (info) => {
              const files = info.fileList.map((f) => f.originFileObj as File).filter(Boolean)
              if (!files.length) return
              setUploading(true)
              try {
                await orders.uploadAttachments(orderId, op.id, files, batchNo)
                message.success(t('uploaded_n', { n: files.length })); setBatchNo(''); onChanged()
              } catch (e: any) { message.error(e?.message || t('upload_failed')) } finally { setUploading(false) }
            }}
          >
            <p className="ant-upload-drag-icon"><InboxOutlined /></p>
            <p className="ant-upload-text">{t('upload')}</p>
          </Dragger>
        </div>
      )}

      {(canReviewCoo || canReviewDept) && (
        <div style={{ marginTop: 12, padding: 12, borderRadius: 8, background: canReviewCoo ? '#eef3fa' : '#fbf2dd', border: `1px solid ${canReviewCoo ? '#c7d8ec' : '#e5cf9c'}` }}>
          <Tag className="coo-tag" style={{ background: canReviewCoo ? '#e9eff8' : '#faf0dc', color: canReviewCoo ? '#1f5fa8' : '#a67c1e', border: 'none' }}>{canReviewCoo ? t('coo_review') : t('dept_review')}</Tag>
          <Input.TextArea rows={2} placeholder={t('change_note')} value={reason} onChange={(e) => setReason(e.target.value)} style={{ margin: '8px 0' }} />
          <Space>
            <Button type="primary" size="small" icon={<CheckOutlined />} loading={busy} onClick={() => doReview('approve', canReviewCoo ? 'coo' : 'dept')}>{t('approve')}</Button>
            <Button danger size="small" icon={<CloseOutlined />} loading={busy} disabled={!reason.trim()} onClick={() => doReview('reject', canReviewCoo ? 'coo' : 'dept')}>{t('reject')}</Button>
          </Space>
        </div>
      )}

      <AttachmentPreview open={!!preview} url={preview?.url ?? ''} name={preview?.name ?? ''} onClose={() => setPreview(null)} />
    </div>
  )
}

// ---------- 订单详情页 ----------
export default function OrderDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const { t, lang } = useI18n()
  const nav = useNavigate()
  const { message, modal } = App.useApp()
  const [order, setOrder] = useState<OrderDetailResp | null>(null)
  const [templates, setTemplates] = useState<Package[]>([])
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()

  const load = useCallback(() => {
    if (!id) return
    setLoading(true)
    orders.detail(id)
      .then((o) => setOrder(o))
      .catch(() => setOrder(null))
      .finally(() => setLoading(false))
  }, [id])

  useEffect(() => {
    load()
    pkgApi.list().then((p) => setTemplates(p)).catch(() => setTemplates([]))
  }, [load])

  if (loading) return <Card variant="borderless" loading />
  if (!order) return <Card variant="borderless">{t('no_data')}</Card>

  const canExport = user!.role !== 'submitter' && user!.role !== 'dept_reviewer'
  // 增删订单资料包/删订单：COO/管理员任意；提交人仅本人负责订单（与后端 can_edit_order 对齐）
  const canEditOrder = (user!.role === 'admin' || user!.role === 'coo_reviewer') ||
    (user!.role === 'submitter' && order.owner_user_id === user!.id)
  const typeName = lang === 'en' ? (p: Package) => p.name_en || p.name_zh
    : lang === 'th' ? (p: Package) => p.name_th || p.name_zh : (p: Package) => p.name_zh

  async function addPkg() {
    if (!order) return
    const v = await form.validateFields()
    await orders.addPackage(order.id, { package_id: v.package_id, due_date: v.due_date || '' })
    message.success(t('add_package')); setOpen(false); form.resetFields(); load()
  }
  function removeOp(op: OrderPackage) {
    if (!order) return
    modal.confirm({ title: t('cancel'), content: t('remove_package_confirm'), okText: t('confirm'), cancelText: t('cancel'), onOk: async () => { await orders.removePackage(order.id, op.id); message.success(t('removed')); load() } })
  }

  return (
    <div>
      <Button icon={<ArrowLeftOutlined />} onClick={() => nav('/orders')} style={{ marginBottom: 12 }}>{t('back')}</Button>

      <PageHeader
        title={`${order.factory_code} · ${order.order_no}`}
        desc={order.factory_name ? `${order.factory_name}${order.customer ? ` · ${order.customer}` : ''}` : (order.customer || '')}
        extra={<Space>
          {canExport && (
            <>
              <Button icon={<DownloadOutlined />} onClick={() => orders.exportCsv(order.id, order.order_no)}>{t('export_csv')}</Button>
              <Button icon={<FileZipOutlined />} onClick={() => orders.exportZip(order.id, order.order_no)}>{t('export_zip')}</Button>
            </>
          )}
          <Button type="primary" icon={<PlusOutlined />} disabled={!canEditOrder} onClick={() => setOpen(true)}>{t('add_package')}</Button>
        </Space>}
      />

      <Card variant="borderless" className="coo-card">
        <Descriptions column={3} size="small">
          <Descriptions.Item label={t('factory')}>{order.factory_name || order.factory_code}</Descriptions.Item>
          <Descriptions.Item label={t('customer')}>{order.customer || '-'}</Descriptions.Item>
          <Descriptions.Item label={t('product')}>{order.product || '-'}</Descriptions.Item>
          <Descriptions.Item label={t('quantity')}>{order.quantity}</Descriptions.Item>
          <Descriptions.Item label={t('export_date')}>{order.export_date || '-'}</Descriptions.Item>
          <Descriptions.Item label={t('status')}><StatusTag status={order.status || 'active'} /></Descriptions.Item>
          <Descriptions.Item label={t('completion')} span={3}>{Math.round(order.completion)}%（{order.released_count}/{order.package_count}）</Descriptions.Item>
          {order.note && <Descriptions.Item label={t('change_note')} span={3}>{order.note}</Descriptions.Item>}
        </Descriptions>
      </Card>

      <Card variant="borderless" className="coo-card" style={{ marginTop: 16 }} title={t('progress')}>
        <Table
          rowKey="id"
          dataSource={order.packages}
          pagination={false}
          expandable={{
            expandedRowRender: (op) => <RowAttachments orderId={order.id} op={op} user={user!} onChanged={load} />,
          }}
          columns={[
            { title: 'COO', dataIndex: 'package_code', width: 90, render: (v) => v || '-' },
            { title: t('packages'), dataIndex: 'package_name', render: (v) => v || '-' },
            { title: t('status'), dataIndex: 'status', width: 150, render: (s: string) => (<><StatusTag status={s} /><br /><ReviewSteps status={s} compact /></>) },
            { title: t('attachment'), dataIndex: 'attachment_count', width: 90 },
            { title: t('due_date'), dataIndex: 'due_date', width: 110, render: (v) => v || '-' },
            { title: t('required'), dataIndex: 'required', width: 70, render: (v: boolean) => (v ? <Tag className="coo-tag" style={{ background: '#faf0dc', color: '#a67c1e', border: 'none' }}>{t('required')}</Tag> : '-') },
            { title: '', key: 'act', width: 90, render: (_, op: OrderPackage) => canEditOrder && <Button size="small" danger icon={<DeleteOutlined />} onClick={() => removeOp(op)}>{t('cancel')}</Button> },
          ]}
        />
      </Card>

      <Modal title={t('add_package')} open={open} onOk={addPkg} onCancel={() => setOpen(false)} okText={t('save')} cancelText={t('cancel')}>
        <Form form={form} layout="vertical">
          <Form.Item name="package_id" label={t('packages')} rules={[{ required: true }]}>
            <Select options={templates.map((p) => ({ label: `${p.code} · ${typeName(p)}`, value: p.id }))} />
          </Form.Item>
          <Form.Item name="due_date" label={t('due_date')}><Input placeholder="2026-10-15" /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}