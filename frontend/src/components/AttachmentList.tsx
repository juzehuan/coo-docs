import { useState } from 'react'
import { App, Button, Input, Space, Table, Tag, Typography, Upload } from 'antd'
import { DeleteOutlined, DownloadOutlined, EyeOutlined, InboxOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { downloadFile, errMessage } from '@/api/client'
import { packages } from '@/api/endpoints'
import { useI18n } from '@/i18n'
import { formatSize, formatTime } from '@/utils/format'
import type { Attachment } from '@/types'
import AttachmentPreview from '@/components/LazyAttachmentPreview'

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

  async function doUpload(files: File[]) {
    if (!files.length || uploading) return
    setUploading(true)
    try {
      await packages.uploadAttachments(pkgId, version.id, files, orderNo, batchNo)
      message.success(t('uploaded_n', { n: files.length }))
      setOrderNo(''); setBatchNo('')
      onChanged()
    } catch (e) {
      message.error(errMessage(e))
    } finally {
      setUploading(false)
    }
  }

  async function removeAtt(r: Attachment) {
    try {
      await packages.deleteAttachment(pkgId, version.id, r.id)
      message.success(t('deleted'))
      onChanged()
    } catch (e) {
      message.error(errMessage(e))   // 如"已放行版本不可修改"，原先静默失败
    }
  }

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
          <Button size="small" icon={<DownloadOutlined />} onClick={() => downloadFile(packages.attachmentUrl(pkgId, version.id, r.id, false), r.original_name || r.file_name)}>{t('download')}</Button>
          {canEdit && <Button size="small" danger icon={<DeleteOutlined />} onClick={() => removeAtt(r)}>{t('cancel')}</Button>}
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
            disabled={uploading}
            // 受控为空，防止 antd 内部 fileList 跨批次累积
            fileList={[]}
            // antd 对每个选中文件各调一次 beforeUpload，第二参数为本批全部文件；
            // 只在最后一个文件时整批上传一次。原先用 onChange 会按累积列表重复提交，
            // 选 N 个文件产生 N(N+1)/2 条附件记录。
            beforeUpload={(file, batch) => {
              if (file === batch[batch.length - 1]) doUpload(batch as unknown as File[])
              return false
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
