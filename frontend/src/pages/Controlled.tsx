import { useEffect, useState } from 'react'
import { App, Button, Card, Space, Table, Tag, Typography } from 'antd'
import { DownloadOutlined, FileOutlined, LockOutlined } from '@ant-design/icons'
import { controlled, packages } from '@/api/endpoints'
import { useI18n } from '@/i18n'
import { formatSize, formatTime } from '@/utils/format'
import AttachmentPreview from '@/components/AttachmentPreview'
import StatusTag from '@/components/StatusTag'
import PageHeader from '@/components/PageHeader'
import type { ControlledItem } from '@/types'

export default function Controlled() {
  const { t } = useI18n()
  const { message } = App.useApp()
  const [rows, setRows] = useState<ControlledItem[]>([])
  const [loading, setLoading] = useState(true)
  const [preview, setPreview] = useState<{ url: string; name: string } | null>(null)

  useEffect(() => {
    controlled.list().then(setRows).catch(() => setRows([])).finally(() => setLoading(false))
  }, [])

  function downloadZip(r: ControlledItem) {
    const v = r.version
    controlled.exportZip(v.package_id, v.id, `controlled_${r.package_code}_${v.version_no}.zip`)
      .then(() => message.success(t('export_zip')))
      .catch((e: any) => message.error(e?.message || '下载失败'))
  }

  return (
    <>
      <PageHeader title={t('controlled')} desc={t('controlled_desc')} />
      <Card variant="borderless" className="coo-card">
      <Table
        rowKey={(r) => r.version.id}
        loading={loading}
        dataSource={rows}
        pagination={{ pageSize: 10 }}
        expandable={{
          expandedRowRender: (r) => {
            const v = r.version
            const atts = v.attachments || []
            if (!atts.length) return <Typography.Text type="secondary">{t('no_data')}</Typography.Text>
            return (
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                dataSource={atts}
                columns={[
                  { title: t('attachment'), render: (_, a) => (
                    <a onClick={() => setPreview({ url: packages.attachmentUrl(v.package_id, v.id, a.id, true), name: a.original_name || a.file_name })}>
                      <FileOutlined /> {a.original_name || a.file_name}
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
        columns={[
          { title: 'COO', dataIndex: 'package_code', width: 90 },
          { title: t('packages'), dataIndex: 'package_name' },
          { title: t('version'), dataIndex: ['version', 'version_no'], width: 90 },
          { title: t('status'), width: 110, render: () => <StatusTag status="released" /> },
          { title: t('attachment'), dataIndex: 'attachment_count', width: 90 },
          { title: '', key: 'lock', width: 60, render: () => <Tag className="coo-tag" style={{ background: '#eaf2ec', color: '#2f6b4a', border: 'none' }}><LockOutlined /></Tag> },
          { title: '', key: 'act', width: 150, render: (_, r) => (
            <Space>
              <Button size="small" icon={<DownloadOutlined />} disabled={!r.attachment_count} onClick={() => downloadZip(r)}>{t('export_zip')}</Button>
            </Space>
          ) },
        ]}
      />

      <AttachmentPreview open={!!preview} url={preview?.url ?? ''} name={preview?.name ?? ''} onClose={() => setPreview(null)} />
      </Card>
    </>
  )
}