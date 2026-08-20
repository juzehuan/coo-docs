import { useCallback, useEffect, useState } from 'react'
import { App, Button, Card, Col, Row, Space, Table, Tag } from 'antd'
import { DatabaseOutlined, SyncOutlined } from '@ant-design/icons'
import { nas } from '@/api/endpoints'
import { useAuth } from '@/store/AuthContext'
import { useI18n } from '@/i18n'
import { formatTime } from '@/utils/format'
import type { NasStatus, SyncRecord } from '@/types'

export default function Nas() {
  const { t } = useI18n()
  const { user } = useAuth()
  const { message } = App.useApp()
  const [st, setSt] = useState<NasStatus | null>(null)
  const [recs, setRecs] = useState<SyncRecord[]>([])
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    const [s, r] = await Promise.all([nas.status(), nas.records()])
    setSt(s); setRecs(r)
  }, [])
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

  if (!st) return null
  const canSync = user?.role === 'coo_reviewer' || user?.role === 'admin'

  return (
    <Row gutter={16}>
      <Col xs={24} md={10}>
        <Card variant="borderless" title={<span><DatabaseOutlined /> {t('sync_status')}</span>}
          extra={canSync && <Button type="primary" icon={<SyncOutlined />} loading={busy} onClick={sync}>{t('sync_now')}</Button>}>
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div><Tag color={st.nas_reachable ? 'green' : 'red'}>{st.nas_reachable ? t('all_ok') : t('nas_unreachable')}</Tag></div>
            <div><b>{t('last_sync')}：</b>{st.last_sync ? `${formatTime(st.last_sync.started_at)} (${st.last_sync.success}/${st.last_sync.total})` : t('no_data')}</div>
            <div><b>{t('pending_sync')}：</b>{st.pending_count}</div>
            <div className="muted">NAS：{st.nas_root}</div>
          </Space>
        </Card>
      </Col>
      <Col xs={24} md={14}>
        <Card variant="borderless" title={t('sync_status')}>
          <Table rowKey="id" size="small" pagination={{ pageSize: 8 }} dataSource={recs} columns={[
            { title: 'ID', dataIndex: 'id', width: 70 },
            { title: '类型', dataIndex: 'run_type', width: 90 },
            { title: '成功/总数', render: (_, r) => `${r.success}/${r.total}`, width: 110 },
            { title: t('status'), dataIndex: 'status', width: 100, render: (s: string) => <Tag color={s === 'success' ? 'green' : s === 'failed' ? 'red' : 'gold'}>{s}</Tag> },
            { title: '时间', dataIndex: 'started_at', render: (v: string) => formatTime(v) },
          ]} />
        </Card>
      </Col>
    </Row>
  )
}
