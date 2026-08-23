import { Suspense, lazy } from 'react'
import { Modal, Spin } from 'antd'

/** 附件预览的懒加载包装。
 *
 * AttachmentPreview 依赖 pdfjs-dist，而它此前被静态引入、打进了主包：
 * 实测主包 1.86MB（gzip 594KB）、pdfjs 位于 1.60MB 处的尾部，4G 网络下
 * 首屏要 4.9 秒才出现登录框。而多数用户（工厂提交人）根本不打开 PDF 预览，
 * 却每次都要把这一大坨下载下来。
 *
 * 这里改为**仅在真正要预览时**才动态载入；未打开时不渲染，也就不会触发下载。
 */
const AttachmentPreview = lazy(() => import('@/components/AttachmentPreview'))

interface Props {
  open: boolean
  url: string
  name: string
  onClose: () => void
}

export default function LazyAttachmentPreview(props: Props) {
  if (!props.open) return null
  return (
    <Suspense fallback={
      // 加载分块期间给一个明确的等待态，而不是"点了没反应"
      <Modal open footer={null} onCancel={props.onClose} title={props.name}>
        <div style={{ textAlign: 'center', padding: 48 }}><Spin size="large" /></div>
      </Modal>
    }>
      <AttachmentPreview {...props} />
    </Suspense>
  )
}
