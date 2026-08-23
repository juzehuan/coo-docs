"""Excel(.xlsx) 表格导出。

导出的表格由 COO、审计员与外部核查方直接用 Excel/WPS 打开。此前一律输出 CSV，
虽然能打开，但列宽、冻结表头、筛选都没有，长数字串还会被 Excel 自作主张地转成
科学计数法或抹掉前导零——订单号、MD5 这类值一旦被改写，导出的表格就与系统里的
记录对不上，而核查方并不知道是 Excel 干的。

**公式注入**：xlsx 同样有这个问题，而且比 CSV 更直接——openpyxl 见到以 `=` 开头
的字符串会把单元格类型判为公式(data_type='f')，Excel 打开即执行。这里所有单元格
一律强制为字符串类型(data_type='s')，既挡住 `=HYPERLINK`/`=cmd|...`，也顺带保住
长数字串的原样(前导零、精度都不丢)。因此**不需要**再做 csv_safe 那种加单引号的
中和——那个单引号在 Excel 里会显示出来，反而污染内容。
"""
import io
from typing import Iterable, Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# 列宽上限：MD5、说明这类长文本不至于把整张表撑得没法看
MAX_COL_WIDTH = 60
MIN_COL_WIDTH = 8

_HEADER_FILL = PatternFill("solid", fgColor="16263F")   # 与界面主色一致
_HEADER_FONT = Font(color="F5F1E4", bold=True)


def _cell_text(v) -> str:
    return "" if v is None else str(v)


def build_sheet(ws, header: Sequence[str], rows: Iterable[Sequence]) -> None:
    """把表头与数据写入工作表，全部作为文本，并设置表头样式/冻结/筛选/列宽。"""
    widths = [len(_cell_text(h)) for h in header]

    for col, name in enumerate(header, start=1):
        c = ws.cell(row=1, column=col, value=_cell_text(name))
        c.data_type = "s"
        c.fill = _HEADER_FILL
        c.font = _HEADER_FONT
        c.alignment = Alignment(vertical="center")

    r = 1
    for r, row in enumerate(rows, start=2):
        for col, val in enumerate(row, start=1):
            text = _cell_text(val)
            c = ws.cell(row=r, column=col, value=text)
            # 一律按字符串存：既阻断公式注入，也避免 Excel 改写长数字串
            c.data_type = "s"
            if col <= len(widths):
                widths[col - 1] = max(widths[col - 1], len(text))
            else:
                widths.append(len(text))

    ws.freeze_panes = "A2"                    # 滚动时表头常驻
    if r >= 1 and header:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(header))}{max(r, 1)}"
    for i, w in enumerate(widths, start=1):
        # 中文字符实际占宽约为字母的两倍，粗略放大以免列被挤扁
        ws.column_dimensions[get_column_letter(i)].width = min(
            MAX_COL_WIDTH, max(MIN_COL_WIDTH, w + 2))


def build_xlsx(header: Sequence[str], rows: Iterable[Sequence],
               sheet_title: str = "Sheet1") -> bytes:
    """生成单表 xlsx 字节流。"""
    wb = Workbook()
    ws = wb.active
    # 工作表名不得含 : \ / ? * [ ]，且不超过 31 字符
    ws.title = _safe_title(sheet_title)
    build_sheet(ws, header, rows)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _safe_title(s: str) -> str:
    for ch in ':\\/?*[]':
        s = s.replace(ch, "_")
    return (s or "Sheet1")[:31]


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
