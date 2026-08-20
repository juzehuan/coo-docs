import { Segmented } from 'antd'
import { GlobalOutlined } from '@ant-design/icons'
import { useI18n } from '@/i18n'
import { LANG_LABELS } from '@/i18n/messages'
import type { Lang } from '@/types'

export default function LanguageSwitcher() {
  const { lang, setLang } = useI18n()
  return (
    <Segmented
      value={lang}
      onChange={(v) => setLang(v as Lang)}
      options={(Object.keys(LANG_LABELS) as Lang[]).map((l) => ({ label: LANG_LABELS[l], value: l }))}
      // @ts-expect-error antd 图标在 prefix 上可用
      prefix={<GlobalOutlined />}
    />
  )
}
