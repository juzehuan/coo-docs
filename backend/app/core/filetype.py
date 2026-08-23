"""文件类型：按扩展名给出权威 MIME，并用文件头校验内容是否名副其实。

两个问题促成此模块：

1. **MIME 完全由客户端决定**。附件的 `mime_type` 直接取 `UploadFile.content_type`，
   而它是请求里的一个字段，任何客户端都可随意填写。后果是双向的：一份真 PDF 若
   被声明成 `text/plain`（缺少 MIME 数据库的系统、某些上传工具就会这样），系统便
   认为它不可预览；反过来，任何内容只要声明成 `application/pdf` 就会被当成 PDF 预览。
   类型应由服务端按扩展名判定，不该听客户端的。

2. **内容从不校验**。上传只看扩展名白名单，一个纯文本文件改名 `发票.pdf` 照样入库、
   照样同步到 NAS、照样打进交付给核查方的 ZIP，MD5 一应俱全——直到对方打开时才
   发现打不开。对一个"归集核查证据"的系统来说，这类文件等于无效证据，而系统全程
   报告一切正常。这里在入库前用文件头(magic bytes)拦下明显的名实不符。

校验刻意保守：只对有稳定文件头的格式做判定，txt/csv 这类无签名格式一律放行，
宁可漏判也不能把用户正常的文件挡在门外。
"""

# 扩展名 -> 权威 MIME（服务端判定，不采信客户端声明）
EXT_MIME = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".zip": "application/zip",
    ".rar": "application/vnd.rar",
    ".7z": "application/x-7z-compressed",
    ".txt": "text/plain",
    ".csv": "text/csv",
}

# ZIP 容器：docx/xlsx/pptx 本质都是 zip（空包 PK\x05\x06、分卷 PK\x07\x08 也算）
_ZIP = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
# OLE 复合文档：老版 doc/xls/ppt
_OLE = (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",)

# 扩展名 -> 可接受的文件头。未列出的扩展名（.txt/.csv）不做内容校验。
SIGNATURES: dict[str, tuple[bytes, ...]] = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".bmp": (b"BM",),
    ".tif": (b"II*\x00", b"MM\x00*"),
    ".tiff": (b"II*\x00", b"MM\x00*"),
    ".zip": _ZIP,
    ".docx": _ZIP,
    ".xlsx": _ZIP,
    ".pptx": _ZIP,
    # 老版 Office 既可能是 OLE，也可能已被另存为新格式（zip）——两者都放行
    ".doc": _OLE + _ZIP,
    ".xls": _OLE + _ZIP,
    ".ppt": _OLE + _ZIP,
    ".rar": (b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00"),
    ".7z": (b"7z\xbc\xaf\x27\x1c",),
}

# PDF 头允许不在偏移 0：部分工具会在前面加少量字节，阅读器同样容忍
_PDF_SEARCH_WINDOW = 1024


def guess_mime(ext: str) -> str:
    return EXT_MIME.get(ext.lower(), "application/octet-stream")


def content_matches(content: bytes, ext: str) -> bool:
    """内容的文件头是否与扩展名相符；无签名可判的格式一律返回 True。"""
    ext = ext.lower()
    if ext == ".pdf":
        return b"%PDF-" in content[:_PDF_SEARCH_WINDOW]
    sigs = SIGNATURES.get(ext)
    if not sigs:
        return True          # txt/csv 等：无稳定文件头，不做判定
    return any(content.startswith(s) for s in sigs)
