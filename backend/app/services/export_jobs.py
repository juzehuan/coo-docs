"""异步导出作业：提交、执行、清理。

**为什么需要它**（第 79 轮压测的三条实测结论）：
1. 导出是单进程部署里唯一的 CPU 密集操作，并发 5 个时单请求已要 19 秒；
2. **客户端超时放弃后服务端仍在继续跑**——用户刷新重试只会雪上加霜；
3. 同步 HTTP 还受代理超时约束（第 65 轮把 nginx 放宽到 600s 也只是把悬崖推远）。

改成作业后：提交即返回、请求不被占住、断线不丢结果、失败有原因可查，
并且服务端按名额排队而不是一拥而上。

注意这**不会让导出变快**——单进程的 CPU 就那么多。它解决的是"等待方式"，
真正的吞吐要靠多进程（P3 记的三处进程内状态先得解决）。
"""
import datetime
import logging
import os
import threading
import time

from app.core.config import settings
from app.models import ExportJob

logger = logging.getLogger("app.export_jobs")

# 产物保留时长：够用户看到通知后回来下载，又不至于把磁盘堆满
RETENTION_HOURS = 24
# 轮询间隔。作业量很小，不值得为它引入消息队列
POLL_SECONDS = 2.0
ERROR_BACKOFF_SECONDS = 30.0

# kind -> 生成器。生成器签名统一为 (db, user, params) -> (文件名, 路径, 行数)
_BUILDERS: dict = {}
# kind -> 权限校验函数 (db, user, params)，无权时抛 HTTPException。
# 与同步端点用同一套规则：异步这条路绝不能成为绕过权限的旁路。
_CHECKS: dict = {}


def register(kind: str, fn, check=None) -> None:
    _BUILDERS[kind] = fn
    if check is not None:
        _CHECKS[kind] = check


def permission_check(kind: str):
    return _CHECKS.get(kind)


def known_kinds() -> list:
    return sorted(_BUILDERS)


def store_dir() -> str:
    d = os.path.join(settings.UPLOAD_DIR, ".export-jobs")
    os.makedirs(d, exist_ok=True)
    return d


def submit(db, user, kind: str, params: dict) -> ExportJob:
    """登记一个作业。权限由调用方（接口层）在此之前判定完毕。"""
    job = ExportJob(kind=kind, params=params or {}, user_id=user.id, status="pending")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _run_one(db, job: ExportJob) -> None:
    from app.models import User

    fn = _BUILDERS.get(job.kind)
    user = db.get(User, job.user_id)
    if fn is None or user is None:
        job.status = "failed"
        job.error = "作业类型未注册" if fn is None else "提交人已不存在"
        job.finished_at = datetime.datetime.utcnow()
        db.commit()
        return
    job.status = "running"
    job.started_at = datetime.datetime.utcnow()
    db.commit()
    try:
        fname, path, _n = fn(db, user, job.params or {})
        # 移入长期目录：生成器落在 .export-tmp，那里是"用完即删"的语义
        dest = os.path.join(store_dir(), f"{job.id}{os.path.splitext(fname)[1]}")
        os.replace(path, dest)
        job.file_name = fname
        job.stored_name = os.path.basename(dest)
        job.file_size = os.path.getsize(dest)
        job.status = "done"
    except Exception as e:  # noqa: BLE001
        # 失败原因要能给用户看：第 79 轮之前用户只知道"没反应"
        logger.exception("导出作业失败 id=%s kind=%s", job.id, job.kind)
        job.status = "failed"
        job.error = str(e)[:2000]
    finally:
        job.finished_at = datetime.datetime.utcnow()
        db.commit()


def _cleanup(db) -> None:
    """清掉过期产物与其作业行。文件与记录必须一起清，否则要么留孤儿文件、
    要么留指向不存在文件的记录（第 71 轮的教训）。"""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=RETENTION_HOURS)
    old = db.query(ExportJob).filter(ExportJob.created_at < cutoff).all()
    for j in old:
        if j.stored_name:
            try:
                os.unlink(os.path.join(store_dir(), j.stored_name))
            except OSError:
                pass
        db.delete(j)
    if old:
        db.commit()
        logger.info("已清理 %d 个过期导出作业", len(old))


def _loop() -> None:
    """作业主循环。

    **整个循环体必须包在 try 里**——第 76 轮的教训：NAS 调度线程当时只有
    内层操作被 try 包着，一次数据库抖动就让线程永久结束、功能静默停摆。
    """
    last_cleanup = 0.0
    while True:
        try:
            from app.db import SessionLocal
            db = SessionLocal()
            try:
                if time.monotonic() - last_cleanup > 3600:
                    _cleanup(db)
                    last_cleanup = time.monotonic()
                # 一次只取一个：单进程 CPU 有限，排队本身就是保护
                job = (db.query(ExportJob)
                       .filter(ExportJob.status == "pending")
                       .order_by(ExportJob.created_at.asc(), ExportJob.id.asc())
                       .first())
                if job is None:
                    time.sleep(POLL_SECONDS)
                    continue
                _run_one(db, job)
            finally:
                db.close()
        except Exception:  # noqa: BLE001
            logger.exception("导出作业循环出错，%.0f 秒后重试（线程继续运行）",
                             ERROR_BACKOFF_SECONDS)
            time.sleep(ERROR_BACKOFF_SECONDS)


def start_worker() -> None:
    threading.Thread(target=_loop, name="export-job-worker", daemon=True).start()
    logger.info("导出作业 worker 已启动（保留 %d 小时，已注册类型：%s）",
                RETENTION_HOURS, "、".join(known_kinds()) or "无")
