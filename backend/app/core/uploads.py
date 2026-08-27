"""上传校验与读取辅助（orders 与 packages 两个上传端点共用）。

背景：原实现 `await f.read()` 先把整个请求文件读入内存再检查大小，
攻击者并发上传超大文件可在校验前耗尽内存（OOM）。此处按 1MB 分块累计，
一旦超过上限立刻抛错停止读取，内存占用被限制在 MAX_FILE_MB 以内。
"""
import hashlib
import re
import os

from fastapi import HTTPException, UploadFile

from app.constants import ALLOWED_EXTENSIONS
from app.core.filetype import content_matches, guess_mime

_CHUNK = 1024 * 1024


async def read_upload_limited(f: UploadFile, max_mb: int) -> bytes:
    limit = max_mb * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await f.read(_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(status_code=400, detail=f"文件超过 {max_mb}MB 上限")
        chunks.append(chunk)
    return b"".join(chunks)


# attachments.original_name 列宽 255；超出会在写库时抛 DataError，
# 而此时文件已落盘 —— 会留下无人引用的孤儿文件，故在读取前先行截断。
MAX_ORIGINAL_NAME = 255


# 控制字符在文件名里没有任何正当用途，且会一路污染下游：
# xlsx 是 XML，这些字符不合法，openpyxl 直接抛 IllegalCharacterError（第 69 轮）。
# 路径分隔符同样剔除：原名会作为下载响应的 Content-Disposition filename 下发，
# 纯 ASCII 时 Starlette 用的是 `filename="..."` 原样形式，实测 `../../etc/passwd.txt`
# 会被原样带进响应头——浏览器与 curl 都会自行取 basename，但"下载文件名是一个
# 纯文件名"这个不变量本就该在源头成立，不该指望每个下载方都做防护。
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f\\/]")


def sanitize_name(name: str | None) -> str:
    """剔除控制字符与路径分隔符。上传入库与下载响应头共用同一套规则，
    避免"入库时清了、下发时又冒出来"这类两头不一致。"""
    return _CTRL_RE.sub("", name or "")


def safe_original_name(filename: str | None, ext: str) -> str:
    """剔除控制字符，并把过长的原始文件名截断到列宽内，保留扩展名便于识别。"""
    name = sanitize_name(filename) or f"unnamed{ext}"
    if len(name) <= MAX_ORIGINAL_NAME:
        return name
    keep = MAX_ORIGINAL_NAME - len(ext)
    return name[:max(keep, 1)] + ext


async def read_validated_upload(f: UploadFile, max_mb: int) -> tuple[bytes, str, str, str, str]:
    """校验扩展名白名单 + 内容名实相符 + 限量读取。

    返回 (内容, 扩展名, md5, 安全原始文件名, 服务端判定的 MIME)。

    MIME 由扩展名判定而非采信 `f.content_type`：那是客户端可随意填写的字段，
    让它决定"能不能预览"意味着一份真 PDF 可能因声明成 text/plain 而无法预览，
    而任意内容只要声明成 application/pdf 就会被当成 PDF 打开。

    内容校验拦的是"名实不符"：一个纯文本改名 `发票.pdf` 会一路入库、同步 NAS、
    打进交付给核查方的 ZIP，MD5 一应俱全，直到对方打开才发现打不开——对归集
    核查证据的系统而言这就是无效证据，而全程没有任何提示。
    """
    ext = os.path.splitext(f.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型：{ext}")
    content = await read_upload_limited(f, max_mb)
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")
    if not content_matches(content, ext):
        raise HTTPException(
            status_code=400,
            detail=f"文件内容与扩展名 {ext} 不符，请确认上传的是真实的 {ext} 文件",
        )
    return (content, ext, hashlib.md5(content).hexdigest(),
            safe_original_name(f.filename, ext), guess_mime(ext))
