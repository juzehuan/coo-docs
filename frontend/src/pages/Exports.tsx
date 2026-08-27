import { useCallback, useEffect, useRef, useState } from 'react'
import { App, Button, Card, Popconfirm, Space, Table, Tag, Typography } from 'antd'
import { DeleteOutlined, DownloadOutlined, ReloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'

import { downloadFile, errMessage } from '@/api/client'
import { exportJobs } from '@/api/endpoints'
import PageHeader from '@/components/PageHeader'
import { useI18n } from '@/i18n'
import type { ExportJob } from '@/types'
import { formatTime } from '@/utils/format'

const STATUS_TAG: Record<string, { color: string; key: string }> = {
  pending: { color: 'default', key: 'export_pending' },
  running: { color: 'processing', key: 'export_running' },
  done: { color: 'success', key: 'export_done' },
  failed: { color: 'error', key: 'export_failed' },
}

/** 我的导出。
 *
 * 为什么需要这个页面：导出在名额已满时会转为后台作业（见 utils/exportOrQueue.ts），
 * 若没有一个能看到结果的地方，用户提交完就无从得知去哪儿取——第 64 轮的教训是
 * "能力做好了却没有入口等于没做"。因此它同时出现在侧边菜单里，
 * 而不是只靠完成通知的链接。
 */
export default function Exports() {
  const { t } = useI18n()
  const { message } = App.useApp()
  const [rows, setRows] = useState<ExportJob[]>([])
  const [loading, setLoading] = useState(true)
  const timer = useRef<number | null>(null)

  const load = useCallback(() => {
    exportJobs.list()
      .then(setRows)
      .catch((e) => message.error(errMessage(e)))
      .finally(() => setLoading(false))
  }, [message])

  useEffect(() => {
    load()
    // 有作业未完成时才轮询：全部完成后停下来，不做无谓请求
    timer.current = window.setInterval(() => {
      setRows((cur) => {
        if (cur.some((r) => r.status === 'pending' || r.status === 'running')) load()
        return cur
      })
    }, 3000)
    return () => { if (timer.current) window.clearInterval(timer.current) }
  }, [load])

  function remove(id: string) {
    exportJobs.remove(id)
      .then(() => { message.success(t('deleted')); load() })
      .catch((e) => message.error(errMessage(e)))
  }

  const columns: ColumnsType<ExportJob> = [
    { title: t('type'), dataIndex: 'kind', width: 190, render: (v: string) => t(`export_kind_${v}`) || v },
    {
      title: t('status'), dataIndex: 'status', width: 110,
      render: (v: string) => {
        const c = STATUS_TAG[v] || { color: 'default', key: v }
        return <Tag color={c.color}>{t(c.key) || v}</Tag>
      },
    },
    { title: t('export_file'), dataIndex: 'file_name', ellipsis: true, render: (v: string) => v || '-' },
    {
      title: t('size'), dataIndex: 'file_size', width: 110,
      render: (v: number) => (v ? `${(v / 1024).toFixed(1)} KB` : '-'),
    },
    { title: t('submit_time'), dataIndex: 'created_at', width: 170, render: (v: string) => (v ? formatTime(v) : '-') },
    {
      // 失败原因必须显示出来：只标一个"失败"等于让用户重试到放弃。
      // 用独立词条而不是复用 reject_reason（那是审核退回的语义，不是导出失败）
      title: t('export_error'), dataIndex: 'error', ellipsis: true,
      // 只有失败才标红：排队中的"服务重启已自动重排"是说明，不是错误
      render: (v: string, r) => (v ? <Typography.Text type={r.status === 'failed' ? 'danger' : 'secondary'}>{v}</Typography.Text> : '-'),
    },
    {
      title: '', key: 'act', width: 130, fixed: 'right',
      render: (_, r) => (
        <Space size={4}>
          {/* 换票后走浏览器原生下载：纯 <a href> 带不了 Bearer 头（第 87 轮实测 401） */}
          <Button size="small" type="primary" ghost icon={<DownloadOutlined />}
            disabled={r.status !== 'done'}
            onClick={() => downloadFile(exportJobs.downloadUrl(r.id), r.file_name, exportJobs.ticketUrl(r.id))
              .catch((e) => message.error(errMessage(e)))} />
          <Popconfirm title={t('export_confirm_delete')} onConfirm={() => remove(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <PageHeader title={t('my_exports')} extra={
        <Button icon={<ReloadOutlined />} onClick={load}>{t('export_refresh')}</Button>} />
      <Card>
        <Table rowKey="id" size="small" loading={loading} columns={columns} dataSource={rows}
          pagination={false} scroll={{ x: 'max-content' }} />
      </Card>
    </div>
  )
}
