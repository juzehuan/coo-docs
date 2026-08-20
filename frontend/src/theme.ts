import type { ThemeConfig } from 'antd'

// 还原 demo 风格：深海蓝主色、白卡片、柔和圆角。
export const theme: ThemeConfig = {
  token: {
    colorPrimary: '#1f5fa8',
    colorInfo: '#1f5fa8',
    colorLink: '#1f5fa8',
    borderRadius: 8,
    fontSize: 14,
    colorBgLayout: '#f0f2f5',
    colorTextHeading: '#0b2545',
  },
  components: {
    Layout: {
      siderBg: '#0b2545',
      headerBg: '#ffffff',
      headerHeight: 56,
      headerPadding: '0 20px',
      bodyBg: '#f0f2f5',
    },
    Menu: {
      darkItemBg: '#0b2545',
      darkSubMenuItemBg: '#0b2545',
      darkItemSelectedBg: '#1f5fa8',
      itemHeight: 44,
    },
    Card: {
      headerFontSize: 16,
    },
    Table: {
      headerBg: '#f7f9fc',
    },
  },
}
