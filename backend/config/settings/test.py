"""测试环境配置：InMemory Channel Layer，无 Redis 连接

继承 dev.py 的所有配置，仅覆盖 CHANNEL_LAYERS 和 Celery backend
为内存实现，避免 pytest 启动时连接 Redis 超时 (~53s 开销)。

用法:
    pytest --ds=config.settings.test ...
    或在 pyproject.toml 中设置 DJANGO_SETTINGS_MODULE = "config.settings.test"
"""

from .dev import *  # noqa: F401,F403

# 使用 InMemoryChannelLayer 替代 RedisChannelLayer，避免 Redis 连接超时
# 测试运行在单进程内，InMemoryChannelLayer 完全满足需求
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

# Celery 使用内存 backend，无需 Redis
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

# 默认 eager 模式，无需 Worker 进程
GAF_CELERY_MODE = "eager"
CELERY_TASK_ALWAYS_EAGER = True

# spec 2026-08-29-logging-system-consolidation: 测试日志禁止写入生产 debug 目录.
# FileLogHandler 会把 pytest 的 mock 异常/测试期错误落盘到
# debug/YYYYMMDD/backend/system/, 被 daemon 报错扫描当成"服务报错"污染
# 服务管理页计数 (实测 2026-08-29: OSError disk full / heartbeat TMError 均来自测试).
# 测试环境下 database handler 替换为 NullHandler (console 输出保留).
LOGGING["handlers"]["database"] = {
    "class": "logging.NullHandler",
}
