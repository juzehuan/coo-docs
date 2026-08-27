/** 路由与角色的唯一映射：侧边菜单与路由守卫共用，避免"菜单藏了但路由能进"。 */
export const ROUTE_ROLES: { key: string; label: string; roles: string[]; hidden?: boolean }[] = [
  { key: '/', label: 'dashboard', roles: ['submitter', 'dept_reviewer', 'coo_reviewer', 'auditor', 'admin'] },
  { key: '/todo', label: 'todo', roles: ['submitter', 'dept_reviewer', 'coo_reviewer', 'admin'] },
  { key: '/orders', label: 'orders', roles: ['submitter', 'dept_reviewer', 'coo_reviewer', 'auditor', 'admin'] },
  // 提交人不进资料包线：这条线按「责任部门 / 责任人」分工，归部门审核人维护常备档案，
  // 而资料包的责任人实际全部配成了部门经理——提交人点进来永远是空列表。
  // 提交人的工作在订单线（客户订单 → 添加资料包 → 传附件 → 提交审核），见手册 §6.1。
  { key: '/packages', label: 'packages', roles: ['dept_reviewer', 'coo_reviewer', 'auditor', 'admin'] },
  { key: '/controlled', label: 'controlled', roles: ['dept_reviewer', 'coo_reviewer', 'auditor', 'admin'] },
  { key: '/nas', label: 'nas', roles: ['coo_reviewer', 'auditor', 'admin'] },
  { key: '/audit', label: 'audit', roles: ['auditor', 'admin'] },
  { key: '/org', label: 'users', roles: ['admin'] },
  // 通知中心不进侧边菜单（入口在顶栏铃铛），但必须登记角色，
  // 否则路由守卫按兜底规则处理，未来改动容易出现"能进但不该进"
  // 我的导出：导出在名额已满时会转为后台作业，这里是取回产物的地方。
  // 给它一个**可见**的菜单项而不是只靠通知链接——第 64 轮的教训是
  // "能力做好了却没有入口等于没做"。
  { key: '/exports', label: 'my_exports', roles: ['submitter', 'dept_reviewer', 'coo_reviewer', 'auditor', 'admin'] },
  { key: '/notifications', label: 'notifications', roles: ['submitter', 'dept_reviewer', 'coo_reviewer', 'auditor', 'admin'], hidden: true },
]

/** 判断角色能否访问某路径（详情页继承其列表页权限，如 /orders/123 用 /orders 的规则）。 */
export function canAccess(role: string | undefined, pathname: string): boolean {
  if (!role) return false
  const seg = '/' + (pathname.split('/')[1] || '')
  const rule = ROUTE_ROLES.find((r) => r.key === seg) ?? ROUTE_ROLES.find((r) => r.key === '/')
  return !!rule?.roles.includes(role)
}
