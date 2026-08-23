"""CSV 单元格安全化：防止电子表格公式注入（Formula Injection）。

导出的 CSV 常被审计/COO 用 Excel/WPS 打开，若字段以 = + - @ 等开头会被当作
公式执行（如 =HYPERLINK / =cmd|...），可在打开者上下文中触发外联或命令。
统一在此处：对危险前导字符加单引号转义，并对双引号做加倍转义（供外层再包裹引号）。
"""

_DANGEROUS_PREFIX = ("=", "+", "-", "@", "\t", "\r")


def csv_cell(value) -> str:
    """返回可安全放入双引号 CSV 字段的内容（已做公式中和与引号加倍）。

    注意：输出只有包在双引号里才安全，请优先使用 csv_row()。
    """
    s = "" if value is None else str(value)
    if s and s[0] in _DANGEROUS_PREFIX:
        s = "'" + s
    return s.replace('"', '""')


def csv_row(cells) -> str:
    """把一行单元格安全化并拼为带引号的 CSV 行（唯一推荐的拼行方式）。"""
    return ",".join(f'"{csv_cell(c)}"' for c in cells)
