# 后端 API + Worker 共用镜像（通过 CMD 区分进程）
FROM python:3.12-slim

WORKDIR /app

# 先复制依赖清单以利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源码
COPY . .

ENV PYTHONUNBUFFERED=1
ENV WENLV_WORKSPACE_ROOT=/app/workspace

# 默认启动 API（worker 由 compose 覆盖 command）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
