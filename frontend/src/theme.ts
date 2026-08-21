import type { ThemeConfig } from 'antd'

// 典雅档案风：暖纸底 + 墨蓝主色 + 黄铜点缀，宋体标题 / 黑体正文。
export const SERIF = "'Noto Serif SC', 'Source Han Serif SC', 'Songti SC', 'STSong', 'SimSun', serif"
export const SANS = "'Noto Sans SC', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif"

export const theme: ThemeConfig = {
  token: {
    colorPrimary: '#16263f',          // 墨蓝
    colorInfo: '#a8833c',             // 黄铜
    colorLink: '#8a6d2f',
    colorLinkHover: '#a8833c',
    colorSuccess: '#3f7d5c',
    colorWarning: '#b97a1e',
    colorError: '#b04a3a',
    colorTextBase: '#232a33',
    colorBgLayout: '#f5f2ea',         // 暖纸底
    colorBgContainer: '#fffdf7',      // 暖白卡片
    colorBgElevated: '#fffef9',
    colorBorder: '#dcd4c3',
    colorBorderSecondary: '#e8e1d3',
    borderRadius: 6,
    borderRadiusLG: 10,
    borderRadiusSM: 4,
    fontSize: 14,
    controlOutline: 'rgba(168, 131, 60, 0.18)',
    boxShadow: '0 1px 2px rgba(34, 42, 51, 0.05), 0 4px 14px rgba(34, 42, 51, 0.05)',
    boxShadowSecondary: '0 10px 30px rgba(34, 42, 51, 0.10)',
    colorTextHeading: '#16263f',
    colorText: '#232a33',
    colorTextSecondary: '#75705f',
    colorTextTertiary: '#a49e8c',
    fontFamily: SANS,
  },
  components: {
    Layout: {
      siderBg: '#16263f',
      headerBg: '#fffdf7',
      headerHeight: 60,
      headerPadding: '0 28px',
      bodyBg: '#f5f2ea',
    },
    Menu: {
      darkItemBg: '#16263f',
      darkSubMenuItemBg: '#101d31',
      darkItemColor: 'rgba(244, 240, 228, 0.66)',
      darkItemHoverColor: '#f5f1e4',
      darkItemHoverBg: 'rgba(255, 255, 255, 0.06)',
      darkItemSelectedBg: '#2a3d5c',
      darkItemSelectedColor: '#f7e9c9',
      itemHeight: 42,
      itemMarginInline: 10,
      itemBorderRadius: 6,
    },
    Card: {
      headerFontSize: 15,
      headerFontSizeSM: 14,
      paddingLG: 20,
    },
    Table: {
      headerBg: '#f4efe4',
      headerColor: '#6f685a',
      headerSplitColor: 'transparent',
      rowHoverBg: '#faf6ec',
      borderColor: '#e8e1d3',
    },
    Button: {
      primaryShadow: '0 2px 8px rgba(22, 38, 63, 0.24)',
      defaultBg: '#fffdf7',
      defaultBorderColor: '#dcd4c3',
      borderRadius: 6,
      borderRadiusLG: 8,
    },
    Input: {
      activeBorderColor: '#a8833c',
      hoverBorderColor: '#c9b06a',
      activeShadow: '0 0 0 3px rgba(168, 131, 60, 0.14)',
      colorBgContainer: '#fffef8',
    },
    Select: {
      optionSelectedBg: '#f4efe4',
    },
    Segmented: {
      itemSelectedBg: '#16263f',
      itemSelectedColor: '#f7e9c9',
      trackBg: '#eee7d8',
    },
    Progress: {
      defaultColor: '#a8833c',
      remainingColor: '#ece4d3',
    },
    Tag: {
      defaultBg: '#f4efe4',
    },
    Drawer: {
      colorBgElevated: '#fffdf7',
    },
    Modal: {
      contentBg: '#fffdf7',
      headerBg: '#fffdf7',
    },
  },
}
