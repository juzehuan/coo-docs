import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { App, Button, Card, DatePicker, Form, Input, Modal, Select, Space, Switch, Table } from 'antd'
import dayjs from 'dayjs'
import type { Dayjs } from 'dayjs'
import { EditOutlined, EyeOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { errMessage } from '@/api/client'
import { org, packages } from '@/api/endpoints'
import { useAuth } from '@/store/AuthContext'
import { localName, useI18n } from '@/i18n'
import { useSubmit } from '@/hooks/useSubmit'
import { STATUS_LABELS } from '@/i18n/messages'
import SubmitOnEnter from '@/components/SubmitOnEnter'
import StatusTag from '@/components/StatusTag'
import PageHeader from '@/components/PageHeader'
import RowActions, { ActionButton } from '@/components/RowActions'
import { ELLIPSIS, actionWidth } from '@/utils/table'
import type { Department, Lang, Package, PackageRow, User } from '@/types'

// 可筛选的资料包当前状态（与后端 current_status 取值一致）
const STATUS_FILTERS = ['none', 'draft', 'pending_dept', 'pending_coo', 'released', 'rejected', 'withdrawn']

export default function Packages() {
  const { t, lang } = useI18n()
  const { loading: submitting, run: submitRun } = useSubmit()
  const { user } = useAuth()
  const nav = useNavigate()
  const { message } = App.useApp()
  const [rows, setRows] = useState<PackageRow[]>([])
  const [kw, setKw] = useState('')
  const [deptFilter, setDeptFilter] = useState<string | undefined>()
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [loading, setLoading] = useState(true)

  // 配置弹窗（仅管理员）
  const isAdmin = user!.role === 'admin'
  const [depts, setDepts] = useState<Department[]>([])
  const [users, setUsers] = useState<User[]>([])
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Package | null>(null)
  const [form] = Form.useForm()

  async function load() {
    setLoading(true)
    try {
      const r = await packages.list()
      setRows(r)
    } catch { setRows([]) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])
  // 部门列表所有角色都要（用于展示「责任部门」列与按部门筛选）；用户列表仅管理员需要
  useEffect(() => {
    org.listDepartments().then(setDepts).catch(() => setDepts([]))
  }, [])
  useEffect(() => {
    if (!isAdmin) return
    org.listUsers().then(setUsers).catch(() => setUsers([]))
  }, [isAdmin])

  const kwLower = kw.trim().toLowerCase()
  const data = rows.filter((r) => {
    // 关键词跨三语匹配：同一团队可能用不同语言，只搜当前语言会让人搜不到自己知道的名字
    const names = [r.name_zh, r.name_en, r.name_th, r.code].filter(Boolean).join(' ').toLowerCase()
    if (kwLower && !names.includes(kwLower)) return false
    if (deptFilter && r.dept_id !== deptFilter) return false
    if (statusFilter && r.current_status !== statusFilter) return false
    return true
  })

  // 操作列固定在右侧，宽度按实际按钮数算
  const actWidth = actionWidth(isAdmin ? 2 : 1)

  const deptLabel = (id: string | null) => {
    const d = depts.find((x) => x.id === id)
    if (!d) return '-'
    return localName(d, lang)
  }
  const ownerLabel = (id: string | null) => {
    const u = users.find((x) => x.id === id)
    return u ? u.display_name || u.username : '-'
  }

  function openCreate() {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ code: '', name_zh: '', name_en: '', name_th: '', dept_id: undefined, owner_user_id: undefined, required: true, status: 'active', sort_order: 0, due_date: '', review_focus: '' })
    setOpen(true)
  }
  function openEdit(r: PackageRow) {
    setEditing(r)
    form.setFieldsValue({ ...r, dept_id: r.dept_id ?? undefined, owner_user_id: r.owner_user_id ?? undefined })
    setOpen(true)
  }
  async function save() {
    const v = await form.validateFields().catch(() => null)
    if (!v) return
    const payload = { ...v, dept_id: v.dept_id ?? null, owner_user_id: v.owner_user_id ?? null, required: !!v.required }
    const ok = await submitRun(
      () => (editing ? packages.update(editing.id, payload) : packages.create(payload)),
      editing ? t('save') : t('create'))
    if (ok) { setOpen(false); load() }
  }

  return (
    <>
      <PageHeader
        title={t('packages')}
        desc={t('packages_desc')}
        extra={<Space>
          <Input prefix={<SearchOutlined />} placeholder={t('packages')} value={kw} onChange={(e) => setKw(e.target.value)} style={{ width: 200 }} allowClear />
          <Select allowClear placeholder={t('dept')} style={{ width: 150 }} value={deptFilter} onChange={setDeptFilter}
            options={depts.map((d) => ({ label: localName(d, lang), value: d.id }))} />
          <Select allowClear placeholder={t('status')} style={{ width: 140 }} value={statusFilter} onChange={setStatusFilter}
            options={STATUS_FILTERS.map((v) => ({ label: STATUS_LABELS[v]?.[lang as Lang] ?? v, value: v }))} />
          {isAdmin && <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>{t('create')}</Button>}
        </Space>}
      />
      <Card variant="borderless" className="coo-card">
      <Table
        rowKey="id"
        loading={loading}
        dataSource={data}
        pagination={{ defaultPageSize: 10, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100] }}
        // 列宽之和；不够宽时整表横向滚动，列宽不被挤压，字段就不会折行
        scroll={{ x: 870 + actWidth }}
        columns={[
          { title: 'COO', dataIndex: 'code', width: 90 },
          { title: t('packages'), width: 240, ellipsis: ELLIPSIS, render: (_, r) => localName(r, lang) },
          { title: t('dept'), width: 120, ellipsis: ELLIPSIS, render: (_, r) => deptLabel(r.dept_id) },
          { title: t('owner'), width: 110, ellipsis: ELLIPSIS, render: (_, r) => ownerLabel(r.owner_user_id) },
          { title: t('version'), dataIndex: 'current_version', width: 90, render: (v: string) => v || '-' },
          { title: t('status'), dataIndex: 'current_status', width: 130, render: (s: string) => <StatusTag status={s} /> },
          { title: t('attachment'), dataIndex: 'attachment_count', width: 90 },
          { title: t('actions'), key: 'act', width: actWidth, fixed: 'right', render: (_, r) => (
            <RowActions>
              <ActionButton label={t('detail')} icon={<EyeOutlined />} onClick={() => nav(`/packages/${r.id}`)} />
              {isAdmin && <ActionButton label={t('edit')} icon={<EditOutlined />} onClick={() => openEdit(r)} />}
            </RowActions>
          ) },
        ]}
      />

      <Modal
        title={editing ? `${t('edit')} · ${editing.code}` : t('create')}
        open={open}
        onOk={save}
        confirmLoading={submitting}
        onCancel={() => setOpen(false)}
        width={560}
        okText={t('save')}
        cancelText={t('cancel')}
      >
        <Form form={form} layout="vertical" onFinish={save}>
          <Space size="large" style={{ display: 'flex' }}>
            <Form.Item label="COO" name="code" rules={[{ required: true }]} style={{ width: 140 }}>
              <Input maxLength={32} placeholder="COO-01" disabled={!!editing} />
            </Form.Item>
            <Form.Item label={t('sort_order')} name="sort_order"><Input type="number" /></Form.Item>
          </Space>
          <Form.Item label={t('name_zh')} name="name_zh" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label={t('name_en')} name="name_en"><Input /></Form.Item>
          <Form.Item label={t('name_th')} name="name_th"><Input /></Form.Item>
          <Space size="large" style={{ display: 'flex' }}>
            <Form.Item label={t('dept')} name="dept_id" style={{ width: 220 }}>
              <Select allowClear placeholder={t('dept')} options={depts.map((d) => ({ label: `${d.code} · ${localName(d, lang)}`, value: d.id }))} />
            </Form.Item>
            <Form.Item name="required" label={t('required')} valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item label={t('status')} name="status">
              <Select options={[{ value: 'active', label: t('active') }, { value: 'disabled', label: t('disabled') }]} />
            </Form.Item>
          </Space>
          <Form.Item label={t('owner')} name="owner_user_id">
            <Select
              allowClear showSearch optionFilterProp="label"
              placeholder={t('owner')}
              options={users.map((u) => ({ label: `${u.display_name || u.username} (${u.username})`, value: u.id }))}
            />
          </Form.Item>
          <Form.Item label={t('review_focus')} name="review_focus"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item label={t('due_date')} name="due_date"
            /* 用日期选择器而不是自由文本：截止日期此前是纯 Input，任何文本都能存进去，
               而超期判断只认年在前的写法——`01/15/2020` 这类美式日期会被静默当成
               "没有期限"，界面还照原样显示回来，用户以为设好了而超期永远不标红。
               getValueProps/normalize 让表单值仍是字符串，周边代码无需改动。 */
            getValueProps={(v) => ({ value: v && dayjs(v).isValid() ? dayjs(v) : null })}
            normalize={(v) => (v ? (v as Dayjs).format('YYYY-MM-DD') : '')}>
            {/* inputReadOnly：只允许从日历选，不允许手输。
                antd 的 DatePicker 对**无法解析的手输文本会静默丢弃**——实测键入
                `01/15/2020` 后输入框到提交那一刻仍显示着它，而表单实际提交的是
                空串，等于把"静默取消期限"这个缺陷从后端搬到了前端，后端的 422
                根本不会被触发。禁掉手输后，取值只能来自日历，必然是合法日期。 */}
            <DatePicker style={{ width: '100%' }} placeholder="2026-10-15" inputReadOnly />
          </Form.Item>
        <SubmitOnEnter /></Form>
      </Modal>
      </Card>
    </>
  )
}