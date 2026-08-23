import type { Lang, NotificationItem } from '@/types'
import { localName } from '@/i18n'
import { messages } from '@/i18n/messages'

interface Params {
  subject?: string
  name_zh?: string
  name_en?: string
  name_th?: string
}

/** 通知文案：按**收件人**当前界面语言渲染。
 *
 * 通知的 title/body 是创建时写死的中文成品串——泰国工厂的提交人把界面切到
 * 泰文也没用，收到的通知仍然全是中文。后端改为额外存结构化参数(params)，
 * 这里据此按当前语言拼装；没有 params 的历史记录回退到原文案，保证不丢信息。
 */
export function notifyText(n: NotificationItem, lang: Lang): { title: string; body: string } {
  if (!n.params) return { title: n.title, body: n.body }
  let p: Params
  try {
    p = JSON.parse(n.params) as Params
  } catch {
    return { title: n.title, body: n.body }   // 参数损坏时不能让通知变空白
  }
  // 直接按传入的 lang 查表，不走 tOutside（它读 localStorage，切换语言时可能滞后）
  const event = messages[lang]?.[`notif_${n.type}`] ?? messages.zh[`notif_${n.type}`] ?? ''
  const subject = p.subject || ''
  // 事件名缺失（后端新增了前端还不认识的类型）时回退中文标题，宁可语言不对也不能显示成占位符
  if (!event) return { title: n.title, body: n.body }
  return {
    title: subject ? `${subject} ${event}` : event,
    body: localName(p, lang, n.body),
  }
}
