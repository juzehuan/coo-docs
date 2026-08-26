FROM python:3.11.15-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 云端主存储与本地目录回退目录（生产 NAS 走 S3 兼容接口时不再依赖挂载）
# 以非 root 运行：文件上传/同步代码的漏洞不再直接获得容器 root（bind mount 写入也不再产生 root 属主文件）
# uid 1000 与宿主部署用户一致，保证 ./data/uploads、./nas_mount bind mount 可读写
RUN mkdir -p /app/data/uploads /app/data/nas \
    && useradd --uid 1000 --no-create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
# 注：不开启 --forwarded-allow-ips "*" —— 应用自行按可信约定读取 nginx 设置的 X-Real-IP（core/audit.py），
# 放开 uvicorn 层的全局信任会让非 compose 拓扑下任意对端伪造 request.client
# --no-access-log：应用内的 RequestLogMiddleware 已记录同样信息且更完整
# （真实客户端 IP、用户身份、耗时、按状态码分级），保留 uvicorn 访问日志只会
# 让每个请求出现两条，并让每 30 秒一次的健康检查淹没业务日志
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
