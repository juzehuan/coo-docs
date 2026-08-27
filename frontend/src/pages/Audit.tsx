import { useEffect, useState } from 'react'
import { Alert, App, Button, Card, DatePicker, Input, Select, Space, Table } from 'antd'
import { DownloadOutlined, SearchOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import type { Dayjs } from 'dayjs'
import { errMessage } from '@/api/client'
import { audit } from '@/api/endpoints'
import { useAuth } from '@/store/AuthContext'
import { useI18n } from '@/i18n'
import { formatTime } from '@/utils/format'
import PageHeader from '@/components/PageHeader'
import { ELLIPSIS } from '@/utils/table'
import type { AuditLog, AuditQuery } from '@/types'

const DOMAINS = ['auth', 'package', 'attachment', 'review', 'version', 'nas', 'export', 'org']

// 单次拉取上限；命中数超过它时界面会明确提示，而不是让用户以为看到了全部
const LIST_LIMIT = 1000

export default function Audit() {
  const { t } = useI18n()
  const { user } = useAuth()
  const { message } = App.useApp()
  const [logs, setLogs] = useState<AuditLog[]>([])
  // total 是命中总数（可能大于本次返回的条数）：只给一页数据时，界面无从区分
  // "确实没有更多记录"与"被上限截断了"，而审计场景这两者结论完全相反
  const [total, setTotal] = useState(0)
  const [domain, setDomain] = useState<string | undefined>()
  const [actor, setActor] = useState('')
  const [target, setTarget] = useState('')
  // 默认只看最近 90 天，而不是全量。
  //
  // 理由是成本：审计日志按三年保留规划，全量导出可达 10 万行（MAX_EXPORT_ROWS），
  // 第 55 轮实测那个量级要 36 秒 CPU；而这套是单进程部署，第 79 轮压测显示
  // 并发重导出超过约 5 个全站就对普通用户不可用。日常审计工作绝大多数只看近期，
  // 让默认查询便宜一个数量级，导出名额（core/heavy.py）也能更快周转。
  //
  // **默认值放在这里而不是后端**：后端加默认会变成"看不见的截断"——用户看到
  // 空列表会以为没有记录，而这套系统反复吃过这种亏（静默截断与确实没有，
  // 结论完全相反）。放进日期控件后窗口是**显式可见**的，用户一眼看到、
  // 也能随手清空取全量；后端行为完全不变（不传日期就是全量），API 调用方不受影响。
  const [range, setRange] = useState<[Dayjs | null, Dayjs | null] | null>(
    [dayjs().subtract(90, 'day'), dayjs()],
  )
  const [loading, setLoading] = useState(true)

  // d：undefined = 用当前 state；null = 明确清除（Select 的 allowClear 触发时 state 尚未更新）
  // 当前筛选条件：列表与导出共用同一份，避免"导出的内容和屏幕上不一样"
  const query = (d?: string | null): AuditQuery => ({
    domain: d === null ? undefined : (d ?? domain),
    actor: actor.trim() || undefined,
    target: target.trim() || undefined,
    start: range?.[0]?.format('YYYY-MM-DD') || undefined,
    end: range?.[1]?.format('YYYY-MM-DD') || undefined,
  })

  const load = (d?: string | null) => {
    setLoading(true)
    audit.list({ ...query(d), limit: LIST_LIMIT })
      .then((r) => { setLogs(r.items); setTotal(r.total) })
      .catch((e) => { setLogs([]); setTotal(0); message.error(errMessage(e)) })   // 空列表不等于无日志，失败要说清楚
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  async function exportXlsx() {
    try {
      const blob = await audit.exportXlsx(query())
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'audit_logs.xlsx'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e: any) {
      message.error(errMessage(e))
    }
  }

  const canExport = user?.role === 'auditor' || user?.role === 'admin'

  return (
    <>
      <PageHeader
        title={t('audit')}
        desc={t('audit_desc')}
        extra={
          <Space wrap>
            <Input allowClear placeholder={t('operator')} style={{ width: 130 }} value={actor}
              onChange={(e) => setActor(e.target.value)} onPressEnter={() => load()} />
            <Input allowClear placeholder={t('target')} style={{ width: 170 }} value={target}
              onChange={(e) => setTarget(e.target.value)} onPressEnter={() => load()} />
            <DatePicker.RangePicker value={range} onChange={(v) => setRange(v)} allowEmpty={[true, true]} />
            <Select allowClear placeholder={t('domain_action')} style={{ width: 140 }} value={domain} onChange={(v) => { setDomain(v); load(v ?? null) }}
              options={DOMAINS.map((d) => ({ label: d, value: d }))} />
            <Button icon={<SearchOutlined />} onClick={() => load()}>{t('search')}</Button>
            {canExport && <Button icon={<DownloadOutlined />} onClick={exportXlsx}>{t('export_csv')}</Button>}
          </Space>
        }
      />
      <Card variant="borderless" className="coo-card">
      {/* 命中数超过单次上限时必须说清楚：否则"没有更多记录"与"被截断了"
          在界面上长得一模一样，而审计场景两者结论完全相反 */}
      {total > logs.length && (
        <Alert type="warning" showIcon style={{ marginBottom: 12 }}
          message={t('audit_truncated').replace('{shown}', String(logs.length)).replace('{total}', String(total))} />
      )}
      <Table
        rowKey="id"
        loading={loading}
        dataSource={logs}
        pagination={{ defaultPageSize: 15, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100] }}
        // 列宽之和；不够宽时整表横向滚动，列宽不被挤压，字段就不会折行
        scroll={{ x: 1160 }}
        columns={[
          { title: t('time'), dataIndex: 'created_at', width: 170, render: (v: string) => formatTime(v) },
          { title: t('domain_action'), render: (_, r) => `${r.event_domain}.${r.action}`, width: 200, ellipsis: ELLIPSIS },
          { title: t('operator'), dataIndex: 'actor_name', width: 120, ellipsis: ELLIPSIS },
          { title: t('ip'), dataIndex: 'ip', width: 130 },
          // target/detail 是审计里最长的两列（含路径与变更摘要），截断后悬浮看全文
          { title: t('target'), dataIndex: 'target', width: 220, ellipsis: ELLIPSIS },
          { title: t('desc'), dataIndex: 'detail', width: 320, ellipsis: ELLIPSIS },
        ]}
      />
      </Card>
    </>
  )
}
