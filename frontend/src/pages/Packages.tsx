import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { App, Button, Card, Form, Input, Modal, Select, Space, Switch, Table } from 'antd'
import { EditOutlined, EyeOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { org, packages } from '@/api/endpoints'
import { useAuth } from '@/store/AuthContext'
import { useI18n } from '@/i18n'
import StatusTag from '@/components/StatusTag'
import PageHeader from '@/components/PageHeader'
import type { Department, Package, PackageRow, User } from '@/types'

export default function Packages() {
  const { t, lang } = useI18n()
  const { user } = useAuth()
  const nav = useNavigate()
  const { message } = App.useApp()
  const [rows, setRows] = useState<PackageRow[]>([])
  const [kw, setKw] = useState('')
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
  useEffect(() => {
    if (!isAdmin) return
    org.listDepartments().then(setDepts).catch(() => setDepts([]))
    org.listUsers().then(setUsers).catch(() => setUsers([]))
  }, [isAdmin])

  const data = rows.filter((r) =>
    (lang === 'en' ? r.name_en : lang === 'th' ? r.name_th : r.name_zh).toLowerCase().includes(kw.toLowerCase()) ||
    r.code.toLowerCase().includes(kw.toLowerCase()),
  )

  const deptLabel = (id: string | null) => depts.find((d) => d.id === id)?.name_zh || '-'
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
    const v = await form.validateFields()
    const payload = { ...v, dept_id: v.dept_id ?? null, owner_user_id: v.owner_user_id ?? null, required: !!v.required }
    try {
      if (editing) {
        await packages.update(editing.id, payload)
        message.success(t('save'))
      } else {
        await packages.create(payload)
        message.success(t('create'))
      }
      setOpen(false)
      load()
    } catch (e: any) {
      message.error(e?.message || '操作失败')
    }
  }

  return (
    <>
      <PageHeader
        title={t('packages')}
        desc={t('packages_desc')}
        extra={<Space>
          <Input prefix={<SearchOutlined />} placeholder={t('packages')} value={kw} onChange={(e) => setKw(e.target.value)} style={{ width: 220 }} allowClear />
          {isAdmin && <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>{t('create')}</Button>}
        </Space>}
      />
      <Card variant="borderless" className="coo-card">
      <Table
        rowKey="id"
        loading={loading}
        dataSource={data}
        pagination={{ pageSize: 10, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100] }}
        columns={[
          { title: 'COO', dataIndex: 'code', width: 90 },
          { title: t('packages'), render: (_, r) => lang === 'en' ? r.name_en || r.name_zh : lang === 'th' ? r.name_th || r.name_zh : r.name_zh },
          { title: t('dept'), width: 120, render: (_, r) => deptLabel(r.dept_id) },
          { title: t('owner'), width: 110, render: (_, r) => ownerLabel(r.owner_user_id) },
          { title: t('version'), dataIndex: 'current_version', width: 90, render: (v: string) => v || '-' },
          { title: t('status'), dataIndex: 'current_status', width: 130, render: (s: string) => <StatusTag status={s} /> },
          { title: t('attachment'), dataIndex: 'attachment_count', width: 90 },
          { title: '', key: 'act', width: isAdmin ? 180 : 110, render: (_, r) => (
            <Space>
              <Button size="small" icon={<EyeOutlined />} onClick={() => nav(`/packages/${r.id}`)}>{t('detail')}</Button>
              {isAdmin && <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>{t('edit')}</Button>}
            </Space>
          ) },
        ]}
      />

      <Modal
        title={editing ? `${t('edit')} · ${editing.code}` : t('create')}
        open={open}
        onOk={save}
        onCancel={() => setOpen(false)}
        width={560}
        okText={t('save')}
        cancelText={t('cancel')}
      >
        <Form form={form} layout="vertical">
          <Space size="large" style={{ display: 'flex' }}>
            <Form.Item label="COO" name="code" rules={[{ required: true }]} style={{ width: 140 }}>
              <Input placeholder="COO-01" disabled={!!editing} />
            </Form.Item>
            <Form.Item label={t('sort_order')} name="sort_order"><Input type="number" /></Form.Item>
          </Space>
          <Form.Item label={t('name_zh')} name="name_zh" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label={t('name_en')} name="name_en"><Input /></Form.Item>
          <Form.Item label={t('name_th')} name="name_th"><Input /></Form.Item>
          <Space size="large" style={{ display: 'flex' }}>
            <Form.Item label={t('dept')} name="dept_id" style={{ width: 220 }}>
              <Select allowClear placeholder={t('dept')} options={depts.map((d) => ({ label: `${d.code} · ${d.name_zh}`, value: d.id }))} />
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
          <Form.Item label={t('due_date')} name="due_date"><Input placeholder="2026-10-15" /></Form.Item>
        </Form>
      </Modal>
      </Card>
    </>
  )
}