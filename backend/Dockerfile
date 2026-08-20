FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 云端主存储与本地目录回退目录（生产 NAS 走 S3 兼容接口时不再依赖挂载）
RUN mkdir -p /app/data/uploads /app/data/nas

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
