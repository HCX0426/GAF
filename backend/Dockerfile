FROM python:3.11-slim

# Install system dependencies
# 2026-08-03 spec: dev/prod 统一 SQLite, 不再需要 libpq-dev (PG 客户端头文件)
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (prod slice includes gunicorn + whitenoise)
COPY requirements/prod.txt ./requirements/prod.txt
COPY requirements/base.txt ./requirements/base.txt
RUN pip install --no-cache-dir -r requirements/prod.txt

# Copy application code
COPY . .

# Collect static files (settings module must be prod)
# D4 (评审 2026-09-05): 移除 `|| true` — collectstatic 失败必须让构建失败,
# 否则故障被推迟到上线后表现为静态资源 404。
ENV DJANGO_SETTINGS_MODULE=config.settings.prod
RUN python manage.py collectstatic --noinput

# Expose port
EXPOSE 8000

# D1 (评审 2026-09-05): gunicorn wsgi 无 WebSocket; daphne 走 ASGI,
# http 请求经 asgi.py 的 django_asgi_app 同样可用。
# 容器内必须绑定 0.0.0.0 才能被端口映射转发 (与 systemd 侧 127.0.0.1 不同)。
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
