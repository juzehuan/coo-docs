import { useState } from 'react'
import { App, Button, Input, Space, Table, Tag, Tooltip, Upload, Typography } from 'antd'
import { DeleteOutlined, DownloadOutlined, EyeOutlined, InboxOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { packages } from '@/api/endpoints'
import { useI18n } from '@/i18n'
import { formatSize, formatTime } from '@/utils/format'
import type { Attachment } from '@/types'

const { Dragger } = Upload

interface Props {
  pkgId: string
  version: { id: string; attachments: Attachment[] }
  canEdit: boolean
  onChanged: () => void
}

const PREVIEW_TYPES = ['application/pdf', 'image/png', 'image/jpeg', 'image/gif', 'image/bmp', 'image/webp']

export default function AttachmentList({ pkgId, version, canEdit, onChanged }: Props) {
  const { t } = useI18n()
  const { message } = App.useApp()
  const [orderNo, setOrderNo] = useState('')
  const [batchNo, setBatchNo] = useState('')
  const [uploading, setUploading] = useState(false)

  const atts = version.attachments

  const columns: ColumnsType<Attachment> = [
    {
      title: t('attachment'),
      dataIndex: 'original_name',
      render: (name: string, r) => (
        <a onClick={() => window.open(packages.attachmentUrl(pkgId, version.id, r.id, false), '_blank')}>{name}</a>
      ),
    },
    { title: t('order_no'), dataIndex: 'order_no', render: (v) => v || '-' },
    { title: t('batch_no'), dataIndex: 'batch_no', render: (v) => v || '-' },
    { title: 'MD5', dataIndex: 'md5', ellipsis: true, render: (v) => <Typography.Text copyable={{ text: v }} style={{ fontSize: 12 }}>{v.slice(0, 12)}…</Typography.Text> },
    { title: 'NAS', dataIndex: 'nas_synced', width: 70, render: (s: boolean) => (s ? <Tag color="green">✓</Tag> : <Tag color="gold">⏳</Tag>) },
    { title: t('status'), dataIndex: 'uploaded_at', width: 160, render: (v) => formatTime(v) },
    {
      title: '', key: 'act', width: 120,
      render: (_, r) => (
        <Space>
          <Tooltip title={t('detail')}><Button size="small" icon={<EyeOutlined />} onClick={() => { if (PREVIEW_TYPES.includes(r.mime_type)) window.open(packages.attachmentUrl(pkgId, version.id, r.id, true), '_blank'); else window.open(packages.attachmentUrl(pkgId, version.id, r.id, false), '_blank') }} /></Tooltip>
          <Tooltip title="下载"><Button size="small" icon={<DownloadOutlined />} onClick={() => window.open(packages.attachmentUrl(pkgId, version.id, r.id, false), '_blank')} /></Tooltip>
          {canEdit && <Tooltip title={t('cancel')}><Button size="small" danger icon={<DeleteOutlined />} onClick={async () => { await packages.deleteAttachment(pkgId, version.id, r.id); message.success('已删除'); onChanged() }} /></Tooltip>}
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Table rowKey="id" size="middle" pagination={false} columns={columns} dataSource={atts} locale={{ emptyText: t('no_data') }} />

      {canEdit && (
        <div style={{ marginTop: 16, padding: 16, background: '#fafcff', border: '1px dashed #dfe6f0', borderRadius: 8 }}>
          <Space style={{ marginBottom: 12 }}>
            <Input addonBefore={t('order_no')} value={orderNo} onChange={(e) => setOrderNo(e.target.value)} style={{ width: 220 }} />
            <Input addonBefore={t('batch_no')} value={batchNo} onChange={(e) => setBatchNo(e.target.value)} style={{ width: 220 }} />
          </Space>
          <Dragger
            multiple
            showUploadList={false}
            beforeUpload={() => false}
            disabled={uploading}
            onChange={async (info) => {
              const files = info.fileList.map((f) => f.originFileObj as File).filter(Boolean)
              if (!files.length) return
              setUploading(true)
              try {
                await packages.uploadAttachments(pkgId, version.id, files, orderNo, batchNo)
                message.success(`已上传 ${files.length} 个文件`)
                setOrderNo(''); setBatchNo('')
                onChanged()
              } catch (e: any) {
                message.error(e?.message || '上传失败')
              } finally {
                setUploading(false)
              }
            }}
          >
            <p className="ant-upload-drag-icon"><InboxOutlined /></p>
            <p className="ant-upload-text">{t('upload')}</p>
          </Dragger>
        </div>
      )}
    </div>
  )
}
