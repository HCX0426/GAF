"""Production settings: SQLite + WAL, Redis, WhiteNoise, HTTPS-ready."""

import os

from django.conf.global_settings import STORAGES as _DEFAULT_STORAGES

from .base import *  # noqa: F401,F403,E402

DEBUG = False

ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]

# Security headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# HTTPS-related cookie security (set SECURE_SSL_REDIRECT=True when behind HTTPS)
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "false").lower() == "true"
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true"
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", "true").lower() == "true"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
# D6 (评审 2026-09-05): HSTS preload 是"不可逆"操作 —— 域名一旦进入浏览器
# 内置 preload 列表, 回滚极其困难; includeSubDomains 还会连带强制所有子域名。
# 默认关闭 preload (env 可覆盖); 启用 HTTPS 后先以较小 SECURE_HSTS_SECONDS
# 观察, 稳定后再显式打开 preload。未启用 HTTPS 时 HSTS 头本身不下发
# (仅在 request.is_secure() 时, 经 SECURE_PROXY_SSL_HEADER 正确判定)。
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("SECURE_HSTS_INCLUDE_SUBDOMAINS", "true").lower() == "true"
SECURE_HSTS_PRELOAD = os.getenv("SECURE_HSTS_PRELOAD", "false").lower() == "true"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Database — 2026-08-03 spec: dev/prod 统一 SQLite + WAL (单机部署 < 100 并发)
# base.py 已配置 SQLite + WAL + busy_timeout, prod.py 不再默认 PG.
# 如需切换 PG/MySQL, 通过 DB_ENGINE 环境变量覆盖 (不建议, 单机部署 PG 性能过剩).
if os.getenv("DB_ENGINE"):
    DATABASES = {
        "default": {
            "ENGINE": str(os.getenv("DB_ENGINE")),
            "NAME": os.getenv("DB_NAME", "gaf"),
            "USER": os.getenv("DB_USER", "gaf"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
            "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
        }
    }

# CORS — read from env (comma-separated list)
_cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
if _cors_origins:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_origins.split(",") if o.strip()]

# Static files — WhiteNoise for serving static assets in production
# Insert SecurityMiddleware + WhiteNoiseMiddleware at the head while preserving
# all existing middleware (e.g. CorsMiddleware). Previously MIDDLEWARE[1:] silently
# dropped CorsMiddleware, breaking CORS in production.
MIDDLEWARE = [m for m in MIDDLEWARE if m != "django.middleware.security.SecurityMiddleware"]  # noqa: F405
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
] + MIDDLEWARE  # noqa: F405

# D8 (评审 2026-09-05 实测发现): Django 5.1 已移除 STATICFILES_STORAGE 设置,
# 旧的 `STATICFILES_STORAGE = "whitenoise.storage..."` 在 5.2.15 下被
# **静默忽略** — WhiteNoise 的 CompressedManifest 存储自升级 Django 5.2 起
# 从未生效 (又一处"配置加载成功"假象下的静默降级)。改用 STORAGES dict。
# 注意: manifest 存储要求 collectstatic 已运行 (Docker 构建内已强制),
# 裸机更新代码后也必须执行 `python manage.py collectstatic`。
STORAGES = {
    **_DEFAULT_STORAGES,
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Cache — prefer Redis-backed cache in production
if os.getenv("REDIS_URL"):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": str(os.getenv("REDIS_URL")),
        }
    }

# Email — configurable via env (default to console for dev-like fallback)
if os.getenv("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.getenv("EMAIL_HOST")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
    DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@gaf.local")
