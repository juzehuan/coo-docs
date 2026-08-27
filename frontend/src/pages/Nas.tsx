import { useCallback, useEffect, useState } from 'react'
import { App, Button, Card, Col, Form, Input, Modal, Radio, Row, Space, Switch, Table, Tag, Typography } from 'antd'
import { DatabaseOutlined, SettingOutlined, SyncOutlined } from '@ant-design/icons'
import { errMessage } from '@/api/client'
import { nas } from '@/api/endpoints'
import { useAuth } from '@/store/AuthContext'
import { useI18n } from '@/i18n'
import { useSubmit } from '@/hooks/useSubmit'
import { formatTime } from '@/utils/format'
import SubmitOnEnter from '@/components/SubmitOnEnter'
import PageHeader from '@/components/PageHeader'
import type { NasConfig, NasStatus, SyncRecord } from '@/types'

/** 同步状态：后端枚举 → 文案键与配色。running/partial 走同一档警示色。 */
const SYNC_STATUS_LABEL: Record<string, string> = {
  running: 'sync_running',
  success: 'sync_ok',   // sync_success 已被「同步完成」的提示语占用
  partial: 'sync_partial',
  failed: 'sync_failed',
}
const SYNC_STATUS_STYLE: Record<string, { bg: string; fg: string }> = {
  success: { bg: '#eaf2ec', fg: '#2f6b4a' },
  failed: { bg: '#f9ece9', fg: '#9c4134' },
  partial: { bg: '#faf0dc', fg: '#a67c1e' },
  running: { bg: '#faf0dc', fg: '#a67c1e' },
}

export default function Nas() {
  const { t } = useI18n()
  const { user } = useAuth()
  const { message } = App.useApp()
  const { loading: submitting, run: submitRun } = useSubmit()
  const [st, setSt] = useState<NasStatus | null>(null)
  const [recs, setRecs] = useState<SyncRecord[]>([])
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    // 捕获失败：未捕获的拒绝会中断渲染导致白屏（无权角色深链接进入时即为此情形）
    try {
      const [s, r] = await Promise.all([nas.status(), nas.records(200)])
      setSt(s); setRecs(r)
    } catch (e) {
      setSt(null); setRecs([]); message.error(errMessage(e))
    }
  }, [message])
  useEffect(() => { load() }, [load])

  async function sync() {
    setBusy(true)
    try {
      await nas.sync()
      message.success(t('sync_success'))
      await load()
    } catch (e: any) {
      message.error(e?.message || 'sync failed')
    } finally {
      setBusy(false)
    }
  }

  // ---- NAS 配置（仅管理员）----
  // 归档目标、访问密钥、同步时间此前只能改环境变量并重启整套服务，
  // 而这些恰恰是交付现场才确定、且会随换机/轮换密钥而变的信息。
  const isAdmin = user?.role === 'admin'
  const [cfgOpen, setCfgOpen] = useState(false)
  const [cfgForm] = Form.useForm<NasConfig>()
  const [mode, setMode] = useState<'s3' | 'local'>('s3')
  const [testing, setTesting] = useState(false)

  async function openConfig() {
    try {
      const c = await nas.config()
      setMode(c.mode)
      // 密钥回来的是掩码，清空后展示占位提示，避免管理员误以为这就是真实值
      cfgForm.setFieldsValue({ ...c, secret_key: '' })
      setCfgOpen(true)
    } catch (e) {
      message.error(errMessage(e))
    }
  }

  async function testConfig() {
    const v = await cfgForm.validateFields().catch(() => null)
    if (!v) return
    setTesting(true)
    try {
      const r = await nas.testConfig(v)
      if (r.ok) message.success(r.detail)
      else message.error(r.detail)   // 原样展示后端原因：地址不通/密钥不对/桶不存在靠它区分
    } catch (e) {
      message.error(errMessage(e))
    } finally {
      setTesting(false)
    }
  }

  async function saveConfig() {
    const v = await cfgForm.validateFields().catch(() => null)
    if (!v) return
    if (await submitRun(() => nas.saveConfig(v), t('nas_cfg_saved'))) {
      setCfgOpen(false)
      load()   // 归档目标随即变化，状态卡片需要刷新
    }
  }

  if (!st) return null
  const canSync = user?.role === 'coo_reviewer' || user?.role === 'admin'

  return (
    <>
      <PageHeader title={t('nas')} desc={t('nas_desc')} />
      {/* 两张卡片上下排列：同步状态是结论、同步记录是明细，竖排读起来是自然顺序；
          并排时明细表被压在 14 栏里，列宽不够只能横向滚动 */}
      <Row gutter={[16, 16]}>
      <Col span={24}>
        <Card variant="borderless" className="coo-card" title={<span><DatabaseOutlined /> {t('sync_status')}</span>}
          extra={<Space>
            {isAdmin && <Button icon={<SettingOutlined />} onClick={openConfig}>{t('nas_config')}</Button>}
            {canSync && <Button type="primary" icon={<SyncOutlined />} loading={busy} onClick={sync}>{t('sync_now')}</Button>}
          </Space>}>
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div><Tag className="coo-tag" style={{ background: st.nas_reachable ? '#eaf2ec' : '#f9ece9', color: st.nas_reachable ? '#2f6b4a' : '#9c4134', border: 'none' }}>
              <span className="coo-dot" style={{ background: st.nas_reachable ? '#3f7d5c' : '#b04a3a' }} />
              {st.nas_reachable ? t('all_ok') : t('nas_unreachable')}
            </Tag></div>
            <div><b>{t('last_sync')}：</b>{st.last_sync ? `${formatTime(st.last_sync.started_at)} (${st.last_sync.success}/${st.last_sync.total})` : t('no_data')}</div>
            <div><b>{t('pending_sync')}：</b>{st.pending_count}</div>
            <div className="muted">NAS：{st.nas_root}</div>
          </Space>
        </Card>
      </Col>
      <Col span={24}>
        <Card variant="borderless" className="coo-card" title={t('sync_records')}>
          {/* 这张表原先整列漏出后端的原始英文枚举（auto/manual、success/partial/failed），
              还带一列数据库自增 ID——对使用者没有任何意义，反而看不出"昨晚那次到底成没成"。
              现在只留下四件事：什么时候、谁触发的、成没成、多少件。 */}
          <Table rowKey="id" size="small" pagination={{ defaultPageSize: 8, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100] }} dataSource={recs}
            // 列宽之和；窄屏下改为横向滚动，列宽不被挤压，字段就不会折行
            scroll={{ x: 540 }}
            columns={[
            { title: t('time'), dataIndex: 'started_at', width: 170, render: (v: string) => formatTime(v) },
            { title: t('sync_trigger'), dataIndex: 'run_type', width: 100, render: (v: string) => (v === 'manual' ? t('sync_manual') : t('sync_auto')) },
            { title: t('status'), dataIndex: 'status', width: 110, render: (s: string) => <Tag className="coo-tag" style={{ background: SYNC_STATUS_STYLE[s]?.bg ?? '#faf0dc', color: SYNC_STATUS_STYLE[s]?.fg ?? '#a67c1e', border: 'none' }}>{t(SYNC_STATUS_LABEL[s] ?? 'sync_running')}</Tag> },
            // 失败件数单独标红：只给 "128/130" 的话，差在哪、是不是该处理，用户得自己做减法
            { title: t('success_total'), width: 160, render: (_, r) => (
              <>
                {r.success}/{r.total}
                {r.failed > 0 && <Typography.Text type="danger">　{t('sync_failed_n', { n: r.failed })}</Typography.Text>}
              </>
            ) },
          ]} />
        </Card>
      </Col>
      </Row>

      <Modal title={t('nas_config')} open={cfgOpen} onOk={saveConfig} confirmLoading={submitting}
        onCancel={() => setCfgOpen(false)} okText={t('save')} cancelText={t('cancel')} width={560}
        destroyOnHidden
        footer={(_, { OkBtn, CancelBtn }) => (
          <Space>
            {/* 先试连再保存：否则改错地址要等到当晚自动同步失败才发现，
                而那意味着该归档的核查证据没有归档 */}
            <Button onClick={testConfig} loading={testing}>{t('nas_test')}</Button>
            <CancelBtn /><OkBtn />
          </Space>
        )}>
        <Form form={cfgForm} layout="vertical" onValuesChange={(c) => c.mode && setMode(c.mode)} onFinish={saveConfig}>
          <Form.Item name="mode" label={t('nas_mode')}>
            <Radio.Group optionType="button" buttonStyle="solid" options={[
              { label: t('nas_mode_s3'), value: 's3' },
              { label: t('nas_mode_local'), value: 'local' },
            ]} />
          </Form.Item>
          {mode === 's3' ? (
            <>
              <Form.Item name="endpoint_url" label={t('nas_endpoint')}
                rules={[{ required: true }, { max: 255 }]}>
                <Input placeholder="http://192.168.1.10:9000" />
              </Form.Item>
              <Row gutter={12}>
                <Col span={12}><Form.Item name="access_key" label={t('nas_access_key')} rules={[{ required: true }, { max: 128 }]}><Input /></Form.Item></Col>
                <Col span={12}><Form.Item name="secret_key" label={t('nas_secret_key')} rules={[{ max: 256 }]} extra={t('nas_secret_hint')}><Input.Password placeholder="********" /></Form.Item></Col>
              </Row>
              <Row gutter={12}>
                <Col span={12}><Form.Item name="bucket" label={t('nas_bucket')} rules={[{ required: true }, { max: 128 }]}><Input placeholder="coo-nas" /></Form.Item></Col>
                <Col span={8}><Form.Item name="region" label={t('nas_region')} rules={[{ max: 64 }]}><Input placeholder="us-east-1" /></Form.Item></Col>
                <Col span={4}><Form.Item name="use_ssl" label={t('nas_use_ssl')} valuePropName="checked"><Switch /></Form.Item></Col>
              </Row>
            </>
          ) : (
            <Form.Item name="local_root" label={t('nas_local_root')} rules={[{ required: true }, { max: 255 }]}>
              <Input placeholder="/app/data/nas" />
            </Form.Item>
          )}
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="sync_time" label={t('nas_sync_time')}
                rules={[{ required: true }, { pattern: /^([01]\d|2[0-3]):[0-5]\d$/, message: 'HH:MM' }]}>
                <Input placeholder="01:00" />
              </Form.Item>
            </Col>
            <Col span={12}><Form.Item name="auto_sync" label={t('nas_auto_sync')} valuePropName="checked"><Switch /></Form.Item></Col>
          </Row>
        <SubmitOnEnter /></Form>
      </Modal>
    </>
  )
}
