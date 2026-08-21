import { useEffect, useRef, useState } from 'react'
import { Button, Modal, Result, Space, Spin } from 'antd'
import { DownloadOutlined, LeftOutlined, RightOutlined } from '@ant-design/icons'
import { downloadFile, getToken } from '@/api/client'
import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy } from 'pdfjs-dist'

// PDF.js worker：不依赖浏览器内置 PDF 查看器，任何环境（含 headless）都能渲染
// ?v=2 用于破坏浏览器缓存：早期 nginx 将 .mjs 以 octet-stream 返回并被缓存 30 天，需强制重新拉取
GlobalWorkerOptions.workerSrc = `${new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()}?v=2`

type Kind = 'image' | 'pdf' | 'text' | 'unsupported'

interface Props {
  open: boolean
  url: string // 完整 /api/... 路径（含 query），浏览器导航无法带 Bearer 头，故用 fetch 携带
  name: string
  onClose: () => void
}

/** 附件预览 Modal：fetch 携带 token 获取 blob，图片/PDF/文本内嵌展示，其余类型提供下载。 */
export default function AttachmentPreview({ open, url, name, onClose }: Props) {
  const [kind, setKind] = useState<Kind | null>(null)
  const [blobUrl, setBlobUrl] = useState('')
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const blobUrlRef = useRef('')

  // PDF.js 状态
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null)
  const [pageNum, setPageNum] = useState(1)
  const [totalPages, setTotalPages] = useState(0)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true); setError(''); setKind(null); setText(''); setBlobUrl(''); blobUrlRef.current = ''
    setPdfDoc(null); setTotalPages(0); setPageNum(1)

    ;(async () => {
      try {
        const res = await fetch(url, { headers: { Authorization: `Bearer ${getToken()}` } })
        if (!res.ok) throw new Error(`加载失败（HTTP ${res.status}）`)
        const blob = await res.blob()
        if (cancelled) return
        const mime = blob.type || res.headers.get('Content-Type') || ''
        if (mime.startsWith('image/')) {
          const u = URL.createObjectURL(blob); blobUrlRef.current = u; setBlobUrl(u); setKind('image')
        } else if (mime === 'application/pdf') {
          setKind('pdf')
          const doc = await getDocument({ data: await blob.arrayBuffer() }).promise
          if (cancelled) { doc.destroy(); return }
          setPdfDoc(doc); setTotalPages(doc.numPages)
        } else if (mime.startsWith('text/') || mime.includes('csv') || mime.includes('json')) {
          setKind('text'); setText(await blob.text())
        } else {
          const u = URL.createObjectURL(blob); blobUrlRef.current = u; setBlobUrl(u); setKind('unsupported')
        }
      } catch (e: any) {
        if (!cancelled) setError(e?.message || '加载失败')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
      if (blobUrlRef.current) URL.revokeObjectURL(blobUrlRef.current)
      if (pdfDoc) { try { pdfDoc.destroy() } catch { /* ignore */ } }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, url])

  // 渲染 PDF 当前页到 canvas
  useEffect(() => {
    if (!pdfDoc || !canvasRef.current) return
    let cancelled = false
    ;(async () => {
      const page = await pdfDoc.getPage(pageNum)
      const viewport = page.getViewport({ scale: 1.3 })
      const canvas = canvasRef.current!
      canvas.width = viewport.width
      canvas.height = viewport.height
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      await page.render({ canvasContext: ctx, viewport }).promise
      if (cancelled) return
      const cs = canvas as HTMLCanvasElement & { __page?: string }
      cs.__page = `p${pageNum}`
    })()
    return () => { cancelled = true }
  }, [pdfDoc, pageNum])

  return (
    <Modal open={open} onCancel={onClose} footer={null} width={980} title={name} destroyOnClose>
      {loading && <div style={{ textAlign: 'center', padding: 64 }}><Spin tip="加载中" /></div>}
      {!loading && error && <Result status="warning" title={error} />}
      {!loading && !error && kind === 'image' && (
        <div style={{ textAlign: 'center', background: '#f5f5f5', borderRadius: 8, padding: 8 }}>
          <img src={blobUrl} alt={name} style={{ maxWidth: '100%', maxHeight: '72vh' }} />
        </div>
      )}
      {!loading && !error && kind === 'pdf' && (
        <div style={{ background: '#525659', borderRadius: 8, padding: 12, textAlign: 'center' }}>
          <canvas ref={canvasRef} style={{ maxWidth: '100%', boxShadow: '0 2px 10px rgba(0,0,0,.35)' }} />
          {totalPages > 1 && (
            <Space style={{ marginTop: 12, color: '#fff' }}>
              <Button size="small" icon={<LeftOutlined />} disabled={pageNum <= 1} onClick={() => setPageNum(pageNum - 1)} />
              <span>{pageNum} / {totalPages}</span>
              <Button size="small" icon={<RightOutlined />} disabled={pageNum >= totalPages} onClick={() => setPageNum(pageNum + 1)} />
            </Space>
          )}
        </div>
      )}
      {!loading && !error && kind === 'text' && (
        <pre style={{ margin: 0, padding: 16, maxHeight: '72vh', overflow: 'auto', whiteSpace: 'pre-wrap', background: '#fafafa', borderRadius: 8 }}>{text}</pre>
      )}
      {!loading && !error && kind === 'unsupported' && (
        <Result
          icon={<DownloadOutlined />}
          title="该文件类型暂不支持在线预览"
          subTitle={`${name} · 请下载后查看`}
          extra={<Button type="primary" icon={<DownloadOutlined />} onClick={() => downloadFile(url, name)}>下载</Button>}
        />
      )}
    </Modal>
  )
}
