import type { AxiosError } from 'axios'

import { exportJobs } from '@/api/endpoints'
import { errMessage } from '@/api/client'

/** 先直接下载；服务器说忙（429）时自动转为排队作业。
 *
 * 为什么是这个形状而不是"全部改异步"：实测订单清单导出只要 0.08 秒、
 * 归档清单 0.3 秒，把它们也变成"提交→轮询→下载"只会让常见操作更难用。
 * 而后端的导出名额闸门（core/heavy.py，名额 2）在过载时返回 429——
 * 那一刻正是该排队的时刻。这样：快的路径保持快，过载时也不会撞上死路。
 *
 * 返回 'direct' | 'queued'，调用方据此给不同提示。
 */
export async function exportOrQueue(
  direct: () => Promise<unknown>,
  kind: string,
  params: Record<string, unknown> = {},
): Promise<'direct' | 'queued'> {
  try {
    await direct()
    return 'direct'
  } catch (e) {
    const st = (e as AxiosError)?.response?.status
    if (st !== 429) throw e
    // 名额已满：转为后台作业。失败原因照常抛给调用方显示，
    // 不要把"排队也失败了"悄悄吞掉——那会让用户以为已经排上。
    await exportJobs.submit(kind, params)
    return 'queued'
  }
}

/** 把导出错误转成可读文案。blob 响应下 axios 的 data 是 Blob，
 *  直接交给 errMessage 会得到无意义的结果，这里先把它读回文本。 */
export async function exportErrMessage(e: unknown): Promise<string> {
  const resp = (e as AxiosError)?.response
  const data = resp?.data as unknown
  if (data instanceof Blob) {
    try {
      const txt = await data.text()
      const j = JSON.parse(txt) as { detail?: string }
      if (j?.detail) return j.detail
    } catch { /* 不是 JSON 就走通用文案 */ }
  }
  return errMessage(e)
}
