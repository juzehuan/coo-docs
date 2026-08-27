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
    job_id = job.id       # 行被删后 rollback 会让 job 的属性全部过期，再取会抛 ObjectDeletedError
    dest = ""
    try:
        fname, path, _n = fn(db, user, job.params or {})
        # 移入长期目录：生成器落在 .export-tmp，那里是"用完即删"的语义
        dest = os.path.join(store_dir(), f"{job.id}{os.path.splitext(fname)[1]}")
        os.replace(path, dest)
        job.file_name = fname
        job.stored_name = os.path.basename(dest)
        job.file_size = os.path.getsize(dest)
        job.status = "done"
        job.error = ""
    except Exception as e:  # noqa: BLE001
        # 失败原因要能给用户看：第 79 轮之前用户只知道"没反应"
        logger.exception("导出作业失败 id=%s kind=%s", job.id, job.kind)
        job.status = "failed"
        job.error = str(e)[:2000]
    finally:
        job.finished_at = datetime.datetime.utcnow()
        try:
            db.commit()
        except Exception:  # noqa: BLE001
            # 作业跑到一半被提交人删掉了（DELETE /exports/{id}），UPDATE 匹配 0 行。
            # 行没了，产物也不能留：否则它既不在列表里、也不会被清理（第 71 轮）。
            db.rollback()
            if dest:
                try:
                    os.unlink(dest)
                except OSError:
                    pass
            logger.warning("导出作业 id=%s 执行期间已被删除，产物已丢弃", job_id)
            return
        _notify_done(db, job)


# 被重启打断的作业最多自动重跑一次；再次被打断就判失败——否则一个会把进程
# 跑崩（比如 OOM）的作业会在每次重启后被重新捡起，形成崩溃循环。
_REQUEUE_MARK = "服务重启中断，已自动重排"


def _reclaim_interrupted(db) -> None:
    """启动时接手上一进程留下的 `running` 作业。

    worker 由单例选举保证同一时刻只有一个（core/singleton.py），因此启动时看到的
    `running` 一定是上一个进程死掉时留下的：主循环只取 `pending`，这些行不接手
    就会**永远停在 running**——提交人看着"执行中"干等，前端一直轮询，直到 24 小时
    后清理把它悄悄删掉，全程没有任何提示。（第 86 轮实测确认。）
    """
    stuck = db.query(ExportJob).filter(ExportJob.status == "running").all()
    for j in stuck:
        if (j.error or "").startswith(_REQUEUE_MARK):
            j.status = "failed"
            j.error = f"{_REQUEUE_MARK}后再次被中断，请重新提交"
            j.finished_at = datetime.datetime.utcnow()
            db.commit()
            _notify_done(db, j)
            logger.warning("导出作业 id=%s 两次被重启中断，已判失败", j.id)
        else:
            j.status = "pending"
            j.error = _REQUEUE_MARK
            j.started_at = None
            db.commit()
            logger.warning("导出作业 id=%s 被重启中断，已重新排队", j.id)


def _notify_done(db, job: ExportJob) -> None:
    """作业完成/失败后通知提交人。

    没有通知的话，用户提交完只能自己去"我的导出"里反复刷新——第 64 轮的教训：
    「指派了活却没有任何信号」等于把这件事做空了。通知失败不能影响作业本身，
    因此整段包在 try 里。
    """
    try:
        import json as _json

        from app.services.notify import notify_users
        ok = job.status == "done"
        title = f"{job.file_name or job.kind} " + ("导出完成" if ok else "导出失败")
        # **必须带 params**：前端 notifyText 没有 params 时会直接回退到这里的
        # 中文 title，泰文/英文界面的用户又会看到中文——那正是早先专门修过的
        # "通知按创建者语言而非收件人语言"。带上结构化参数后，
        # 前端用 notif_export_done / notif_export_failed 按收件人语言拼装。
        params = _json.dumps({"subject": job.file_name or job.kind}, ensure_ascii=False)
        notify_users(db, [job.user_id], title=title,
                     ntype="export_done" if ok else "export_failed",
                     link="/exports", params=params,
                     body=("" if ok else (job.error or "")[:200]))
        db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("导出完成通知发送失败 job=%s（不影响作业本身）", job.id)


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
    reclaimed = False
    while True:
        try:
            from app.db import SessionLocal
            db = SessionLocal()
            try:
                if not reclaimed:
                    _reclaim_interrupted(db)
                    reclaimed = True
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
