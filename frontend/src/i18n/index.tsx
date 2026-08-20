import { createContext, useContext, useState, type ReactNode } from 'react'
import type { Lang } from '@/types'
import { messages } from './messages'

const LANG_KEY = 'coo_lang'

interface I18nCtx {
  lang: Lang
  setLang: (l: Lang) => void
  t: (k: string) => string
}

const Ctx = createContext<I18nCtx | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>((localStorage.getItem(LANG_KEY) as Lang) || 'zh')

  const setLang = (l: Lang) => {
    setLangState(l)
    localStorage.setItem(LANG_KEY, l)
  }

  const t = (k: string): string => messages[lang][k] ?? messages.zh[k] ?? k

  return <Ctx.Provider value={{ lang, setLang, t }}>{children}</Ctx.Provider>
}

export function useI18n(): I18nCtx {
  const c = useContext(Ctx)
  if (!c) throw new Error('useI18n must be used within I18nProvider')
  return c
}
