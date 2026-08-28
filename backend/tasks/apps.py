from django.apps import AppConfig


class TasksConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tasks'

    def ready(self):
        # P-020-D: 注册 TaskExecution 状态变更信号 (失败时触发 ActionChain 恢复)
        from . import signals  # noqa: F401
