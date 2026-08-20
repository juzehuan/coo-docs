FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 云端主存储与 NAS 挂载点（生产时 NAS_ROOT 挂载隧道客户端提供的目录）
RUN mkdir -p /app/data/uploads /app/data/nas

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
