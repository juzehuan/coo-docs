import type { ThemeConfig } from 'antd'

// 品牌设计语言：深海蓝主色、浅色主题、白卡片、精致圆角与阴影。
export const theme: ThemeConfig = {
  token: {
    colorPrimary: '#1f5fa8',
    colorInfo: '#1f5fa8',
    colorLink: '#1f5fa8',
    colorLinkHover: '#2f7fd6',
    borderRadius: 8,
    borderRadiusLG: 10,
    fontSize: 14,
    colorBgLayout: '#f0f2f5',
    colorTextHeading: '#0b2545',
    colorBgContainer: '#ffffff',
    colorBorderSecondary: '#e6ebf2',
    boxShadow: '0 4px 16px rgba(11, 37, 69, 0.08)',
    boxShadowSecondary: '0 8px 26px rgba(11, 37, 69, 0.12)',
    controlOutline: 'rgba(31, 95, 168, 0.15)',
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif",
  },
  components: {
    Layout: {
      siderBg: '#0b2545',
      headerBg: '#ffffff',
      headerHeight: 56,
      headerPadding: '0 24px',
      bodyBg: '#f0f2f5',
    },
    Menu: {
      darkItemBg: '#0b2545',
      darkSubMenuItemBg: '#0e2c52',
      darkItemColor: 'rgba(255, 255, 255, 0.72)',
      darkItemHoverColor: '#ffffff',
      darkItemHoverBg: 'rgba(255, 255, 255, 0.08)',
      darkItemSelectedBg: '#1f5fa8',
      darkItemSelectedColor: '#ffffff',
      itemHeight: 44,
      itemMarginInline: 8,
      itemBorderRadius: 8,
    },
    Card: {
      headerFontSize: 16,
      headerFontSizeSM: 15,
      paddingLG: 20,
    },
    Table: {
      headerBg: '#f7f9fc',
    },
    Button: {
      primaryShadow: '0 2px 8px rgba(31, 95, 168, 0.3)',
    },
    Tag: {
      defaultBg: '#f4f7fb',
    },
  },
}