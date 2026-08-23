import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { App, Button, Card, Form, Input, InputNumber, Modal, Progress, Select, Space, Table } from 'antd'
import { DownloadOutlined, EyeOutlined, FileZipOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { errMessage } from '@/api/client'
import { factories, orders } from '@/api/endpoints'
import { useAuth } from '@/store/AuthContext'
import { localName, useI18n } from '@/i18n'
import { useSubmit } from '@/hooks/useSubmit'
import SubmitOnEnter from '@/components/SubmitOnEnter'
import StatusTag from '@/components/StatusTag'
import PageHeader from '@/components/PageHeader'
import type { Factory, Order } from '@/types'

const PAGE_SIZE = 20

export default function Orders() {
  const { t, lang } = useI18n()
  const { loading: submitting, run: submitRun } = useSubmit()
  const { user } = useAuth()
  const { message } = App.useApp()
  const nav = useNavigate()
  const [rows, setRows] = useState<Order[]>([])
  const [factList, setFactList] = useState<Factory[]>([])
  const [kw, setKw] = useState('')
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)

  const isAdmin = user!.role === 'admin'
  const canExport = user!.role !== 'submitter' && user!.role !== 'dept_reviewer'
  const isReadOnly = user!.role === 'auditor'

  // 搜索与分页都走服务端：订单随业务量无限增长，一次性全量下发在千单规模下
  // 每次打开页面都要拉数百 KB；而只加分页不改搜索，会让关键词只在当前页内匹配，
  // 用户搜不到却以为"没有这张订单"（与第 35 轮审计导出忽略筛选同类）。
  const load = useCallback(async (keyword?: string, p = 1) => {
    setLoading(true)
    try {
      const [os, fs] = await Promise.all([
        orders.list({ q: (keyword ?? kw).trim() || undefined, limit: PAGE_SIZE, offset: (p - 1) * PAGE_SIZE }),
        factories.list(),
      ])
      setRows(os.items); setTotal(os.total); setFactList(fs)
    } catch (e) {
      setRows([]); setTotal(0); message.error(errMessage(e))
    } finally { setLoading(false) }
  }, [kw, message])
  useEffect(() => { load(undefined, 1) }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const factName = (id: string) => localName(factList.find((f) => f.id === id), lang)

  const data = rows

  // ---- 新建订单 ----
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()
  async function submit() {
    // 校验失败交给 antd 行内提示，不进 submitRun（否则会弹出无意义的错误 toast）
    const v = await form.validateFields().catch(() => null)
    if (!v) return
    const ok = await submitRun(() => orders.create(v), t('create'))
    // 仅成功时关窗重置：失败时保留用户已填内容
    if (ok) { setOpen(false); form.resetFields(); load() }
  }

  return (
    <>
      <PageHeader
        title={t('orders')}
        desc={t('orders_desc')}
        extra={<Space>
          {/* 回车或点清除即查询：服务端搜索，覆盖全部订单而非当前页 */}
          <Input prefix={<SearchOutlined />} placeholder={t('orders')} value={kw} style={{ width: 220 }} allowClear
            onChange={(e) => { setKw(e.target.value); if (!e.target.value) { setPage(1); load('', 1) } }}
            onPressEnter={() => { setPage(1); load(undefined, 1) }} />
          <Button icon={<SearchOutlined />} onClick={() => { setPage(1); load(undefined, 1) }}>{t('search')}</Button>
          {!isReadOnly && <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>{t('create_order')}</Button>}
        </Space>}
      />
      <Card variant="borderless" className="coo-card">
        <Table
          rowKey="id"
          loading={loading}
          dataSource={data}
          pagination={{ current: page, pageSize: PAGE_SIZE, total, showSizeChanger: false,
            onChange: (p) => { setPage(p); load(undefined, p) },
            showTotal: (n) => t('audit_total').replace('{total}', String(n)) }}
          columns={[
            { title: t('factory'), width: 110, render: (_, r) => <span>{r.factory_code} · {r.factory_name || factName(r.factory_id)}</span> },
            { title: t('order_no'), dataIndex: 'order_no', width: 170 },
            { title: t('customer'), dataIndex: 'customer', ellipsis: true },
            { title: t('product'), dataIndex: 'product', ellipsis: true },
            { title: t('quantity'), dataIndex: 'quantity', width: 80 },
            { title: t('export_date'), dataIndex: 'export_date', width: 110, render: (v: string) => v || '-' },
            { title: t('completion'), width: 140, render: (_, r) => <Progress percent={r.completion} size="small" /> },
            { title: t('status'), dataIndex: 'status', width: 100, render: (s: string) => <StatusTag status={s || 'active'} /> },
            {
              title: '', key: 'act', width: 260,
              render: (_, r) => (
                <Space size={4}>
                  <Button size="small" icon={<EyeOutlined />} onClick={() => nav(`/orders/${r.id}`)}>{t('detail')}</Button>
                  {canExport && (<>
                    <Button size="small" icon={<DownloadOutlined />} onClick={() => orders.exportCsv(r.id, r.order_no)}>{t('export_csv')}</Button>
                    <Button size="small" icon={<FileZipOutlined />} onClick={() => orders.exportZip(r.id, r.order_no)}>{t('export_zip')}</Button>
                  </>)}
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Modal title={t('create_order')} open={open} onOk={submit} confirmLoading={submitting}
        onCancel={() => setOpen(false)} okText={t('save')} cancelText={t('cancel')}>
        <Form form={form} layout="vertical" initialValues={{ status: 'active', quantity: 0, required: true }} onFinish={submit}>
          <Form.Item name="factory_id" label={t('factory')} rules={[{ required: true }]}>
            {/* 已停用工厂不再出现在新建订单可选项（后端同样拒绝，见 orders.create_order）；
                factList 本身保留全量，订单列表仍需按 id 显示历史工厂名 */}
            <Select options={factList.filter((f) => f.status === 'active' && (isAdmin || user!.factory_ids.includes(f.id))).map((f) => ({ label: `${f.code} · ${localName(f, lang)}`, value: f.id }))} placeholder={t('factory')} />
          </Form.Item>
          <Form.Item name="order_no" label={t('order_no')} rules={[{ required: true }]}><Input maxLength={64} placeholder="ORD-XXX-001" /></Form.Item>
          <Form.Item name="customer" label={t('customer')}><Input /></Form.Item>
          <Form.Item name="product" label={t('product')}><Input /></Form.Item>
          <Form.Item name="quantity" label={t('quantity')}><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="export_date" label={t('export_date')}><Input placeholder="2026-10-15" /></Form.Item>
        <SubmitOnEnter /></Form>
      </Modal>
    </>
  )
}