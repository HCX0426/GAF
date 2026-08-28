import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

from config.app_info import API_PREFIX, APP_ROUTES, APP_VERSION

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR.parent / ".env")

SECRET_KEY = os.getenv(
    "SECRET_KEY", "django-insecure-gaf-dev-change-me-in-production"
)
# TD-334: 检测到不安全默认值时, 生产环境必须显式配置 SECRET_KEY
if SECRET_KEY == "django-insecure-gaf-dev-change-me-in-production" and os.getenv("DJANGO_SETTINGS_MODULE", "").endswith("prod"):
    raise RuntimeError("Production SECRET_KEY must be set via environment variable (DJANGO_SETTINGS_MODULE ends with 'prod').")

# TD-334: DEBUG 默认 False (安全优先), dev.py 显式 True
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "django_celery_beat",
    "drf_spectacular",
    "channels",
    "accounts",
    "agents",
    "tasks",
    "resources",
    "monitors",
    "skills",
    "debug",
    # "qa" — 2026-08-04 合并到 gaf_ai
    "protocol",
    "notifications",
    "gamestate",
    "plugins",
    "scheduler",
    "pipeline",
    "executions",
    "settings",
    # "search" — 2026-08-04 合并到 gaf_core.search
    "gaf_ai",
    # "i18n" — 2026-08-04 合并到 gaf_core.i18n
    # "tracing" — 2026-08-04 合并到 gaf_core.tracing
    "gaf_core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "gaf_core.tracing.middleware.TracingMiddleware",
    "gaf_core.middleware.PerfMiddleware",
    "gaf_core.middleware.UnifiedResponseMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": os.getenv("DB_ENGINE", "django.db.backends.sqlite3"),
        "NAME": os.getenv("DB_NAME", BASE_DIR / "db.sqlite3"),
        # 2026-08-03 spec: dev/prod 统一 SQLite + WAL, 单机部署 < 100 并发场景
        # WAL 模式: 读写并发不阻塞, 写性能 ~1000 TPS
        # synchronous=NORMAL: 崩溃时可能丢最后一两个事务, 单机可接受
        # busy_timeout=5000: 写锁等待 5s, 避免 SQLITE_BUSY 立即失败
        "OPTIONS": {
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=5000;",
            "transaction_mode": "IMMEDIATE",
        },
    }
}

# Cache — explicit LocMemCache for dev (default if not declared). Production
# overrides this with Redis when REDIS_URL is set (see config/settings/prod.py).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "gaf-dev-cache",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTH_USER_MODEL = "accounts.User"

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

# ---------- i18n Configuration (P-033 Phase 4) ----------
# Available languages for backend API responses (must match frontend i18n locales)
LANGUAGES = [
    ("zh-hans", "简体中文"),
    ("en", "English"),
    ("ja", "日本語"),
    ("ko", "한국어"),
]
# Translation files location: backend/locale/<lang>/LC_MESSAGES/django.po
LOCALE_PATHS = [BASE_DIR / "locale"]

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------- Debug directory (N194 归一化, 2026-07-28) ----------
# Root for ALL per-execution debug artifacts (backend + agent): run.log,
# structured.jsonl, screenshots/, meta.json, archives/.
#
# 归一化前: backend 写 <BASE_DIR>/debug/ (即 backend/debug/), agent 写 ./debug/
# (相对 CWD 飘忽). 两者不归一, 用户调试要跨多个根目录翻找.
#
# 归一化后: 统一到 d:/code/GAF/debug/. 每次执行一个目录:
#   <DEBUG_DIR>/<YYYYMMDD_HHMMSS>_<safe_task_name>_<exec_id_suffix8>/
#     ├── meta.json            # 用户可读元信息 (视角 B)
#     ├── run.log              # backend FileLogHandler
#     ├── structured.jsonl     # agent StructuredLogger
#     └── screenshots/{annotated,raw}/  # agent DebugImageSaver
#
# FileLogHandler reads this via getattr(settings, "DEBUG_DIR", "./debug")
# so unsetting here would fall back to "./debug" (relative to CWD) — keep
# it explicit so all deployments land in the same on-disk location.
#
# 默认使用 <项目根>/debug (即 d:/code/GAF/debug), 与 agent 侧
# AgentConfig.debug_dir 默认值对齐. BASE_DIR 是 backend/, 所以要 .parent
# 才能拿到项目根. 通过 DEBUG_DIR 环境变量可覆盖.
DEBUG_DIR = os.getenv("DEBUG_DIR", str(BASE_DIR.parent / "debug"))
# Archives subdir — derived from DEBUG_DIR unless explicitly overridden.
# cleanup_old_archives scans here for *.tar.gz older than 30 days.
DEBUG_ARCHIVE_DIR = os.getenv("DEBUG_ARCHIVE_DIR", os.path.join(DEBUG_DIR, "archives"))
# Archive retention — cleanup_old_archives deletes files older than this
# many days (spec §8.3 — default 30 days).
DEBUG_ARCHIVE_RETENTION_DAYS = int(os.getenv("DEBUG_ARCHIVE_RETENTION_DAYS", "30"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "EXCEPTION_HANDLER": "gaf_core.exceptions.unified_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # H8 fix: enable global rate limiting to mitigate brute-force / credential
    # stuffing on auth endpoints and to protect the platform from runaway
    # authenticated clients. Per-IP anon bucket catches unauthenticated abuse;
    # per-user bucket catches authenticated abuse. Login endpoint adds a
    # stricter 'login' scoped throttle (see accounts/views.py login view).
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        # 600/min: 2026-08-28 full_routes 月度全量 E2E（80s 内 46 路由多请求）
        # 实测触发 429，调宽避免健康测试自造限流假红；登录端 login 仍 5/min。
        "user": "600/min",
        "login": "5/min",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "GAF API",
    "DESCRIPTION": "Game Automation Framework API 文档",
    # H22 fix: source API doc version from app_info.APP_VERSION (single source
    # of truth) instead of a hardcoded "1.0.0" that drifted out of sync.
    "VERSION": APP_VERSION,
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SECURITY": [{"BearerAuth": []}],
    "APPEND_COMPONENTS": {
        "securitySchemes": {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
            },
        },
    },
    # TD-268: resolve enum naming collisions for fields named "status"/"role"
    # that have different choice sets across models. drf-spectacular expects
    # keys = desired public enum names, values = dotted module path strings
    # pointing at the TextChoices subclass (see _load_enum_name_overrides in
    # drf_spectacular.plumbing).
    "ENUM_NAME_OVERRIDES": {
        # [pending, running, success, failed, cancelled] — chain execution status
        "ChainExecutionStatusEnum": "pipeline.models.TaskChainExecution.Status",
        # [online, offline, busy, idle] — agent heartbeat status
        "AgentHeartbeatStatusEnum": "agents.models.Agent.Status",
        # [online, offline, busy, error] — device lifecycle status
        "DeviceStatusEnum": "agents.models.Device.Status",
        # [pending, running, completed, failed] — shared by ModelEvaluation
        # and AgentSession (gaf_ai); single override resolves the collision
        # since both use the same choice set.
        "AgentSessionStatusEnum": "gaf_ai.agent.models.AgentSession.Status",
        # [online, offline] — protocol AgentSession (WebSocket connection state)
        "ProtocolAgentSessionStatusEnum": "protocol.models.AgentSession.Status",
        # [pending, running, paused, success, failed, cancelled, force_terminated]
        "TaskExecutionStatusEnum": "tasks.models.TaskExecution.Status",
        # [pending, running, success, failed, skipped]
        "ExecutionStepStatusEnum": "tasks.models.ExecutionStep.Status",
        # [idle, running, stopped, error] — plugin sandbox lifecycle
        "PluginSandboxStatusEnum": "plugins.models.PluginSandbox.Status",
        # [init, running, paused, stopping, stopped, failed] — unattended session
        "UnattendedSessionStatusEnum": "scheduler.models.UnattendedSession.Status",
        # [viewer, operator, admin] — user role
        "UserRoleEnum": "accounts.models.User.Role",
    },
}

GAF_REMEMBER_ME_DAYS = int(os.getenv("GAF_REMEMBER_ME_DAYS", "30"))

GAF_APP_NAME = os.getenv("GAF_APP_NAME", "GAF")

# ── LLM configuration ──────────────────────────────────────────────
# Preferred provider is configured in DB (LLMConfig). Backup, local,
# and the API-key encryption key are env-driven so they can be kept
# out of the database and rotated without a migration.
#
# To enable API-key encryption at rest, generate a key with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# and set it as GAF_LLM_API_KEY_ENCRYPTION_KEY in your .env. When unset,
# keys are stored as plaintext (backward compat — see settings/crypto.py).
GAF_LLM_API_KEY_ENCRYPTION_KEY = os.getenv("GAF_LLM_API_KEY_ENCRYPTION_KEY", "")

# Backup provider (used when the preferred DB-configured provider fails).
LLM_BACKUP_API_KEY = os.getenv("LLM_BACKUP_API_KEY", "")
LLM_BACKUP_PROVIDER = os.getenv("LLM_BACKUP_PROVIDER", "openai")
LLM_BACKUP_BASE_URL = os.getenv("LLM_BACKUP_BASE_URL", "")
LLM_BACKUP_MODEL = os.getenv("LLM_BACKUP_MODEL", "")

# Local provider (Ollama / vLLM on localhost — usually no API key needed).
LLM_LOCAL_BASE_URL = os.getenv("LLM_LOCAL_BASE_URL", "")
LLM_LOCAL_API_KEY = os.getenv("LLM_LOCAL_API_KEY", "")
LLM_LOCAL_PROVIDER = os.getenv("LLM_LOCAL_PROVIDER", "custom")
LLM_LOCAL_MODEL = os.getenv("LLM_LOCAL_MODEL", "llama3")

# Unified API response envelope. When enabled, all JSON responses are wrapped as
# { code, message, data }. P0-2 fix (AI 可调试性, 2026-07-27): default changed
# from False to True — consistent response structure lets AI classify errors
# by `code` field without parsing free-form error messages. Frontend
# api/client.ts response interceptor unwraps the envelope transparently, so
# existing frontend code keeps working with raw payloads. Set to False via
# env var only for legacy clients that expect DRF default format.
GAF_UNIFIED_RESPONSE_ENABLED = (
    os.getenv("GAF_UNIFIED_RESPONSE_ENABLED", "True").lower() in ("true", "1", "yes")
)

BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "5173"))
FRONTEND_URL = os.getenv("FRONTEND_URL", f"http://localhost:{FRONTEND_PORT}")

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI", f"http://localhost:{BACKEND_PORT}/{API_PREFIX}/{APP_ROUTES['accounts']}/auth/oauth/github/callback/")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", f"http://localhost:{BACKEND_PORT}/{API_PREFIX}/{APP_ROUTES['accounts']}/auth/oauth/google/callback/")

SIMPLE_JWT = {
    # TD-334: JWT access token 寿命对齐 api-contract.md (15 分钟)
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_LIFETIME", "15"))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=int(os.getenv("JWT_REFRESH_TOKEN_LIFETIME", "7"))
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}
# P2-7: 30min access token reduces refresh frequency (was 15min).
# 30 days * 24h * 2 refreshes/h = ~1440 refreshes vs ~2880 at 15min.
# Less refresh = less chance of concurrent refresh race condition.

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [
                (os.getenv("CHANNEL_LAYERS_HOST", "localhost"), int(os.getenv("CHANNEL_LAYERS_PORT", "6379"))),
            ],
        },
    }
}

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = os.getenv(
    "CELERY_RESULT_BACKEND", "redis://localhost:6379/2"
)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
# Celery 执行模式: "eager" (开发模式, 无 Worker/Beat 进程, 任务在 daphne 内同步执行)
# 或 "celery" (生产模式, 需要独立 Worker + Beat 进程, 用于分布式部署).
# 默认 eager — 单机开发不需要 Worker + Beat 两个进程的启动开销.
GAF_CELERY_MODE = os.getenv("GAF_CELERY_MODE", "eager").lower()
CELERY_TASK_ALWAYS_EAGER = (GAF_CELERY_MODE == "eager")
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ---------- Device Health & Agent Auto-Start ----------
# Device heartbeat polling interval in seconds.
# Previous default was 2s which caused excessive adb subprocess spawning and
# led to GPU driver crashes (black screen incident 2026-07-11). 30s is safe
# for development; production may set a lower value via env var.
GAF_HEARTBEAT_INTERVAL = int(os.getenv("GAF_HEARTBEAT_INTERVAL", "30"))

# Log retention: LogEntry records older than this many days are deleted by
# the cleanup-old-logs celery beat task (runs daily). Default 7 days —
# enough to debug issues from the past week without unbounded table growth.
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", "7"))

# Whether to auto-start the local Agent subprocess when Django runserver starts.
# Default: DISABLED — admin-elevated agent processes survive Django autoreload,
# causing multiple agents to stack during code changes. Each agent's MonitorManager
# takes screenshots every 30s, and N agent processes = N× screenshots, which can
# trigger GPU driver TDR (black screen incident 2026-07-11, recurred 2026-07-11).
# Enable explicitly with GAF_AUTO_START_AGENT=1 when you need task pipeline testing.
GAF_AUTO_START_AGENT = os.getenv("GAF_AUTO_START_AGENT", "0").lower() in ("true", "1", "yes")

# 统一调试模式（N196, 2026-08-01）：控制所有 app 的调试行为。
# agent 保存标注调试截图、backend 传递 debug_mode=True、结构化日志全量输出。
# 设为 1 启用，所有 app 通过此单一配置控制调试模式。
# 各 app 的独立调试开关以此值为默认值，可被各自命令行参数覆盖。
GAF_DEBUG = os.getenv("GAF_DEBUG", "0").lower() in ("true", "1", "yes")
GAF_ALLOW_LOCALHOST_BYPASS = os.getenv("GAF_ALLOW_LOCALHOST_BYPASS", "0").lower() in ("true", "1", "yes")

# ---------- TLS / SSL 配置（用于 Daphne ASGI Server） ----------
# SSL 证书文件路径（PEM 格式），留空则不启用 HTTPS
GAF_SSL_CERT_FILE = os.getenv("SSL_CERT_FILE", "")
# SSL 私钥文件路径
GAF_SSL_KEY_FILE = os.getenv("SSL_KEY_FILE", "")
# 是否启用 HTTPS（由证书路径是否同时存在自动判定）
GAF_SSL_ENABLED = bool(GAF_SSL_CERT_FILE and GAF_SSL_KEY_FILE)
# HTTPS 监听端口
GAF_HTTPS_PORT = int(os.getenv("HTTPS_PORT", "8443"))

# CORS 允许的前端源 — 优先从 CORS_ALLOWED_ORIGINS 环境变量读取（逗号分隔），
# 未设置时从 FRONTEND_PORT/FRONTEND_URL 推导默认值。
# 环境变量格式: "http://localhost:5173,http://127.0.0.1:5173"
_env_cors = os.getenv("CORS_ALLOWED_ORIGINS")
if _env_cors:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _env_cors.split(",") if o.strip()]
else:
    CORS_ALLOWED_ORIGINS = [
        f"http://localhost:{FRONTEND_PORT}",
        f"http://127.0.0.1:{FRONTEND_PORT}",
        FRONTEND_URL,
    ]
CORS_ALLOW_CREDENTIALS = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        # FileLogHandler archives records to per-execution files
        # at <debug_dir>/logs/<execution_id>/run.log (spec §2.2).
        # N192-A2 fix (2026-07-28, BD2 get_email 测试发现):
        # 原默认 WARNING 阈值太严 — 执行失败时若仅超时 (无 WARNING+ 日志),
        # per-execution 目录根本不创建, AI 调试无法回溯节点执行链路.
        # 改为 INFO 让节点执行日志 (含 step boundary / retry / failure) 落盘.
        # 阈值仍可通过 LOG_DB_LEVEL 环境变量覆盖 (生产可设 WARNING 减少磁盘占用).
        # Legacy handler name "database" kept for back-compat with
        # env vars / deployments that reference it; resolves to
        # FileLogHandler (DatabaseLogHandler is now an alias).
        "database": {
            "level": os.getenv("LOG_DB_LEVEL", "INFO"),
            "class": "gaf_core.handlers.FileLogHandler",
        },
    },
    "root": {
        "handlers": ["console", "database"],
        "level": os.getenv("LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django": {
            # Django's own request/response/DB logging goes to console only,
            # not to the file archive (avoid bloat from per-request SQL logs).
            "handlers": ["console"],
            "level": os.getenv("LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        # Prevent FileLogHandler's own internal errors from recursing
        # back into the file handler.
        "gaf_core.handlers": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        # N198: APScheduler 在 eager 模式下启动时会产生大量 INFO 日志
        # (registering jobs, adding jobs, scheduler started).
        # 这些日志不包含 execution_context, 走 system 日志路径足够.
        # 避免其 INFO 日志触发 FileLogHandler 的 Redis 广播 (Redis 未启动时
        # 每次超时 ~4s, 8 个 job × 2 条日志 = 16 次超时 = ~64s 浪费).
        "apscheduler": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
