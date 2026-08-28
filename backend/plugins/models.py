from django.db import models


def plugin_package_upload_path(instance, filename):
    """生成插件包上传路径"""
    return f'plugins/{instance.name}/{filename}'


class PluginHook(models.Model):
    """插件钩子模型，定义插件的钩子函数注册和执行优先级。"""

    plugin_name = models.CharField(
        max_length=100,
        verbose_name='插件名称',
    )
    event_type = models.CharField(
        max_length=50,
        verbose_name='事件类型',
    )
    hook_function = models.CharField(
        max_length=255,
        verbose_name='钩子函数',
    )
    priority = models.IntegerField(
        default=0,
        verbose_name='优先级',
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='是否启用',
    )

    class Meta:
        db_table = 'plugins_pluginhook'
        ordering = ['-priority']
        verbose_name = '插件钩子'
        verbose_name_plural = '插件钩子'
        unique_together = [('plugin_name', 'event_type', 'hook_function')]

    def __str__(self):
        return f'{self.plugin_name}.{self.hook_function} [{self.event_type}]'


class PluginPackage(models.Model):
    """插件包模型，存储已上传或已安装的插件包元信息。"""

    name = models.CharField(
        max_length=150,
        unique=True,
        verbose_name='插件名称',
    )
    version = models.CharField(
        max_length=50,
        verbose_name='版本号',
    )
    author = models.CharField(
        max_length=150,
        blank=True,
        default='',
        verbose_name='作者',
    )
    description = models.TextField(
        blank=True,
        default='',
        verbose_name='描述',
    )
    manifest = models.JSONField(
        default=dict,
        verbose_name='manifest 信息',
    )
    package_path = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name='包文件路径',
    )
    is_installed = models.BooleanField(
        default=False,
        verbose_name='是否已安装',
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name='是否启用',
    )
    installed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='安装时间',
    )
    checksum = models.CharField(
        max_length=64,
        blank=True,
        default='',
        verbose_name='校验和',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='更新时间',
    )

    class Meta:
        db_table = 'plugins_pluginpackage'
        ordering = ['-created_at']
        verbose_name = '插件包'
        verbose_name_plural = '插件包'

    def __str__(self):
        return f'{self.name} v{self.version}'


class PluginSandbox(models.Model):
    """插件沙箱模型，记录插件在子进程沙箱中的执行状态。"""

    class Status(models.TextChoices):
        IDLE = 'idle', '空闲'
        RUNNING = 'running', '运行中'
        STOPPED = 'stopped', '已停止'
        ERROR = 'error', '错误'

    plugin = models.ForeignKey(
        PluginPackage,
        on_delete=models.CASCADE,
        related_name='sandboxes',
        verbose_name='插件',
    )
    pid = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='进程ID',
    )
    status = models.CharField(
        max_length=50,
        choices=Status.choices,
        default=Status.IDLE,
        verbose_name='状态',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
    )

    class Meta:
        db_table = 'plugins_pluginsandbox'
        ordering = ['-created_at']
        verbose_name = '插件沙箱'
        verbose_name_plural = '插件沙箱'

    def __str__(self):
        return f'Sandbox({self.plugin.name}) [{self.status}]'
