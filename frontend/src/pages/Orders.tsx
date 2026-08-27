import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { App, Button, Card, DatePicker, Form, Input, InputNumber, Modal, Progress, Select, Space, Table } from 'antd'
import dayjs from 'dayjs'
import type { Dayjs } from 'dayjs'
import { DownloadOutlined, EyeOutlined, FileZipOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { errMessage } from '@/api/client'
import { exportOrQueue, exportErrMessage } from '@/utils/exportOrQueue'
import { factories, orders } from '@/api/endpoints'
import { useAuth } from '@/store/AuthContext'
import { localName, useI18n } from '@/i18n'
import { useSubmit } from '@/hooks/useSubmit'
import SubmitOnEnter from '@/components/SubmitOnEnter'
import StatusTag from '@/components/StatusTag'
import PageHeader from '@/components/PageHeader'
import RowActions, { ActionButton } from '@/components/RowActions'
import { ELLIPSIS, actionWidth } from '@/utils/table'
import type { Factory, Order } from '@/types'

const PAGE_SIZE = 20

export default function Orders() {

  /** 导出：先直接下载，服务器名额已满（429）时自动转为排队作业。
   *  说明见 utils/exportOrQueue.ts —— 不把 0.08 秒的导出也改成"提交→轮询"。 */
  async function runExport(kind: 'order_xlsx' | 'order_zip', id: string, orderNo: string) {
    try {
      const how = await exportOrQueue(
        () => (kind === 'order_zip' ? orders.exportZip(id, orderNo) : orders.exportCsv(id, orderNo)),
        kind, { order_id: id })
      if (how === 'queued') message.info(t('export_queued'))
    } catch (e) {
      message.error(await exportErrMessage(e))
    }
  }

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

  // 操作列固定在右侧，宽度按实际按钮数算；scroll.x 取各列宽之和，
  // 列宽不被挤压，字段也就不会折行（不够宽时整表横向滚动）。
  const actWidth = actionWidth(canExport ? 3 : 1)

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
          scroll={{ x: 1080 + actWidth }}
          columns={[
            // 返回纯字符串而不是 <span>：ellipsis 的悬浮提示只认字符串内容
            { title: t('factory'), width: 160, ellipsis: ELLIPSIS, render: (_, r) => `${r.factory_code} · ${r.factory_name || factName(r.factory_id)}` },
            { title: t('order_no'), dataIndex: 'order_no', width: 170, ellipsis: ELLIPSIS },
            { title: t('customer'), dataIndex: 'customer', width: 160, ellipsis: ELLIPSIS },
            { title: t('product'), dataIndex: 'product', width: 160, ellipsis: ELLIPSIS },
            { title: t('quantity'), dataIndex: 'quantity', width: 80 },
            { title: t('export_date'), dataIndex: 'export_date', width: 110, render: (v: string) => v || '-' },
            { title: t('completion'), width: 140, render: (_, r) => <Progress percent={r.completion} size="small" /> },
            { title: t('status'), dataIndex: 'status', width: 100, render: (s: string) => <StatusTag status={s || 'active'} /> },
            {
              title: t('actions'), key: 'act', width: actWidth, fixed: 'right',
              render: (_, r) => (
                <RowActions>
                  <ActionButton label={t('detail')} icon={<EyeOutlined />} onClick={() => nav(`/orders/${r.id}`)} />
                  {canExport && (<>
                    <ActionButton label={t('export_csv')} icon={<DownloadOutlined />} onClick={() => runExport('order_xlsx', r.id, r.order_no)} />
                    <ActionButton label={t('export_zip')} icon={<FileZipOutlined />} onClick={() => runExport('order_zip', r.id, r.order_no)} />
                  </>)}
                </RowActions>
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
          <Form.Item name="export_date" label={t('export_date')}
            /* 与资料包截止日期、订单资料包截止日期用同一套：此前这里是纯 Input，
               任何文本都能存进去（后端 export_date 就是 32 字符的宽松文本），
               `01/15/2020` 这类美式写法会原样存下并原样显示回来，看着像是设好了。
               getValueProps/normalize 让表单值仍是 'YYYY-MM-DD' 字符串，后端无需改动。 */
            getValueProps={(v) => ({ value: v && dayjs(v).isValid() ? dayjs(v) : null })}
            normalize={(v) => (v ? (v as Dayjs).format('YYYY-MM-DD') : '')}>
            {/* inputReadOnly：只允许从日历选。antd 的 DatePicker 对无法解析的手输文本
                会静默丢弃——输入框里还显示着它，提交的却是空串。 */}
            <DatePicker style={{ width: '100%' }} placeholder="2026-10-15" inputReadOnly />
          </Form.Item>
        <SubmitOnEnter /></Form>
      </Modal>
    </>
  )
}