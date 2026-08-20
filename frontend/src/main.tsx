import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { App as AntdApp, ConfigProvider, theme as antdTheme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import enUS from 'antd/locale/en_US'
import thTH from 'antd/locale/th_TH'
import { I18nProvider, useI18n } from './i18n'
import { AuthProvider } from './store/AuthContext'
import App from './App'
import { theme } from './theme'
import './styles.css'

const localeMap = { zh: zhCN, en: enUS, th: thTH }

function Root() {
  const { lang } = useI18n()
  return (
    <ConfigProvider theme={{ ...theme, algorithm: antdTheme.defaultAlgorithm }} locale={localeMap[lang]}>
      <AntdApp>
        <BrowserRouter>
          <AuthProvider>
            <App />
          </AuthProvider>
        </BrowserRouter>
      </AntdApp>
    </ConfigProvider>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <I18nProvider>
      <Root />
    </I18nProvider>
  </React.StrictMode>,
)
