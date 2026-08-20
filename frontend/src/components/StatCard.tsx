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
  const c = color || token.colorPrimary
  return (
    <Card variant="borderless" className="coo-card" styles={{ body: { padding: 18 } }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
        {icon && (
          <span style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 44, height: 44, borderRadius: 12, flexShrink: 0,
            background: `linear-gradient(135deg, ${c}22, ${c}0a)`,
            color: c, fontSize: 22,
          }}>{icon}</span>
        )}
        <div>
          <div style={{ color: token.colorTextSecondary, fontSize: 13, marginBottom: 4 }}>{title}</div>
          <Statistic value={value} suffix={suffix} valueStyle={{ color, fontWeight: 700, fontSize: 26 }} />
        </div>
      </div>
    </Card>
  )
}