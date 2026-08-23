/** 路由与角色的唯一映射：侧边菜单与路由守卫共用，避免"菜单藏了但路由能进"。 */
export const ROUTE_ROLES: { key: string; label: string; roles: string[] }[] = [
  { key: '/', label: 'dashboard', roles: ['submitter', 'dept_reviewer', 'coo_reviewer', 'auditor', 'admin'] },
  { key: '/todo', label: 'todo', roles: ['submitter', 'dept_reviewer', 'coo_reviewer', 'admin'] },
  { key: '/orders', label: 'orders', roles: ['submitter', 'dept_reviewer', 'coo_reviewer', 'auditor', 'admin'] },
  { key: '/packages', label: 'packages', roles: ['submitter', 'dept_reviewer', 'coo_reviewer', 'auditor', 'admin'] },
  { key: '/controlled', label: 'controlled', roles: ['dept_reviewer', 'coo_reviewer', 'auditor', 'admin'] },
  { key: '/nas', label: 'nas', roles: ['coo_reviewer', 'auditor', 'admin'] },
  { key: '/audit', label: 'audit', roles: ['auditor', 'admin'] },
  { key: '/org', label: 'users', roles: ['admin'] },
]

/** 判断角色能否访问某路径（详情页继承其列表页权限，如 /orders/123 用 /orders 的规则）。 */
export function canAccess(role: string | undefined, pathname: string): boolean {
  if (!role) return false
  const seg = '/' + (pathname.split('/')[1] || '')
  const rule = ROUTE_ROLES.find((r) => r.key === seg) ?? ROUTE_ROLES.find((r) => r.key === '/')
  return !!rule?.roles.includes(role)
}
