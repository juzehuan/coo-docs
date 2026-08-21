import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { App, Button, Card, Form, Input, InputNumber, Modal, Progress, Select, Space, Table } from 'antd'
import { DownloadOutlined, FileZipOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { factories, orders } from '@/api/endpoints'
import { useAuth } from '@/store/AuthContext'
import { useI18n } from '@/i18n'
import StatusTag from '@/components/StatusTag'
import PageHeader from '@/components/PageHeader'
import type { Factory, Order } from '@/types'

export default function Orders() {
  const { t, lang } = useI18n()
  const { user } = useAuth()
  const { message } = App.useApp()
  const nav = useNavigate()
  const [rows, setRows] = useState<Order[]>([])
  const [factList, setFactList] = useState<Factory[]>([])
  const [kw, setKw] = useState('')
  const [loading, setLoading] = useState(true)

  const isAdmin = user!.role === 'admin'
  const canExport = user!.role !== 'submitter' && user!.role !== 'dept_reviewer'
  const isReadOnly = user!.role === 'auditor'

  async function load() {
    setLoading(true)
    try {
      const [os, fs] = await Promise.all([orders.list(), factories.list()])
      setRows(os); setFactList(fs)
    } catch { setRows([]); setFactList([]) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const factName = (id: string) => factList.find((f) => f.id === id)?.name_zh || ''

  const data = rows.filter((r) =>
    r.order_no.toLowerCase().includes(kw.toLowerCase()) ||
    r.customer.toLowerCase().includes(kw.toLowerCase()) ||
    (r.factory_name || '').includes(kw),
  )

  // ---- 新建订单 ----
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()
  async function submit() {
    const v = await form.validateFields()
    await orders.create(v)
    message.success(t('create'))
    setOpen(false); form.resetFields(); load()
  }

  return (
    <>
      <PageHeader
        title={t('orders')}
        desc={t('orders_desc')}
        extra={<Space>
          <Input prefix={<SearchOutlined />} placeholder={t('orders')} value={kw} onChange={(e) => setKw(e.target.value)} style={{ width: 220 }} allowClear />
          {!isReadOnly && <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>{t('create_order')}</Button>}
        </Space>}
      />
      <Card variant="borderless" className="coo-card">
        <Table
          rowKey="id"
          loading={loading}
          dataSource={data}
          pagination={{ pageSize: 10 }}
          columns={[
            { title: t('factory'), width: 110, render: (_, r) => <span>{r.factory_code} · {(lang === 'en' ? '' : t('factory'))}{factName(r.factory_id)}</span> },
            { title: t('order_no'), dataIndex: 'order_no', width: 170 },
            { title: t('customer'), dataIndex: 'customer', ellipsis: true },
            { title: t('product'), dataIndex: 'product', ellipsis: true },
            { title: t('quantity'), dataIndex: 'quantity', width: 80 },
            { title: t('export_date'), dataIndex: 'export_date', width: 110, render: (v: string) => v || '-' },
            { title: t('completion'), width: 140, render: (_, r) => <Progress percent={r.completion} size="small" /> },
            { title: t('status'), dataIndex: 'status', width: 100, render: (s: string) => <StatusTag status={s || 'active'} /> },
            {
              title: '', key: 'act', width: 150,
              render: (_, r) => (
                <Space>
                  <a onClick={() => nav(`/orders/${r.id}`)}>{t('detail')}</a>
                  {canExport && (<>
                    <a onClick={() => orders.exportCsv(r.id)}><DownloadOutlined /></a>
                    <a onClick={() => orders.exportZip(r.id)}><FileZipOutlined /></a>
                  </>)}
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Modal title={t('create_order')} open={open} onOk={submit} onCancel={() => setOpen(false)} okText={t('save')} cancelText={t('cancel')}>
        <Form form={form} layout="vertical" initialValues={{ status: 'active', quantity: 0, required: true }}>
          <Form.Item name="factory_id" label={t('factory')} rules={[{ required: true }]}>
            <Select options={factList.filter((f) => isAdmin || user!.factory_ids.includes(f.id)).map((f) => ({ label: `${f.code} · ${f.name_zh}`, value: f.id }))} placeholder={t('factory')} />
          </Form.Item>
          <Form.Item name="order_no" label={t('order_no')} rules={[{ required: true }]}><Input placeholder="ORD-XXX-001" /></Form.Item>
          <Form.Item name="customer" label={t('customer')}><Input /></Form.Item>
          <Form.Item name="product" label={t('product')}><Input /></Form.Item>
          <Form.Item name="quantity" label={t('quantity')}><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="export_date" label={t('export_date')}><Input placeholder="2026-10-15" /></Form.Item>
        </Form>
      </Modal>
    </>
  )
}