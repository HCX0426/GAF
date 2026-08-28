from django.apps import AppConfig


class ExecutionsConfig(AppConfig):
    """执行管理应用配置"""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'executions'
    verbose_name = '执行管理'
