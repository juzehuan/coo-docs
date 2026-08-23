import { useRef, useState } from 'react'
import { App } from 'antd'
import { errMessage } from '@/api/client'

/** 弹窗/按钮提交的统一封装：防重复提交 + 按钮 loading + 失败提示。
 *
 * 此前各处 `<Modal onOk={fn}>` 既没有 confirmLoading 也没有防重：慢网下用户
 * 看不到任何反馈就会连点，实测「发起新版本」连点三次真的创建了 V1.0/V1.1/V1.2
 * 三个版本（其余操作只是靠数据库唯一约束侥幸挡住，并非代码有防护）。
 *
 * busy 用 ref 而不是 state：state 要等重渲染才生效，同一批次内的连点可能
 * 全都读到旧值；ref 是同步的，第二次点击立刻被挡下。
 *
 * 返回值表示"是否成功"，调用方据此决定关弹窗/重置表单，避免失败时把用户
 * 填的内容一并清空。
 */
export function useSubmit() {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(false)
  const busy = useRef(false)

  async function run(fn: () => Promise<unknown>, okMsg?: string): Promise<boolean> {
    if (busy.current) return false
    busy.current = true
    setLoading(true)
    try {
      await fn()
      if (okMsg) message.success(okMsg)
      return true
    } catch (e) {
      message.error(errMessage(e))
      return false
    } finally {
      busy.current = false
      setLoading(false)
    }
  }

  return { loading, run }
}
