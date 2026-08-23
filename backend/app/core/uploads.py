"""上传校验与读取辅助（orders 与 packages 两个上传端点共用）。

背景：原实现 `await f.read()` 先把整个请求文件读入内存再检查大小，
攻击者并发上传超大文件可在校验前耗尽内存（OOM）。此处按 1MB 分块累计，
一旦超过上限立刻抛错停止读取，内存占用被限制在 MAX_FILE_MB 以内。
"""
import hashlib
import os

from fastapi import HTTPException, UploadFile

from app.constants import ALLOWED_EXTENSIONS

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


def safe_original_name(filename: str | None, ext: str) -> str:
    """把过长的原始文件名截断到列宽内，保留扩展名便于识别。"""
    name = filename or f"unnamed{ext}"
    if len(name) <= MAX_ORIGINAL_NAME:
        return name
    keep = MAX_ORIGINAL_NAME - len(ext)
    return name[:max(keep, 1)] + ext


async def read_validated_upload(f: UploadFile, max_mb: int) -> tuple[bytes, str, str, str]:
    """校验扩展名白名单 + 限量读取，返回 (内容, 扩展名, md5, 安全原始文件名)。"""
    ext = os.path.splitext(f.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型：{ext}")
    content = await read_upload_limited(f, max_mb)
    return content, ext, hashlib.md5(content).hexdigest(), safe_original_name(f.filename, ext)
