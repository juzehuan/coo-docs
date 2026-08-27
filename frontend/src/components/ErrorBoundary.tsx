import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button, Result, Typography } from 'antd'
import { tOutside } from '@/i18n/messages'

interface Props { children: ReactNode }
interface State { error: Error | null }

/** 全局错误边界。
 *
 * React 的默认行为是：任一组件在渲染期抛错就**卸载整棵树**。此前全项目没有
 * 任何错误边界，实测只要接口返回一条结构异常的数据（后端契约变化、数据损坏
 * 都可能），整个 `#root` 会被清空——用户看到的是**纯白页面**，没有提示、
 * 没有导航、没有恢复入口，只能自己想到按刷新。
 *
 * 这里兜住渲染异常，给出可读说明与两个出口（重试 / 回工作台），并把堆栈打到
 * 控制台便于排障。刻意不做自动上报：本系统部署在客户内网/隧道后，向外发送
 * 错误详情（可能含订单号等业务信息）需要客户明确授权，不该由前端擅自决定。
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // 保留堆栈供排障：白屏时控制台是唯一线索，不能连它也吞掉
    console.error('[ErrorBoundary] 渲染异常：', error, info.componentStack)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children
    // 懒加载 chunk 拿不到 = 服务端已部署新版本、本页还是旧 index.html（第 104 轮）。
    // 这不是"页面出错"，更不该让用户截图找管理员：刷新即可。main.tsx 里的
    // vite:preloadError 监听会先自动刷新一次；走到这里说明刷新后仍失败或监听未触发。
    const msg = String(error.message || error)
    const stale = /dynamically imported module|Importing a module script failed|error loading dynamically imported module/i.test(msg)
    if (stale) {
      return (
        <div style={{ padding: 48 }}>
          <Result
            status="info"
            title={tOutside('app_updated_title')}
            subTitle={tOutside('app_updated_desc')}
            extra={<Button type="primary" onClick={() => { try { sessionStorage.removeItem('coo_chunk_reloaded') } catch { /* ignore */ } window.location.reload() }}>
              {tOutside('reload_page')}
            </Button>}
          />
        </div>
      )
    }
    return (
      <div style={{ padding: 48 }}>
        <Result
          status="error"
          title={tOutside('render_error_title')}
          subTitle={tOutside('render_error_desc')}
          extra={[
            <Button type="primary" key="retry" onClick={() => this.setState({ error: null })}>
              {tOutside('retry')}
            </Button>,
            <Button key="home" onClick={() => { window.location.href = '/' }}>
              {tOutside('back_home')}
            </Button>,
          ]}
        >
          {/* 错误摘要对用户没意义，但截图给运维时是关键线索 */}
          <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0 }}>
            {String(error.message || error).slice(0, 200)}
          </Typography.Paragraph>
        </Result>
      </div>
    )
  }
}
