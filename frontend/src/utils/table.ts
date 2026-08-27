/**
 * 表格列的统一约定。
 *
 * 字段一律单行显示：超长用省略号截断，鼠标悬浮显示全文。
 * 这里用的是 antd 表格自带的 `ellipsis` 属性（内部即 text-overflow + title 提示），
 * 不再各页自己写 CSS 或包 Tooltip——后者在滚动/固定列下容易错位，且各页写法不一。
 *
 * 用法：给可能超长的列加 `ellipsis: ELLIPSIS`；其余列给足 `width`。
 * 配合表格的 `scroll={{ x }}`（列宽之和），列宽不会被挤压，也就不会折行。
 */
export const ELLIPSIS = { showTitle: true } as const

const ICON_BTN = 24                      // 小号图标按钮的宽度（antd 小号按钮高 24，图标按钮为正方形）
const GAP = 4                            // RowActions 里按钮之间的间距
const CELL_PADDING = { middle: 32, small: 16 }   // 单元格左右内边距之和，随表格 size 变化
const HEADER_MIN = 56                    // 表头「操作 / Actions / จัดการ」所需的最小内容宽度

/**
 * 操作列宽度：按实际显示的按钮数量算，不再各页拍脑袋写死。
 *
 * 按钮数量常随权限变化（能否导出、是否管理员），宽度跟着算才不会出现
 * 「只有一个按钮却留了 260px 空白」或「三个按钮被固定列裁掉一个」。
 */
export function actionWidth(count: number, size: 'middle' | 'small' = 'middle'): number {
  const buttons = count * ICON_BTN + Math.max(count - 1, 0) * GAP
  return Math.max(buttons, HEADER_MIN) + CELL_PADDING[size]
}
