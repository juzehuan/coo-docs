import { createContext, useContext, useState, type ReactNode } from 'react'
import type { Lang } from '@/types'
import { messages } from './messages'

const LANG_KEY = 'coo_lang'

interface I18nCtx {
  lang: Lang
  setLang: (l: Lang) => void
  t: (k: string, params?: Record<string, string | number>) => string
}

const Ctx = createContext<I18nCtx | null>(null)

/** 按界面语言取业务对象名称（资料包/部门/工厂都存了 zh/en/th 三份）。
 *  缺译时回退中文：宁可语言不对，也不能让名称变成空白而无法辨认。 */
export function localName(
  obj: { name_zh?: string; name_en?: string; name_th?: string } | null | undefined,
  lang: Lang,
  fallback = '',
): string {
  if (!obj) return fallback
  const v = obj[`name_${lang}` as const]
  return (v && v.trim()) || obj.name_zh || fallback
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>((localStorage.getItem(LANG_KEY) as Lang) || 'zh')

  const setLang = (l: Lang) => {
    setLangState(l)
    localStorage.setItem(LANG_KEY, l)
  }

  const t = (k: string, params?: Record<string, string | number>): string => {
    let s = messages[lang][k] ?? messages.zh[k] ?? k
    if (params) for (const [key, val] of Object.entries(params)) s = s.split(`{${key}}`).join(String(val))
    return s
  }

  return <Ctx.Provider value={{ lang, setLang, t }}>{children}</Ctx.Provider>
}

export function useI18n(): I18nCtx {
  const c = useContext(Ctx)
  if (!c) throw new Error('useI18n must be used within I18nProvider')
  return c
}
