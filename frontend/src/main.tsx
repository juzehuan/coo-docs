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
import ErrorBoundary from './components/ErrorBoundary'
import { theme } from './theme'
import './styles.css'

const localeMap = { zh: zhCN, en: enUS, th: thTH }

function Root() {
  const { lang } = useI18n()
  return (
    <ConfigProvider theme={{ ...theme, algorithm: antdTheme.defaultAlgorithm }} locale={localeMap[lang]}>
      <AntdApp>
      {/* 外层边界：内层只包页面内容，若布局/上下文本身出错仍会白屏 */}
      <ErrorBoundary>
        <BrowserRouter>
          <AuthProvider>
            <App />
          </AuthProvider>
        </BrowserRouter>
      </ErrorBoundary>
      </AntdApp>
    </ConfigProvider>
  )
}

// 网页字体改为挂载后动态加载。index.html 里的 <link rel="stylesheet"> 是渲染阻塞的：
// 第 94 轮实测，字体主机不可达且连接挂起（工厂内网防火墙丢包而非快速拒绝）时，
// 首屏白屏 20.5 秒（正常 1.2 秒）。动态插入的样式表不阻塞渲染，字体到了再换、到不了就用本地字体。
function loadWebFonts() {
  const l = document.createElement('link')
  l.rel = 'stylesheet'
  l.href = 'https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@500;600;700;900&family=Noto+Sans+SC:wght@400;500;600;700&display=swap'
  document.head.appendChild(l)
}
window.setTimeout(loadWebFonts, 0)

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <I18nProvider>
      <Root />
    </I18nProvider>
  </React.StrictMode>,
)
