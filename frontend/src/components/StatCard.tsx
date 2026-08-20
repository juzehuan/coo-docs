import { Card, Statistic, theme as antdTheme } from 'antd'
import type { ReactNode } from 'react'

export default function StatCard({ title, value, suffix, icon, color }: {
  title: string
  value: number | string
  suffix?: string
  icon?: ReactNode
  color?: string
}) {
  const { token } = antdTheme.useToken()
  return (
    <Card variant="borderless" styles={{ body: { padding: 18 } }}>
      <Statistic title={title} value={value} suffix={suffix} valueStyle={{ color: color || token.colorPrimary, fontWeight: 700 }} />
      {icon && <div style={{ position: 'absolute', right: 18, top: 18, opacity: 0.15, fontSize: 28 }}>{icon}</div>}
    </Card>
  )
}
