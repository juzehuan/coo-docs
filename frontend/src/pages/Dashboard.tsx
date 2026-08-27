import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { App, Button, Card, Col, Empty, Progress, Row, Table, Spin, Typography } from 'antd'
import { AuditOutlined, DownloadOutlined, EyeOutlined, FileDoneOutlined, FileSyncOutlined, InboxOutlined } from '@ant-design/icons'
import type { Lang } from '@/types'
import { errMessage } from '@/api/client'
import { dashboard } from '@/api/endpoints'
import { useAuth } from '@/store/AuthContext'
import { useI18n } from '@/i18n'
import { STATUS_LABELS } from '@/i18n/messages'
import { formatTime } from '@/utils/format'
import StatCard from '@/components/StatCard'
import StatusTag from '@/components/StatusTag'
import RowActions, { ActionButton } from '@/components/RowActions'
import { ELLIPSIS, actionWidth } from '@/utils/table'
import type { Dashboard as Dash } from '@/types'

export default function Dashboard() {
  const { t, lang } = useI18n()
  const nav = useNavigate()
  const { user } = useAuth()
  const { message } = App.useApp()
  const [d, setD] = useState<Dash | null>(null)
  // 导出角色与后端 export_viewer 一致：COO 终审人 / 审计查看人 / 管理员
  const canExport = ['coo_reviewer', 'auditor', 'admin'].includes(user?.role || '')
  async function exportArchive() {
    try {
      const blob = await dashboard.exportCsv()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'archive_list.xlsx'; a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      message.error(errMessage(e))
    }
  }

  useEffect(() => { dashboard.get().then(setD).catch(() => {}) }, [])

  if (!d) return <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>

  return (
    <div>
      <div className="coo-pagehead">
        <div>
          <h1 className="coo-pagehead-title">{t('dashboard')}</h1>
          <div className="coo-pagehead-desc">{t('dashboard_desc')}</div>
        </div>
        {/* F-10「归档清单可导出为 Excel/CSV」：后端接口一直存在但界面无入口。
            外面这层 coo-pagehead-extra 与 PageHeader 组件保持一致——窄屏页头改为上下
            堆叠，没有它按钮会被拉伸成占满整行。 */}
        {canExport && (
          <div className="coo-pagehead-extra">
            <Button icon={<DownloadOutlined />} onClick={exportArchive}>{t('export_csv')}</Button>
          </div>
        )}
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}><div className="coo-rise coo-rise-1"><StatCard title={t('progress')} value={d.package_completion} suffix="%" icon={<FileDoneOutlined />} color="#16263f" /></div></Col>
        <Col xs={12} md={6}><div className="coo-rise coo-rise-2"><StatCard title={t('pending_mine')} value={d.pending_mine} icon={<FileSyncOutlined />} color="#b97a1e" onClick={() => nav('/todo')} /></div></Col>
        <Col xs={12} md={6}><div className="coo-rise coo-rise-3"><StatCard title={t('released')} value={d.released} icon={<AuditOutlined />} color="#3f7d5c" /></div></Col>
        <Col xs={12} md={6}><div className="coo-rise coo-rise-4"><StatCard title={t('attachment')} value={d.total_attachments} icon={<InboxOutlined />} color="#a8833c" /></div></Col>
      </Row>

      {/* 同一行的两张卡片等高：Row 的 Col 本就会拉伸到同高，但 Card 默认只占内容
          高度，「重点关注」为空时缩成一条，与左边的完成度环差出一大截。
          coo-card-fill 让卡片和卡片体都撑满 Col，内容再在其中居中。 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} md={10}>
          <Card variant="borderless" className="coo-card coo-card-fill" title={t('progress')}
            styles={{ body: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' } }}>
            <Progress type="dashboard" percent={d.package_completion} strokeColor={{ '0%': '#a8833c', '100%': '#c9b06a' }} strokeWidth={10} />
            <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
              {t('released')} <b style={{ color: '#3f7d5c' }}>{d.released}</b> · {t('overdue')} <b style={{ color: d.overdue > 0 ? '#cf1322' : '#3f7d5c' }}>{d.overdue}</b>
            </Typography.Paragraph>
          </Card>
        </Col>
        <Col xs={24} md={14}>
          <Card variant="borderless" className="coo-card coo-card-fill" title={t('need_attention')}
            /* 空态时把卡片体变成居中容器；有表格时保持普通块级布局，免得表格被 flex 压窄 */
            styles={d.need_attention.length === 0
              ? { body: { display: 'flex', alignItems: 'center', justifyContent: 'center' } }
              : undefined}>
            {d.need_attention.length === 0
              /* 空态与待办页、通知页统一用 Empty：原先是一行小灰字，卡片直接塌下去 */
              ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('no_data')} style={{ margin: '24px 0' }} />
              : (
                <Table
                  rowKey={(_, i) => String(i)}
                  size="small" pagination={false}
                  dataSource={d.need_attention}
                  scroll={{ x: 680 }}
                  columns={[
                    { title: 'COO', dataIndex: 'code', width: 90 },
                    { title: t('packages'), dataIndex: 'name', width: 200, ellipsis: ELLIPSIS },
                    // 事项文案由前端按 issue_code 翻译：后端此前直接下发中文，
                    // 英文/泰文界面下这一列会整列漏出中文
                    { title: t('issue'), dataIndex: 'issue_code', width: 170, ellipsis: ELLIPSIS, render: (_: string, r) => (
                      <span style={{ color: r.overdue ? '#cf1322' : '#b97a1e', fontWeight: r.overdue ? 600 : 400 }}>
                        {r.issue_code === 'overdue'
                          ? `${t('overdue_issue')}${r.due_date ? `（${r.due_date}）` : ''}`
                          : STATUS_LABELS[r.issue_code]?.[lang as Lang] ?? r.issue_code}
                      </span>
                    ) },
                    { title: t('reject_reason'), dataIndex: 'reason', width: 220, ellipsis: ELLIPSIS, render: (v: string) => v || '-' },
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
          pagination={{ defaultPageSize: 8, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100] }}
          // 列宽之和；不够宽时整表横向滚动，列宽不被挤压，字段就不会折行
          scroll={{ x: 720 + actionWidth(1) }}
          columns={[
            { title: 'COO', dataIndex: 'code', width: 90 },
            { title: t('packages'), dataIndex: 'name', width: 240, ellipsis: ELLIPSIS, render: (v: string, r: { overdue?: boolean }) => (r.overdue ? <Typography.Text type="danger" strong>{v}（{t('overdue')}）</Typography.Text> : v) },
            { title: t('status'), dataIndex: 'status', width: 120, render: (s: string) => <StatusTag status={s} /> },
            {
              title: t('progress'), dataIndex: 'percent', width: 180,
              render: (p: number) => <Progress percent={p} size="small" strokeColor="#a8833c" />,
            },
            { title: t('attachment'), dataIndex: 'attachments', width: 90, render: (n: number) => `${n}` },
            // 与其他列表页一致：行内操作一律用小号图标按钮，不再用裸链接
            { title: t('actions'), key: 'act', width: actionWidth(1), fixed: 'right', render: () => (
              <RowActions>
                <ActionButton label={t('detail')} icon={<EyeOutlined />} onClick={() => nav('/packages')} />
              </RowActions>
            ) },
          ]}
        />
      </Card>
    </div>
  )
}
