import { Steps, Tooltip } from 'antd'
import { useI18n } from '@/i18n'

/** 审核流程步骤定义：提交资料 → 部门审核 → COO 终审 → 放行归档 */
const STEP_KEYS = ['step_submit', 'step_dept', 'step_coo', 'step_release'] as const

/** 根据状态机推导当前所在步骤（index）与是否为退回错误态 */
function stepIndex(status: string): { current: number; error: boolean } {
  switch (status) {
    case 'pending_dept': return { current: 1, error: false }
    case 'pending_coo': return { current: 2, error: false }
    case 'released': return { current: 3, error: false }
    case 'rejected': return { current: 0, error: true }   // 退回重提，标红
    case 'withdrawn': return { current: 0, error: false }  // 撤回待重新提交
    default: return { current: 0, error: false }           // draft / 其它
  }
}

interface Props {
  status: string
  /** 紧凑模式：仅渲染一行小圆点，供表格行内使用，悬停提示步骤 */
  compact?: boolean
}

export default function ReviewSteps({ status, compact = false }: Props) {
  const { t } = useI18n()
  const { current, error } = stepIndex(status)
  const isReleased = status === 'released'

  if (compact) {
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}>
        {STEP_KEYS.map((key, i) => {
          const done = isReleased || i < current
          const active = !error && !isReleased && i === current
          const err = error && i === current
          // 档案风暖色：绿=完成，黄铜=进行中，红=退回，浅灰=未到
          const color = err ? '#b04a3a' : active ? '#a8833c' : done ? '#3f7d5c' : '#d8d1c2'
          return (
            <Tooltip key={key} title={t(key)}>
              <span style={{
                width: 9, height: 9, borderRadius: '50%', background: color, display: 'inline-block',
                boxShadow: active ? `0 0 0 3px rgba(168, 131, 60, 0.22)` : undefined,
              }} />
            </Tooltip>
          )
        })}
      </span>
    )
  }

  const statusProp = error ? 'error' : isReleased ? 'finish' : 'process'
  const items = STEP_KEYS.map((key) => ({ title: t(key) }))
  return <Steps size="small" current={current} status={statusProp} items={items} />
}