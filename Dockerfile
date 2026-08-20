# Bilibilibs 生产镜像：gunicorn 托管 Flask 应用
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production

WORKDIR /app

# 系统依赖（lxml、cryptography 等编译需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libxml2-dev libxslt1-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 先装依赖（利用层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 非 root 运行
RUN useradd -m appuser
USER appuser

EXPOSE 8000

# gunicorn 4 worker；超时调大以容纳慢采集接口
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "--timeout", "120", "--graceful-timeout", "30", "run:app"]
