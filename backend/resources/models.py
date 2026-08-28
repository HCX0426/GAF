from django.conf import settings
from django.db import models


class ResourcePack(models.Model):
    """Resource pack model managing template images, configs and other resources."""

    name = models.CharField(
        max_length=255,
        verbose_name='Resource pack name',
    )
    version = models.CharField(
        max_length=50,
        verbose_name='Version',
    )
    target_app = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Target application',
    )
    author = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Author',
    )
    directory_path = models.CharField(
        max_length=512,
        verbose_name='Resource directory path',
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name='Is active',
    )
    gaf_version_compat = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='GAF version compatibility',
    )
    description = models.TextField(
        blank=True,
        verbose_name='Description',
    )
    config_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Config data (settings.json content)',
    )
    game_profile = models.ForeignKey(
        'gamestate.GameProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resource_packs',
        verbose_name='所属游戏档案',
        help_text='R37-P1: 资源包所属的游戏档案（nullable，兼容老资源包）',
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
        db_table = 'resources_resourcepack'
        ordering = ['-id']
        verbose_name = '资源包'
        verbose_name_plural = '资源包'
        unique_together = [('name', 'version')]

    def __str__(self):
        return f'{self.name} v{self.version}'

    # ── N197-8: Server-specific template loading ──────────────────────

    def get_servers(self) -> dict:
        """Return the servers config from config_data.

        The ``config_data`` JSONField can contain a ``servers`` key mapping
        server region codes to display names, e.g.::

            {
                "servers": {
                    "cn": {"label": "国服", "template_dir": "templates/cn"},
                    "jp": {"label": "日服", "template_dir": "templates/jp"},
                    "global": {"label": "国际服", "template_dir": "templates/global"}
                }
            }

        Returns:
            dict: Server config dict, or empty dict if not configured.
        """
        return self.config_data.get('servers', {}) if isinstance(self.config_data, dict) else {}

    def get_server_label(self, server_region: str) -> str:
        """Return the human-readable label for a server region.

        Args:
            server_region: Server region code (e.g. 'cn', 'jp').

        Returns:
            str: Human-readable label, or the region code itself if not found.
        """
        servers = self.get_servers()
        server_info = servers.get(server_region, {})
        if isinstance(server_info, dict):
            return server_info.get('label', server_region)
        return server_region

    def get_template_dir_for_server(self, server_region: str) -> str:
        """Return the template subdirectory path for a given server.

        If the server has a custom ``template_dir`` in config, use it.
        Otherwise fall back to ``templates/<server_region>/``.
        Default (no server match) returns ``templates/common/``.

        Args:
            server_region: Server region code (e.g. 'cn', 'jp').

        Returns:
            str: Relative template directory path under the pack root.
        """
        servers = self.get_servers()
        server_info = servers.get(server_region, {})
        if isinstance(server_info, dict) and 'template_dir' in server_info:
            return server_info['template_dir']
        if server_region in servers:
            return f'templates/{server_region}/'
        return 'templates/common/'

    def get_templates_for_server(self, server_region: str = 'cn'):
        """Query templates suitable for the given server region.

        Returns templates from the server-specific subdirectory first,
        falling back to ``templates/common/`` if no server-specific
        templates exist.

        Args:
            server_region: Server region code (default 'cn' = 国服).

        Returns:
            QuerySet of Template instances.
        """
        from resources.models import Template

        # Try server-specific templates
        template_dir = self.get_template_dir_for_server(server_region)
        qs = Template.objects.filter(
            resource_pack=self,
            image_path__startswith=template_dir,
            is_active=True,
        )
        if qs.exists():
            return qs

        # Fall back to common templates
        return Template.objects.filter(
            resource_pack=self,
            image_path__startswith='templates/common/',
            is_active=True,
        )


class Tag(models.Model):
    """Simple tag for templates, with optional display color."""

    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='标签名称',
    )
    color = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='标签颜色',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
    )

    class Meta:
        db_table = 'resources_tag'
        ordering = ['name']
        verbose_name = '标签'
        verbose_name_plural = '标签'

    def __str__(self):
        return self.name


class Template(models.Model):
    """模板模型，存储图像识别模板图片及其元数据。"""

    resource_pack = models.ForeignKey(
        ResourcePack,
        on_delete=models.CASCADE,
        related_name='templates',
        verbose_name='关联资源包',
    )
    name = models.CharField(
        max_length=255,
        verbose_name='模板名称',
    )
    image_path = models.CharField(
        max_length=512,
        verbose_name='图片路径',
    )
    template_type = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='模板类型',
    )
    match_threshold = models.FloatField(
        default=0.8,
        verbose_name='匹配阈值',
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='是否启用',
    )
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name='templates',
        verbose_name='标签',
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
        db_table = 'resources_template'
        ordering = ['-id']
        verbose_name = '模板'
        verbose_name_plural = '模板'
        unique_together = [('resource_pack', 'name')]

    def __str__(self):
        return f'{self.name} ({self.resource_pack.name})'


class TemplateVersion(models.Model):
    """Snapshot of a Template at a point in time, allowing restore to previous versions."""

    template = models.ForeignKey(
        Template,
        on_delete=models.CASCADE,
        related_name='versions',
        verbose_name='关联模板',
    )
    version_number = models.IntegerField(
        verbose_name='版本号',
    )
    snapshot_data = models.JSONField(
        default=dict,
        verbose_name='快照数据',
    )
    comment = models.CharField(
        max_length=500,
        blank=True,
        verbose_name='版本备注',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='创建者',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
    )

    class Meta:
        db_table = 'resources_templateversion'
        ordering = ['-version_number']
        verbose_name = '模板版本'
        verbose_name_plural = '模板版本'
        unique_together = [('template', 'version_number')]

    def __str__(self):
        return f'{self.template.name} v{self.version_number}'


class TemplateAnnotation(models.Model):
    """模板标注模型，存储模板图片的区域标注数据。"""

    template = models.ForeignKey(
        Template,
        on_delete=models.CASCADE,
        related_name='annotations',
        verbose_name='关联模板',
    )
    annotation_type = models.CharField(
        max_length=50,
        verbose_name='标注类型',
    )
    points = models.JSONField(
        default=dict,
        verbose_name='标注坐标点',
    )
    label = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='标签名称',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
    )

    class Meta:
        db_table = 'resources_templateannotation'
        ordering = ['-id']
        verbose_name = '模板标注'
        verbose_name_plural = '模板标注'

    def __str__(self):
        return f'{self.template.name} - {self.annotation_type}'


class RecognizerBenchmark(models.Model):
    """识别器基准测试模型，记录识别引擎的性能基准数据。"""

    recognizer_type = models.CharField(
        max_length=50,
        verbose_name='识别器类型',
    )
    engine_name = models.CharField(
        max_length=100,
        verbose_name='引擎名称',
    )
    sample_count = models.IntegerField(
        verbose_name='样本数量',
    )
    avg_duration_ms = models.FloatField(
        verbose_name='平均耗时(ms)',
    )
    accuracy = models.FloatField(
        verbose_name='准确率',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
    )

    class Meta:
        db_table = 'resources_recognizerbenchmark'
        ordering = ['-created_at']
        verbose_name = '识别器基准测试'
        verbose_name_plural = '识别器基准测试'

    def __str__(self):
        return f'{self.recognizer_type}/{self.engine_name} (准确率: {self.accuracy})'


class TemplateEffectiveness(models.Model):
    """模板有效性模型，记录模板在实际使用中的成功率和有效性统计。

    R37-P3 Stage 7 Task 20a: migrated from tasks app. Belongs in resources
    because it is per-template metadata keyed on resources.Template — keeping
    it here avoids a tasks→resources cross-app FK and lets the resources app
    own the full template lifecycle (definition, versions, annotations,
    effectiveness). db_table kept as 'tasks_templateeffectiveness' for zero
    data migration.
    """

    template = models.ForeignKey(
        Template,
        on_delete=models.CASCADE,
        related_name='effectiveness_records',
        verbose_name='关联模板',
        help_text='关联的模板记录',
    )
    template_name = models.CharField(
        max_length=255,
        default='',
        verbose_name='模板名称',
        help_text='模板的显示名称',
    )
    total_attempts = models.IntegerField(
        default=0,
        verbose_name='总尝试次数',
        help_text='模板累计匹配尝试次数',
    )
    success_count = models.IntegerField(
        default=0,
        verbose_name='成功次数',
        help_text='模板匹配成功次数',
    )
    fail_count = models.IntegerField(
        default=0,
        verbose_name='失败次数',
        help_text='模板匹配失败次数',
    )
    last_success_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='最后成功时间',
        help_text='模板最近一次匹配成功的时间',
    )
    last_match_time = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='最后匹配时间',
        help_text='模板最近一次被使用的时间',
    )
    avg_confidence = models.FloatField(
        default=0,
        verbose_name='平均置信度',
        help_text='模板匹配的平均置信度',
    )
    consecutive_failures = models.IntegerField(
        default=0,
        verbose_name='连续失败次数',
        help_text='模板连续匹配失败次数',
    )
    is_suspected_invalid = models.BooleanField(
        default=False,
        verbose_name='疑似无效',
        help_text='标记模板是否疑似失效',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
        help_text='记录创建的时间戳',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='更新时间',
        help_text='记录最近一次更新的时间戳',
    )

    class Meta:
        db_table = 'tasks_templateeffectiveness'
        verbose_name = '模板有效性'
        verbose_name_plural = '模板有效性'

    @property
    def success_rate(self):
        if self.total_attempts == 0:
            return 0
        return round(self.success_count / self.total_attempts * 100, 1)

    @property
    def is_degraded(self):
        return self.total_attempts >= 10 and self.success_rate < 50

    def __str__(self):
        return f'{self.template.name} (成功率: {self.success_count}/{self.total_attempts})'
