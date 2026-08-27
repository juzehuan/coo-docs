import { useEffect, useState } from 'react'
import { App, Button, Card, Table, Tag, Typography } from 'antd'
import { DownloadOutlined, LockOutlined } from '@ant-design/icons'
import { errMessage } from '@/api/client'
import { controlled, orders, packages } from '@/api/endpoints'
import { useI18n } from '@/i18n'
import { formatSize, formatTime } from '@/utils/format'
import AttachmentPreview from '@/components/LazyAttachmentPreview'
import StatusTag from '@/components/StatusTag'
import PageHeader from '@/components/PageHeader'
import RowActions from '@/components/RowActions'
import { ELLIPSIS } from '@/utils/table'
import type { ControlledItem } from '@/types'

const PAGE_SIZE = 20

export default function Controlled() {
  const { t } = useI18n()
  const { message } = App.useApp()
  const [rows, setRows] = useState<ControlledItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [preview, setPreview] = useState<{ url: string; name: string } | null>(null)

  useEffect(() => {
    // 服务端分页：受控内容随放行永久增长，不能一次性全量下发
    setLoading(true)
    // 失败要提示：空表格会被误读为"没有已放行资料"，掩盖真正的加载失败
    controlled.list(PAGE_SIZE, (page - 1) * PAGE_SIZE)
      .then((d) => { setRows(d.items); setTotal(d.total) })
      .catch((e) => { setRows([]); setTotal(0); message.error(errMessage(e)) })
      .finally(() => setLoading(false))
  }, [page, message])

  function downloadZip(r: ControlledItem) {
    const name = `controlled_${r.package_code}_${r.subject}.zip`
    const p = r.kind === 'order'
      ? controlled.exportOrderZip(r.ids.order_id!, r.ids.op_id!, name)
      : controlled.exportZip(r.ids.pkg_id!, r.ids.version_id!, name)
    p.then(() => message.success(t('export_zip')))
      .catch((e) => message.error(errMessage(e)))
  }

  /** 附件预览地址按所属线选择：两条线的附件端点不同。 */
  function attUrl(r: ControlledItem, aid: string) {
    return r.kind === 'order'
      ? orders.attachmentUrl(r.ids.order_id!, r.ids.op_id!, aid, true)
      : packages.attachmentUrl(r.ids.pkg_id!, r.ids.version_id!, aid, true)
  }

  return (
    <>
      <PageHeader title={t('controlled')} desc={t('controlled_desc')} />
      <Card variant="borderless" className="coo-card">
      <Table
        rowKey={(r) => r.key}
        loading={loading}
        dataSource={rows}
        pagination={{ current: page, pageSize: PAGE_SIZE, total, showSizeChanger: false, onChange: setPage,
          showTotal: (n) => t('audit_total').replace('{total}', String(n)) }}
        expandable={{
          expandedRowRender: (r) => {
            const atts = r.attachments || []
            if (!atts.length) return <Typography.Text type="secondary">{t('no_data')}</Typography.Text>
            return (
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                dataSource={atts}
                scroll={{ x: 640 }}
                columns={[
                  // 文件名单独成串（不再前置图标）：ellipsis 的悬浮提示只认字符串内容，
                  // 且与附件列表、订单详情里的文件名链接保持同一样式
                  { title: t('attachment'), width: 240, ellipsis: ELLIPSIS, render: (_, a) => (
                    <a onClick={() => setPreview({ url: attUrl(r, a.id), name: a.original_name || a.file_name })}>
                      {a.original_name || a.file_name}
                    </a>
                  ) },
                  { title: t('batch_no'), dataIndex: 'batch_no', width: 120, render: (x: string) => x || '-' },
                  { title: t('size'), width: 110, render: (_, a) => formatSize(a.file_size) },
                  { title: t('time'), dataIndex: 'uploaded_at', width: 170, render: (x: string) => formatTime(x) },
                ]}
              />
            )
          },
        }}
        // 列宽之和（含展开列）；不够宽时整表横向滚动，列宽不被挤压，字段就不会折行
        scroll={{ x: 1040 }}
        columns={[
          { title: 'COO', dataIndex: 'package_code', width: 90 },
          { title: t('packages'), dataIndex: 'package_name', width: 240, ellipsis: ELLIPSIS },
          { title: t('kind'), dataIndex: 'kind', width: 100,
            render: (k: string) => <Tag className="coo-tag" style={{ background: k === 'order' ? '#eef2f8' : '#f6f1e6', color: k === 'order' ? '#2f4a6b' : '#8a6a1e', border: 'none' }}>{k === 'order' ? t('kind_order') : t('kind_version')}</Tag> },
          { title: t('version'), dataIndex: 'subject', width: 150, ellipsis: ELLIPSIS },
          { title: t('status'), width: 110, render: () => <StatusTag status="released" /> },
          { title: t('attachment'), dataIndex: 'attachment_count', width: 90 },
          { title: t('locked'), key: 'lock', width: 80, render: () => <Tag className="coo-tag" style={{ background: '#eaf2ec', color: '#2f6b4a', border: 'none' }}><LockOutlined /></Tag> },
          { title: t('actions'), key: 'act', width: 130, fixed: 'right', render: (_, r) => (
            <RowActions>
              <Button size="small" icon={<DownloadOutlined />} disabled={!r.attachment_count} onClick={() => downloadZip(r)}>{t('export_zip')}</Button>
            </RowActions>
          ) },
        ]}
      />

      <AttachmentPreview open={!!preview} url={preview?.url ?? ''} name={preview?.name ?? ''} onClose={() => setPreview(null)} />
      </Card>
    </>
  )
}