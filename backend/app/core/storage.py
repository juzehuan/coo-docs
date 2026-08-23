"""附件物理存储：按 sha256 内容哈希命名（内容寻址存储）。

对应落地方案「4.4 文件管理」——文件以内容哈希命名存储、原始中文文件名保存于数据库。
收益：
- 相同内容自动去重（多个订单实例/版本引用同一物理文件，只落盘一份）；
- sha256 作为文件内容的合规证据，可用于与 NAS 归档、出厂对账比对。
历史附件（以 snowflake id 命名）仍按其数据库 file_name 读取，天然兼容。
"""
import hashlib
import os
import tempfile

from app.core.config import settings


def save_upload(content: bytes, ext: str) -> str:
    """按内容 sha256 写入 UPLOAD_DIR，返回存储文件名（含扩展名）。

    若目标文件已存在则复用物理文件，不重复落盘，实现内容去重。

    **先写临时文件再原子替换**：原实现直接以最终路径打开写入，于是在"文件已
    创建但尚未写完"的窗口里，别的请求判定 `os.path.exists` 为真便直接复用，
    其附件记录指向一个只写了一半的文件。实测 60MB 内容并发时，读侧 83 次观测
    有 82 次读到不完整文件（最小仅 36KB）——而 NAS 同步与附件下载正是这样读
    文件的，结果就是归档/交付出一份残缺的证据，且 MD5 是上传时按内存内容算的、
    校验不出来。os.replace 在同一文件系统上是原子的：读者要么看不到文件，
    要么看到完整文件，不存在中间态。
    """
    sha = hashlib.sha256(content).hexdigest()
    stored = f"{sha}{ext}"
    path = os.path.join(settings.UPLOAD_DIR, stored)
    if os.path.exists(path):
        return stored
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    # 临时文件与目标同目录，确保 os.replace 是同文件系统内的原子重命名
    fd, tmp = tempfile.mkstemp(dir=settings.UPLOAD_DIR, prefix=".tmp-", suffix=ext)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())   # 落盘后再替换，避免掉电后留下空洞文件
        os.replace(tmp, path)
    except BaseException:
        # 失败时清掉临时文件，不留垃圾（storage_check 的孤儿扫描也不该被它干扰）
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return stored


def stored_file_path(file_name: str) -> str:
    """拼接存储文件的绝对路径。"""
    return os.path.join(settings.UPLOAD_DIR, file_name)