"""开发环境配置：使用 Redis Channel Layer，Celery EAGER 模式 (无 Worker/Beat 进程)

GAF_CELERY_MODE=eager (默认):
  - CELERY_TASK_ALWAYS_EAGER=True: 任务在 daphne 进程内同步执行, 不进 Redis 队列
  - APScheduler 在 daphne 进程内处理定时任务, 无需独立 Beat 进程
  - 启动快 ~26s, 适合单机开发

GAF_CELERY_MODE=celery (设 .env):
  - CELERY_TASK_ALWAYS_EAGER=False: 任务进 Redis 队列, 由 Worker 消费
  - 需要独立 Worker + Beat 进程, 适合分布式部署
"""

from .base import *  # noqa: F401,F403

DEBUG = True

# N194 fix: 不再覆盖 base.py 的 RedisChannelLayer 配置.
# InMemoryChannelLayer 仅适用于单进程内同步测试, dispatch_task (Celery EAGER
# 线程) -> agent consumer (daphne event loop) 跨线程消息传递会丢失.
# base.py 已配置 RedisChannelLayer (localhost:6379), 直接继承即可.
# CELERY_TASK_ALWAYS_EAGER 由 base.py 根据 GAF_CELERY_MODE 环境变量自动设置.
# 默认 eager 模式 (同步执行), 设 GAF_CELERY_MODE=celery 则进 Redis 队列.
