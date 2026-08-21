import { useState } from 'react'
import { App, Button, Input, Space, Table, Tag, Typography, Upload } from 'antd'
import { DeleteOutlined, DownloadOutlined, EyeOutlined, InboxOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { downloadFile } from '@/api/client'
import { packages } from '@/api/endpoints'
import { useI18n } from '@/i18n'
import { formatSize, formatTime } from '@/utils/format'
import type { Attachment } from '@/types'
import AttachmentPreview from '@/components/AttachmentPreview'

const { Dragger } = Upload

interface Props {
  pkgId: string
  version: { id: string; attachments: Attachment[] }
  canEdit: boolean
  onChanged: () => void
}

export default function AttachmentList({ pkgId, version, canEdit, onChanged }: Props) {
  const { t } = useI18n()
  const { message } = App.useApp()
  const [orderNo, setOrderNo] = useState('')
  const [batchNo, setBatchNo] = useState('')
  const [uploading, setUploading] = useState(false)
  const [preview, setPreview] = useState<{ url: string; name: string } | null>(null)

  const atts = version.attachments

  const openPreview = (r: Attachment) => setPreview({ url: packages.attachmentUrl(pkgId, version.id, r.id, true), name: r.original_name || r.file_name })

  const columns: ColumnsType<Attachment> = [
    {
      title: t('attachment'),
      dataIndex: 'original_name',
      render: (name: string, r) => (
        <a onClick={() => openPreview(r)}>{name}</a>
      ),
    },
    { title: t('order_no'), dataIndex: 'order_no', render: (v) => v || '-' },
    { title: t('batch_no'), dataIndex: 'batch_no', render: (v) => v || '-' },
    { title: 'MD5', dataIndex: 'md5', ellipsis: true, render: (v) => <Typography.Text copyable={{ text: v }} style={{ fontSize: 12 }}>{v.slice(0, 12)}…</Typography.Text> },
    { title: 'NAS', dataIndex: 'nas_synced', width: 70, render: (s: boolean) => (s
      ? <Tag className="coo-tag" style={{ background: '#eaf2ec', color: '#2f6b4a', border: 'none' }}>✓</Tag>
      : <Tag className="coo-tag" style={{ background: '#faf0dc', color: '#a67c1e', border: 'none' }}>⏳</Tag>) },
    { title: t('upload_time'), dataIndex: 'uploaded_at', width: 160, render: (v) => formatTime(v) },
    {
      title: '', key: 'act', width: 200,
      render: (_, r) => (
        <Space size={4}>
          <Button size="small" icon={<EyeOutlined />} onClick={() => openPreview(r)}>{t('detail')}</Button>
          <Button size="small" icon={<DownloadOutlined />} onClick={() => downloadFile(packages.attachmentUrl(pkgId, version.id, r.id, false), r.original_name || r.file_name)}>下载</Button>
          {canEdit && <Button size="small" danger icon={<DeleteOutlined />} onClick={async () => { await packages.deleteAttachment(pkgId, version.id, r.id); message.success('已删除'); onChanged() }}>{t('cancel')}</Button>}
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Table rowKey="id" size="middle" pagination={false} columns={columns} dataSource={atts} locale={{ emptyText: t('no_data') }} />

      {canEdit && (
        <div style={{ marginTop: 16, padding: 16, background: '#faf6ec', border: '1px dashed #d8cdb0', borderRadius: 8 }}>
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

      <AttachmentPreview open={!!preview} url={preview?.url ?? ''} name={preview?.name ?? ''} onClose={() => setPreview(null)} />
    </div>
  )
}
