import type { ReactNode } from 'react'

/** 典雅档案风页头：宋体大标题 + 黄铜装饰线 + 可选描述与右侧操作区 */
export default function PageHeader({ title, desc, extra }: {
  title: string
  desc?: string
  extra?: ReactNode
}) {
  return (
    <div className="coo-pagehead">
      <div>
        <h1 className="coo-pagehead-title">{title}</h1>
        {desc && <div className="coo-pagehead-desc">{desc}</div>}
      </div>
      {extra && <div className="coo-pagehead-extra">{extra}</div>}
    </div>
  )
}
