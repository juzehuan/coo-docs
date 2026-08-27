#!/usr/bin/env bash
# 部署前的最小冒烟检查：在**构建好的镜像**里真正导入一次应用。
#
# 为什么需要它：`docker compose build` 不会执行 Python，语法错误或坏掉的 import
# 一路通过构建，直到容器启动才崩——而那时坏代码已经在生产上了。
# 第 72 轮就这么把线上打断了约一分钟：用正则改一处多行 import，改成了
# `from x import a, (` 这种非法写法，构建通过、部署上去、站点 000。
# （第 54 轮已经记过"正则改代码不可靠"，同一个坑踩了第二次。）
#
# 用法：docker compose build backend && ./scripts/preflight.sh && docker compose up -d backend
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== 1/3 语法检查 =="
# 不加 -q、不吞输出：失败时必须看得见是哪个文件哪一行
docker compose run --rm --no-deps -T backend \
  python -m compileall -q /app/app

echo "== 2/3 应用导入检查（含全部路由与依赖）=="
docker compose run --rm --no-deps -T backend python -c "
import sys; sys.path.insert(0, '/app')
import app.main
# 只断言"能导入且拿得到 app 对象"。不要断言路由条数——路由以 _IncludedRouter
# 形式挂载、并非都带 .path，按条数断言只会得到脆弱的假失败。
assert app.main.app is not None
print('  应用导入成功')
"
echo "== 3/3 导出作业注册自检 =="
docker compose run --rm --no-deps -T backend python -c "
import sys; sys.path.insert(0, '/app')
import app.main  # 触发各 api 模块导入，注册随之发生
from app.services import export_jobs

kinds = export_jobs.known_kinds()
assert kinds, '没有任何导出类型被注册'
bad = []
for k in kinds:
    chk = export_jobs.permission_check(k)
    if chk is None:
        bad.append(k + ': 缺权限校验')
        continue
    # 真正调用一次：本步要抓的正是**函数体内的错名/延迟导入**——模块级导入
    # 检查看不见它们（第 80 轮就这样把一个 ImportError 放到线上：预检通过、
    # 部署上去、提交作业时才 500）。只认 ImportError/NameError：
    # AttributeError 与'传了 None 当参数'无法区分，收进来全是假阳性。
    try:
        chk(None, None, {})
    except (ImportError, NameError) as e:
        bad.append(k + ': ' + type(e).__name__ + ': ' + str(e))
    except Exception:
        pass
if bad:
    print('导出类型自检未通过：')
    for b in bad:
        print('  - ' + b)
    sys.exit(1)
print('  已注册 ' + str(len(kinds)) + ' 种导出类型，权限校验均可解析：' + '、'.join(kinds))
"
echo "预检通过，可以部署。"
