"""附件物理存储：按 sha256 内容哈希命名（内容寻址存储）。

对应落地方案「4.4 文件管理」——文件以内容哈希命名存储、原始中文文件名保存于数据库。
收益：
- 相同内容自动去重（多个订单实例/版本引用同一物理文件，只落盘一份）；
- sha256 作为文件内容的合规证据，可用于与 NAS 归档、出厂对账比对。
历史附件（以 snowflake id 命名）仍按其数据库 file_name 读取，天然兼容。
"""
import hashlib
import os

from app.core.config import settings


def save_upload(content: bytes, ext: str) -> str:
    """按内容 sha256 写入 UPLOAD_DIR，返回存储文件名（含扩展名）。

    若目标文件已存在则复用物理文件，不重复落盘，实现内容去重。
    """
    sha = hashlib.sha256(content).hexdigest()
    stored = f"{sha}{ext}"
    path = os.path.join(settings.UPLOAD_DIR, stored)
    if not os.path.exists(path):
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        with open(path, "wb") as out:
            out.write(content)
    return stored


def stored_file_path(file_name: str) -> str:
    """拼接存储文件的绝对路径。"""
    return os.path.join(settings.UPLOAD_DIR, file_name)