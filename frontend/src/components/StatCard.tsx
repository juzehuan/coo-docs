import { Card, Statistic } from 'antd'
import type { ReactNode } from 'react'
import { SERIF } from '@/theme'

export default function StatCard({ title, value, suffix, icon, color, onClick }: {
  title: string
  value: number | string
  suffix?: string
  icon?: ReactNode
  color?: string
  onClick?: () => void
}) {
  const c = color || '#16263f'
  return (
    <Card
      variant="borderless"
      className="coo-card"
      onClick={onClick}
      styles={{ body: { padding: 18, cursor: onClick ? 'pointer' : undefined } }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
        {icon && (
          <span style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 44, height: 44, borderRadius: 11, flexShrink: 0,
            border: `1px solid ${c}2e`,
            background: `${c}12`,
            color: c, fontSize: 22,
          }}>{icon}</span>
        )}
        <div>
          <div style={{ color: '#75705f', fontSize: 13, marginBottom: 4, letterSpacing: 0.5 }}>{title}</div>
          <Statistic
            value={value}
            suffix={suffix}
            valueStyle={{ color: c, fontFamily: SERIF, fontWeight: 700, fontSize: 28, letterSpacing: 1 }}
          />
        </div>
      </div>
    </Card>
  )
}
