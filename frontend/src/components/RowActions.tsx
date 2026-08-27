import { Button, Space, Tooltip } from 'antd'
import type { ReactNode } from 'react'

/**
 * 表格行内操作区：全站统一间距，且强制不换行。
 *
 * 各页此前分别用 `<Space>`、`<Space size={4}>`、`<span style={{display:'inline-flex'}}>`，
 * 按钮间距与对齐都不一致；操作列又是固定列，宽度写死，换行会把按钮挤出可视区。
 */
export default function RowActions({ children }: { children: ReactNode }) {
  return <Space size={4} wrap={false}>{children}</Space>
}

/**
 * 行内操作按钮：只显图标，文字移到悬浮提示。
 *
 * 带文字的按钮会把操作列撑得很宽——「详情 + 导出 Excel + 导出 ZIP」三个按钮
 * 光文字就要 260px，英文/泰文界面下更长，正文列被固定操作列挤掉一大片。
 * 图标按钮一律 24px，三个也只占 76px；文字改由 Tooltip 呈现，并写进 aria-label
 * 供读屏软件与自动化测试识别。
 */
export function ActionButton({ label, icon, onClick, danger, disabled }: {
  label: string
  icon: ReactNode
  onClick: () => void
  danger?: boolean
  disabled?: boolean
}) {
  const btn = (
    <Button size="small" icon={icon} danger={danger} disabled={disabled} aria-label={label} onClick={onClick} />
  )
  // disabled 的按钮不派发鼠标事件，Tooltip 收不到 hover：包一层能收事件的元素，
  // 否则「没有附件所以不能导出」这种禁用态反而没有任何解释
  return <Tooltip title={label}>{disabled ? <span style={{ display: 'inline-flex' }}>{btn}</span> : btn}</Tooltip>
}
