import { useEffect, useState } from 'react'
import { App, Button, Card, Form, Input, Modal, Select, Table, Tabs, Tag } from 'antd'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { factories, org } from '@/api/endpoints'
import { useI18n } from '@/i18n'
import RoleTag from '@/components/RoleTag'
import PageHeader from '@/components/PageHeader'
import { ROLES } from '@/types'
import type { Department, Factory, User } from '@/types'

export default function Org() {
  const { t, lang } = useI18n()
  const { message } = App.useApp()
  const [depts, setDepts] = useState<Department[]>([])
  const [users, setUsers] = useState<User[]>([])
  const [factList, setFactList] = useState<Factory[]>([])

  async function load() {
    const [d, u, f] = await Promise.all([org.listDepartments(), org.listUsers(), factories.list()])
    setDepts(d); setUsers(u); setFactList(f)
  }
  useEffect(() => { load() }, [])

  const deptName = (id: string | null) => depts.find((d) => d.id === id)?.name_zh || '-'
  const factLabel = (id: string) => {
    const f = factList.find((x) => x.id === id)
    return f ? `${f.code} · ${f.name_zh}` : String(id)
  }

  // ---- 部门 ----
  const [deptOpen, setDeptOpen] = useState(false)
  const [deptForm] = Form.useForm()
  async function submitDept() {
    const v = await deptForm.validateFields()
    await org.createDepartment(v)
    message.success(t('create'))
    setDeptOpen(false); deptForm.resetFields(); load()
  }

  // ---- 工厂 ----
  const [factOpen, setFactOpen] = useState(false)
  const [factForm] = Form.useForm()
  async function submitFactory() {
    const v = await factForm.validateFields()
    await factories.create(v)
    message.success(t('create'))
    setFactOpen(false); factForm.resetFields(); load()
  }

  // ---- 用户 ----
  const [userOpen, setUserOpen] = useState(false)
  const [userForm] = Form.useForm()
  async function submitUser() {
    const v = await userForm.validateFields()
    await org.createUser({ ...v, dept_id: v.dept_id || null, factory_ids: v.factory_ids || [] })
    message.success(t('create'))
    setUserOpen(false); userForm.resetFields(); load()
  }
  async function resetPwd(id: string) {
    await org.resetPassword(id)
    message.success('user123')
  }

  const deptTab = (
    <Card variant="borderless" className="coo-card" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setDeptOpen(true)}>{t('create_dept')}</Button>}>
      <Table rowKey="id" dataSource={depts} pagination={false} columns={[
        { title: t('dept_code'), dataIndex: 'code', width: 120 },
        { title: t('name_zh'), dataIndex: 'name_zh' },
        { title: t('name_en'), dataIndex: 'name_en' },
        { title: t('name_th'), dataIndex: 'name_th' },
      ]} />
    </Card>
  )

  const factTab = (
    <Card variant="borderless" className="coo-card" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setFactOpen(true)}>{t('create_factory')}</Button>}>
      <Table rowKey="id" dataSource={factList} pagination={false} columns={[
        { title: t('factory_code'), dataIndex: 'code', width: 120 },
        { title: t('name_zh'), dataIndex: 'name_zh' },
        { title: t('name_en'), dataIndex: 'name_en' },
        { title: t('name_th'), dataIndex: 'name_th' },
        { title: t('status'), dataIndex: 'status', width: 100, render: (s: string) => <Tag className="coo-tag" style={{ background: s === 'active' ? '#eaf2ec' : '#f9ece9', color: s === 'active' ? '#2f6b4a' : '#9c4134', border: 'none' }}>{s === 'active' ? t('active') : t('disabled')}</Tag> },
      ]} />
    </Card>
  )

  const userTab = (
    <Card variant="borderless" className="coo-card" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setUserOpen(true)}>{t('create_user')}</Button>}>
      <Table rowKey="id" dataSource={users} pagination={false} columns={[
        { title: t('display_name'), render: (_, r) => r.display_name || r.username },
        { title: t('username'), dataIndex: 'username', width: 140 },
        { title: t('role'), dataIndex: 'role', width: 140, render: (r: string) => <RoleTag role={r} /> },
        { title: t('dept'), width: 120, render: (_, r) => deptName(r.dept_id) },
        { title: t('factory'), width: 160, render: (_, r) => (r.factory_ids?.length ? r.factory_ids.map((id) => <Tag key={id} style={{ marginRight: 4 }}>{factLabel(id)}</Tag>) : '-') },
        { title: '', width: 120, render: (_, r) => <Button size="small" icon={<ReloadOutlined />} onClick={() => resetPwd(r.id)}>{t('reset_pwd')}</Button> },
      ]} />
    </Card>
  )

  return (
    <>
      <PageHeader title={t('users')} desc={t('users_desc')} />
      <Tabs
        items={[
          { key: 'dept', label: t('department_manage'), children: deptTab },
          { key: 'factory', label: t('factory_manage'), children: factTab },
          { key: 'user', label: t('user_manage'), children: userTab },
        ]}
      />

      <Modal title={t('create_dept')} open={deptOpen} onOk={submitDept} onCancel={() => setDeptOpen(false)} okText={t('save')} cancelText={t('cancel')}>
        <Form form={deptForm} layout="vertical">
          <Form.Item name="code" label={t('dept_code')} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="name_zh" label={t('name_zh')} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="name_en" label={t('name_en')}><Input /></Form.Item>
          <Form.Item name="name_th" label={t('name_th')}><Input /></Form.Item>
        </Form>
      </Modal>

      <Modal title={t('create_factory')} open={factOpen} onOk={submitFactory} onCancel={() => setFactOpen(false)} okText={t('save')} cancelText={t('cancel')}>
        <Form form={factForm} layout="vertical">
          <Form.Item name="code" label={t('factory_code')} rules={[{ required: true }]}><Input placeholder="RMA / WEV" /></Form.Item>
          <Form.Item name="name_zh" label={t('name_zh')} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="name_en" label={t('name_en')}><Input /></Form.Item>
          <Form.Item name="name_th" label={t('name_th')}><Input /></Form.Item>
        </Form>
      </Modal>

      <Modal title={t('create_user')} open={userOpen} onOk={submitUser} onCancel={() => setUserOpen(false)} okText={t('save')} cancelText={t('cancel')}>
        <Form form={userForm} layout="vertical" initialValues={{ role: 'submitter', password: 'user123' }}>
          <Form.Item name="username" label={t('username')} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="display_name" label={t('display_name')}><Input /></Form.Item>
          <Form.Item name="password" label={t('password')} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="role" label={t('role')} rules={[{ required: true }]}><Select options={ROLES.map((r) => ({ label: r, value: r }))} /></Form.Item>
          <Form.Item name="dept_id" label={t('dept')}><Select allowClear options={depts.map((d) => ({ label: d.name_zh, value: d.id }))} /></Form.Item>
          <Form.Item name="factory_ids" label={t('factory')} extra={lang === 'zh' ? '不选择则无法访问任何工厂数据（管理员不受限）' : 'Leave empty = no factory data access (admin exempt)'}>
            <Select mode="multiple" allowClear options={factList.filter((f) => f.status === 'active').map((f) => ({ label: `${f.code} · ${f.name_zh}`, value: f.id }))} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}
