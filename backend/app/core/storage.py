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
import threading
from contextlib import contextmanager

from app.core.config import settings


# 保护「复用已有物理文件」与「回收无引用文件」之间的临界区。
#
# 竞态路径：上传方调用 save_upload 命中去重分支（文件已存在，不重新落盘），
# 此时新附件行尚未提交；另一请求删除了最后一个引用该文件的附件，_purge_files
# 查库判定"已无引用"便删掉物理文件——新附件于是指向一个不存在的文件，
# 正是 storage_check 定义的「悬空记录（证据丢失）」。
#
# 说明：该窗口由代码推断可得，但用真实接口并发 5 轮**未能复现**（需要恰好
# 同时上传字节完全相同的文件、且并发删除最后一个其它引用）。之所以仍然修，
# 是因为代价极小而后果是证据丢失——本系统的全部价值就在证据完整。
#
# 取舍：锁需由上传方从 save_upload 持有到 commit（未提交的行对别的会话不可见，
# 只锁 save_upload 本身没用）。提交耗时在毫秒级，本系统上传并发很低，
# 串行化这一小段对吞吐无实质影响。
_reuse_lock = threading.Lock()


@contextmanager
def storage_guard():
    """上传落盘→写库提交、以及引用检查→删除文件，两段互斥。"""
    with _reuse_lock:
        yield


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


def purge_files(db, atts: list) -> None:
    """删除这批附件行对应的物理文件（仅当集合之外再无引用）。

    **调用顺序有硬性要求：必须在 `db.commit()` 成功之后调用。**
    反过来"先删文件、再提交"会在提交失败回滚时留下**附件行还在、文件已经没了**
    的悬空记录——也就是 storage_check 报的「证据丢失，需人工恢复」。
    第 71 轮发现 `packages.delete_attachment` 正是这个反向顺序，且没有持
    storage_guard()——它自己内联了一份引用计数，因此接连错过了第 49/50 轮
    给这条路径加的并发保护。这里合并为**唯一实现**，就是为了不再出现
    "改了三处、漏了第四处"。

    存储按 sha256 内容哈希命名，多个附件行（订单附件 / 版本附件）会复用同一
    物理文件，仅当删除集合之外无其它引用时才删除，避免误删仍被引用的文件。
    """
    if not atts:
        return
    from app.models import Attachment
    names = {a.file_name for a in atts}
    ids = [a.id for a in atts]
    # 与上传的去重复用互斥：否则可能删掉一个刚被复用、其附件行尚未提交的文件
    with storage_guard():
        for name in names:
            q = db.query(Attachment.id).filter(Attachment.file_name == name)
            if ids:
                q = q.filter(Attachment.id.notin_(ids))
            if q.first():
                continue
            path = os.path.join(settings.UPLOAD_DIR, name)
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
