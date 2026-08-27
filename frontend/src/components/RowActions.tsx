import { Space } from 'antd'
import type { ReactNode } from 'react'

/**
 * 表格行内操作区：全站统一间距，且强制不换行。
 *
 * 各页此前分别用 `<Space>`、`<Space size={4}>`、`<span style={{display:'inline-flex'}}>`，
 * 按钮间距与对齐都不一致；操作列又是固定列，宽度写死，换行会把按钮挤出可视区。
 * 行内按钮统一为 `size="small"`，主操作留给页头。
 */
export default function RowActions({ children }: { children: ReactNode }) {
  return <Space size={4} wrap={false}>{children}</Space>
}
