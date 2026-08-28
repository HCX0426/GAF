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
ENV DJANGO_SETTINGS_MODULE=config.settings.prod
RUN python manage.py collectstatic --noinput || true

# Expose port
EXPOSE 8000

# Run with gunicorn using config file
CMD ["gunicorn", "--config", "gunicorn.conf.py", "config.wsgi:application"]
