import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Col, Progress, Row, Table, Spin, Typography } from 'antd'
import { AuditOutlined, FileDoneOutlined, FileSyncOutlined, InboxOutlined } from '@ant-design/icons'
import { dashboard } from '@/api/endpoints'
import { useI18n } from '@/i18n'
import { STATUS_LABELS } from '@/i18n/messages'
import { formatTime } from '@/utils/format'
import StatCard from '@/components/StatCard'
import StatusTag from '@/components/StatusTag'
import type { Dashboard as Dash } from '@/types'

export default function Dashboard() {
  const { t, lang } = useI18n()
  const nav = useNavigate()
  const [d, setD] = useState<Dash | null>(null)

  useEffect(() => { dashboard.get().then(setD).catch(() => {}) }, [])

  if (!d) return <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>

  return (
    <div>
      <div className="coo-pagehead">
        <div>
          <h1 className="coo-pagehead-title">{t('dashboard')}</h1>
          <div className="coo-pagehead-desc">{t('dashboard_desc')}</div>
        </div>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}><StatCard title={t('progress')} value={d.package_completion} suffix="%" icon={<FileDoneOutlined />} color="#1f5fa8" /></Col>
        <Col xs={12} md={6}><StatCard title={t('pending_mine')} value={d.pending_mine} icon={<FileSyncOutlined />} color="#d97706" onClick={() => nav('/todo')} /></Col>
        <Col xs={12} md={6}><StatCard title={t('released')} value={d.released} icon={<AuditOutlined />} color="#16a34a" /></Col>
        <Col xs={12} md={6}><StatCard title={t('attachment')} value={d.total_attachments} icon={<InboxOutlined />} color="#7c3aed" /></Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} md={10}>
          <Card variant="borderless" className="coo-card" title={t('progress')}>
            <Progress type="dashboard" percent={d.package_completion} strokeColor={{ '0%': '#1f5fa8', '100%': '#2f7fd6' }} strokeWidth={10} />
            <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
              {t('released')} <b style={{ color: '#16a34a' }}>{d.released}</b> · {t('overdue')} <b style={{ color: '#d97706' }}>{d.overdue}</b>
            </Typography.Paragraph>
          </Card>
        </Col>
        <Col xs={24} md={14}>
          <Card variant="borderless" className="coo-card" title={t('need_attention')}>
            {d.need_attention.length === 0
              ? <Typography.Text type="secondary">{t('no_data')}</Typography.Text>
              : (
                <Table
                  rowKey={(_, i) => String(i)}
                  size="small" pagination={false}
                  dataSource={d.need_attention}
                  columns={[
                    { title: 'COO', dataIndex: 'code', width: 90 },
                    { title: t('packages'), dataIndex: 'name' },
                    { title: t('issue') ?? '事项', dataIndex: 'issue', width: 130, render: (v: string) => <span style={{ color: '#d97706' }}>{v}</span> },
                    { title: t('reject_reason'), dataIndex: 'reason', render: (v: string) => v || '-' },
                  ]}
                />
              )}
          </Card>
        </Col>
      </Row>

      <Card variant="borderless" className="coo-card" title={t('packages')} style={{ marginTop: 16 }}>
        <Table
          rowKey="code"
          dataSource={d.package_progress}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: 'COO', dataIndex: 'code', width: 90 },
            { title: t('packages'), dataIndex: 'name' },
            { title: t('status'), dataIndex: 'status', width: 120, render: (s: string) => <StatusTag status={s} /> },
            {
              title: t('progress'), dataIndex: 'percent', width: 180,
              render: (p: number) => <Progress percent={p} size="small" strokeColor="#1f5fa8" />,
            },
            { title: t('attachment'), dataIndex: 'attachments', width: 90, render: (n: number) => `${n}` },
            { title: '', key: 'act', width: 80, render: (_, r) => <a onClick={() => nav('/packages')}>{t('detail')}</a> },
          ]}
        />
      </Card>
    </div>
  )
}
