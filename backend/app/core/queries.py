"""跨模块共用的查询辅助。

放在这里而不是各 api 模块里各写一份：第 72 轮排查发现 `_latest_version`
在 `api/todo.py` 与 `api/packages.py` 各有一份、`_factory_ids` 在
`api/dashboard.py` 与 `api/orders.py` 各有一份。这两对当时语义还一致，
但同一段逻辑复制多份必然迟早跑偏——第 66 轮(排序兜底漏了三处)、
第 71 轮(引用计数三份拷贝里有一份没跟上两轮修复)都是这么来的。
"""
from sqlalchemy.orm import Session

from app.models import PackageVersion


def latest_version(db: Session, pkg_id: int) -> PackageVersion | None:
    """资料包的最新版本。

    按雪花 ID 而非 created_at 排序：created_at 是**秒级精度**（datetime 无小数秒），
    同秒创建的两个版本比不出先后（同一原因见第 66 轮的分页排序）。

    注意调用方的语义边界：**"最新版本"不等于"待办候选"**。
    第 70 轮实测，一个已提交待审的版本只要有人在它之上再建一个草稿，
    最新版就变成那个草稿，待审的那条会从所有人的待办里消失。
    需要"待我处理"时必须取「最新版本 ∪ 所有在审版本」，见 todo/dashboard。
    """
    return (
        db.query(PackageVersion)
        .filter(PackageVersion.package_id == pkg_id)
        .order_by(PackageVersion.id.desc())
        .first()
    )
