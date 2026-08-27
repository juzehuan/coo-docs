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
