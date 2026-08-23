import { useEffect, useState } from 'react'
import { Alert, App, Button, Card, Form, Input, Modal, Select, Table, Tabs, Tag, Typography } from 'antd'
import { EditOutlined, PlusOutlined, ReloadOutlined, SafetyOutlined, StopOutlined, CheckCircleOutlined } from '@ant-design/icons'
import { factories, org } from '@/api/endpoints'
import { clearToken, errMessage } from '@/api/client'
import { localName, useI18n } from '@/i18n'
import { useSubmit } from '@/hooks/useSubmit'
import SubmitOnEnter from '@/components/SubmitOnEnter'
import RoleTag from '@/components/RoleTag'
import PageHeader from '@/components/PageHeader'
import { ROLES } from '@/types'
import type { Department, Factory, User } from '@/types'

export default function Org() {
  const { t, lang } = useI18n()
  const { loading: submitting, run: submitRun } = useSubmit()
  const { message } = App.useApp()
  const [depts, setDepts] = useState<Department[]>([])
  const [users, setUsers] = useState<User[]>([])
  const [factList, setFactList] = useState<Factory[]>([])

  async function load() {
    try {
      const [d, u, f] = await Promise.all([org.listDepartments(), org.listUsers(), factories.list()])
      setDepts(d); setUsers(u); setFactList(f)
    } catch (e) {
      message.error(errMessage(e))   // 未捕获会中断渲染；无权访问时给出明确提示
    }
  }
  useEffect(() => { load() }, [])

  const deptName = (id: string | null) => localName(depts.find((d) => d.id === id), lang, '-')
  const factLabel = (id: string) => {
    const f = factList.find((x) => x.id === id)
    return f ? `${f.code} · ${localName(f, lang)}` : String(id)
  }

  // ---- 部门 ----
  const [deptOpen, setDeptOpen] = useState(false)
  const [deptForm] = Form.useForm()
  async function submitDept() {
    const v = await deptForm.validateFields().catch(() => null)
    if (!v) return
    if (await submitRun(() => org.createDepartment(v), t('create'))) {
      setDeptOpen(false); deptForm.resetFields(); load()
    }
  }

  // ---- 工厂 ----
  const [factOpen, setFactOpen] = useState(false)
  const [factForm] = Form.useForm()
  async function submitFactory() {
    const v = await factForm.validateFields().catch(() => null)
    if (!v) return
    if (await submitRun(() => factories.create(v), t('create'))) {
      setFactOpen(false); factForm.resetFields(); load()
    }
  }

  // 工厂启停：规格「支持停用/启用」，后端 PATCH /factories/{id} 一直存在但无界面入口。
  // 停用的工厂不再出现在新建订单的可选项里（已有订单不受影响）。
  function toggleFactory(f: Factory) {
    const disabling = f.status === 'active'
    Modal.confirm({
      title: `${disabling ? t('disabled') : t('active')} · ${f.code}`,
      okText: disabling ? t('disabled') : t('active'),
      okButtonProps: disabling ? { danger: true } : undefined,
      cancelText: t('cancel'),
      onOk: async () => {
        try {
          await factories.update(f.id, { status: disabling ? 'disabled' : 'active' })
          message.success(t('save')); load()
        } catch (e) {
          message.error(errMessage(e))
        }
      },
    })
  }

  // ---- 用户 ----
  const [userOpen, setUserOpen] = useState(false)
  const [userForm] = Form.useForm()
  async function submitUser() {
    const v = await userForm.validateFields().catch(() => null)
    if (!v) return
    const ok = await submitRun(
      () => org.createUser({ ...v, dept_id: v.dept_id || null, factory_ids: v.factory_ids || [] }),
      t('create'))
    if (ok) { setUserOpen(false); userForm.resetFields(); load() }
  }
  const [pwdReset, setPwdReset] = useState<{ username: string; password: string } | null>(null)
  async function resetPwd(r: User) {
    const res = await org.resetPassword(r.id)
    setPwdReset({ username: r.display_name || r.username, password: res.password })
  }

  // ---- 用户编辑 / 停用启用（F-02）----
  const [editUser, setEditUser] = useState<User | null>(null)
  const [editForm] = Form.useForm()
  function openEditUser(r: User) {
    setEditUser(r)
    editForm.setFieldsValue({
      display_name: r.display_name, email: r.email, phone: r.phone,
      role: r.role, dept_id: r.dept_id || undefined, factory_ids: r.factory_ids || [],
    })
  }
  async function submitEditUser() {
    const v = await editForm.validateFields().catch(() => null)
    if (!v) return
    const ok = await submitRun(
      () => org.updateUser(editUser!.id, { ...v, dept_id: v.dept_id || null, factory_ids: v.factory_ids || [] }),
      t('save'))
    if (ok) { setEditUser(null); load() }
  }
  function toggleUserStatus(r: User) {
    const disabling = r.status === 'active'
    const name = r.display_name || r.username
    Modal.confirm({
      title: (disabling ? t('disable_user_title') : t('enable_user_title')).replace('{name}', name),
      content: disabling ? t('disable_user_content') : undefined,
      okText: disabling ? t('disabled') : t('active'),
      okButtonProps: disabling ? { danger: true } : undefined,
      cancelText: t('cancel'),
      onOk: async () => {
        try {
          await org.updateUser(r.id, { status: disabling ? 'disabled' : 'active' })
          message.success(t('save'))
          load()
        } catch (e) {
          message.error(errMessage(e))
        }
      },
    })
  }

  // ---- 部门编辑 ----
  const [editDept, setEditDept] = useState<Department | null>(null)
  const [editDeptForm] = Form.useForm()
  function openEditDept(d: Department) {
    setEditDept(d)
    editDeptForm.setFieldsValue({ name_zh: d.name_zh, name_en: d.name_en, name_th: d.name_th })
  }
  async function submitEditDept() {
    const v = await editDeptForm.validateFields().catch(() => null)
    if (!v) return
    if (await submitRun(() => org.updateDepartment(editDept!.id, v), t('save'))) {
      setEditDept(null); load()
    }
  }

  const deptTab = (
    <Card variant="borderless" className="coo-card" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setDeptOpen(true)}>{t('create_dept')}</Button>}>
      <Table rowKey="id" dataSource={depts} pagination={false} columns={[
        { title: t('dept_code'), dataIndex: 'code', width: 120 },
        { title: t('name_zh'), dataIndex: 'name_zh' },
        { title: t('name_en'), dataIndex: 'name_en' },
        { title: t('name_th'), dataIndex: 'name_th' },
        { title: '', width: 90, render: (_, d) => <Button size="small" icon={<EditOutlined />} onClick={() => openEditDept(d)}>{t('edit')}</Button> },
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
        {
          title: '', width: 100,
          render: (_, f) => (
            <Button size="small" danger={f.status === 'active'}
              icon={f.status === 'active' ? <StopOutlined /> : <CheckCircleOutlined />}
              onClick={() => toggleFactory(f)}>
              {f.status === 'active' ? t('disabled') : t('active')}
            </Button>
          ),
        },
      ]} />
    </Card>
  )

  // ---- 安全设置：JWT 密钥轮换 ----
  const [secretKey, setSecretKey] = useState('')
  const [rotating, setRotating] = useState(false)
  function rotateSecret() {
    Modal.confirm({
      title: t('rotate_confirm_title'),
      content: t('rotate_confirm_content'),
      okText: t('rotate_action'),
      okButtonProps: { danger: true },
      cancelText: t('cancel'),
      onOk: async () => {
        setRotating(true)
        try {
          await org.rotateJwtSecret(secretKey.trim() || undefined)
          message.success(t('rotate_done'))
          clearToken()
          location.href = '/login'
        } catch (e) {
          message.error(errMessage(e))
        } finally {
          setRotating(false)
        }
      },
    })
  }

  const securityTab = (
    <Card variant="borderless" className="coo-card" title={t('sec_jwt_title')}>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message={t('sec_alert_msg')}
        description={t('sec_alert_desc')}
      />
      <Input.Password
        value={secretKey}
        onChange={(e) => setSecretKey(e.target.value)}
        placeholder={t('sec_custom_placeholder')}
        style={{ maxWidth: 480, marginRight: 12, marginBottom: 12 }}
      />
      <Button danger type="primary" icon={<SafetyOutlined />} loading={rotating} onClick={rotateSecret}>
        {t('sec_rotate_btn')}
      </Button>
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
        { title: t('status'), width: 90, render: (_, r) => <Tag className="coo-tag" style={{ background: r.status === 'active' ? '#eaf2ec' : '#f9ece9', color: r.status === 'active' ? '#2f6b4a' : '#9c4134', border: 'none' }}>{r.status === 'active' ? t('active') : t('disabled')}</Tag> },
        {
          title: '', width: 250,
          render: (_, r) => (
            <span style={{ display: 'inline-flex', gap: 6 }}>
              <Button size="small" icon={<EditOutlined />} onClick={() => openEditUser(r)}>{t('edit')}</Button>
              <Button size="small" icon={<ReloadOutlined />} onClick={() => resetPwd(r)}>{t('reset_pwd')}</Button>
              <Button
                size="small"
                danger={r.status === 'active'}
                icon={r.status === 'active' ? <StopOutlined /> : <CheckCircleOutlined />}
                onClick={() => toggleUserStatus(r)}
              >
                {r.status === 'active' ? t('disabled') : t('active')}
              </Button>
            </span>
          ),
        },
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
          { key: 'security', label: t('sec_settings'), children: securityTab },
        ]}
      />

      <Modal title={t('create_dept')} open={deptOpen} onOk={submitDept} confirmLoading={submitting} onCancel={() => setDeptOpen(false)} okText={t('save')} cancelText={t('cancel')}>
        <Form form={deptForm} layout="vertical" onFinish={submitDept}>
          <Form.Item name="code" label={t('dept_code')} rules={[{ required: true }]}><Input maxLength={32} /></Form.Item>
          <Form.Item name="name_zh" label={t('name_zh')} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="name_en" label={t('name_en')}><Input /></Form.Item>
          <Form.Item name="name_th" label={t('name_th')}><Input /></Form.Item>
        <SubmitOnEnter /></Form>
      </Modal>

      <Modal title={t('create_factory')} open={factOpen} onOk={submitFactory} confirmLoading={submitting} onCancel={() => setFactOpen(false)} okText={t('save')} cancelText={t('cancel')}>
        <Form form={factForm} layout="vertical" onFinish={submitFactory}>
          <Form.Item name="code" label={t('factory_code')} rules={[{ required: true }]}><Input maxLength={32} placeholder="RMA / WEV" /></Form.Item>
          <Form.Item name="name_zh" label={t('name_zh')} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="name_en" label={t('name_en')}><Input /></Form.Item>
          <Form.Item name="name_th" label={t('name_th')}><Input /></Form.Item>
        <SubmitOnEnter /></Form>
      </Modal>

      <Modal title={t('create_user')} open={userOpen} onOk={submitUser} confirmLoading={submitting} onCancel={() => setUserOpen(false)} okText={t('save')} cancelText={t('cancel')}>
        <Form form={userForm} layout="vertical" initialValues={{ role: 'submitter', password: 'user123' }} onFinish={submitUser}>
          <Form.Item name="username" label={t('username')} rules={[{ required: true }]}><Input maxLength={64} /></Form.Item>
          <Form.Item name="display_name" label={t('display_name')}><Input /></Form.Item>
          <Form.Item name="password" label={t('password')} rules={[{ required: true }, { min: 6, message: t('v_too_short').replace('{n}', '6') }]}><Input /></Form.Item>
          <Form.Item name="role" label={t('role')} rules={[{ required: true }]}><Select options={ROLES.map((r) => ({ label: r, value: r }))} /></Form.Item>
          <Form.Item name="dept_id" label={t('dept')}><Select allowClear options={depts.map((d) => ({ label: d.name_zh, value: d.id }))} /></Form.Item>
          <Form.Item name="factory_ids" label={t('factory')} extra={t('factory_hint')}>
            <Select mode="multiple" allowClear options={factList.filter((f) => f.status === 'active').map((f) => ({ label: `${f.code} · ${localName(f, lang)}`, value: f.id }))} />
          </Form.Item>
        <SubmitOnEnter /></Form>
      </Modal>
      <Modal title={`${t('edit')} · ${editUser?.display_name || editUser?.username || ''}`} open={!!editUser} onOk={submitEditUser} confirmLoading={submitting} onCancel={() => setEditUser(null)} okText={t('save')} cancelText={t('cancel')}>
        <Form form={editForm} layout="vertical" onFinish={submitEditUser}>
          <Form.Item name="display_name" label={t('display_name')}><Input /></Form.Item>
          <Form.Item name="role" label={t('role')} rules={[{ required: true }]}><Select options={ROLES.map((r) => ({ label: r, value: r }))} /></Form.Item>
          <Form.Item name="dept_id" label={t('dept')}><Select allowClear options={depts.map((d) => ({ label: d.name_zh, value: d.id }))} /></Form.Item>
          <Form.Item name="factory_ids" label={t('factory')} extra={t('factory_hint')}>
            <Select mode="multiple" allowClear options={factList.filter((f) => f.status === 'active').map((f) => ({ label: `${f.code} · ${localName(f, lang)}`, value: f.id }))} />
          </Form.Item>
        <SubmitOnEnter /></Form>
      </Modal>

      <Modal title={`${t('edit')} · ${editDept?.code || ''}`} open={!!editDept} onOk={submitEditDept} confirmLoading={submitting} onCancel={() => setEditDept(null)} okText={t('save')} cancelText={t('cancel')}>
        <Form form={editDeptForm} layout="vertical" onFinish={submitEditDept}>
          <Form.Item name="name_zh" label={t('name_zh')} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="name_en" label={t('name_en')}><Input /></Form.Item>
          <Form.Item name="name_th" label={t('name_th')}><Input /></Form.Item>
        <SubmitOnEnter /></Form>
      </Modal>

      <Modal title={t('reset_pwd')} open={!!pwdReset} onOk={() => setPwdReset(null)} onCancel={() => setPwdReset(null)} okText={t('confirm')} cancelText={t('cancel')}>
        {pwdReset && (
          <div>
            <p>{lang === 'zh' ? `已为「${pwdReset.username}」生成一次性临时密码，请立即告知用户：` : `Temporary password generated for "${pwdReset.username}", share it with the user:`}</p>
            <Typography.Title level={4} copyable style={{ textAlign: 'center', margin: '12px 0', letterSpacing: 2 }}>{pwdReset.password}</Typography.Title>
            <p style={{ color: '#9c4134', margin: 0 }}>{lang === 'zh' ? '该密码仅本次展示，关闭后不可再次查看，请务必先复制。' : 'Shown only once; copy it now.'}</p>
          </div>
        )}
      </Modal>
    </>
  )
}
