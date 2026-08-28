from django.conf import settings
from django.db import models


class SkillDefinition(models.Model):
    """LLM Skill 定义模型，描述可被调用的 LLM 技能及其配置。"""

    name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name='技能名称',
    )
    description = models.TextField(
        blank=True,
        verbose_name='描述',
    )
    yaml_content = models.TextField(
        verbose_name='YAML 配置内容',
    )
    version = models.CharField(
        max_length=50,
        verbose_name='版本号',
    )
    applicable_scenarios = models.JSONField(
        default=list,
        verbose_name='适用场景',
    )
    is_builtin = models.BooleanField(
        default=False,
        verbose_name='是否内置',
    )
    is_enabled = models.BooleanField(
        default=True,
        verbose_name='是否启用',
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
        db_table = 'skills_skilldefinition'
        ordering = ['-id']
        verbose_name = 'Skill 定义'
        verbose_name_plural = 'Skill 定义'

    def __str__(self):
        return f'{self.name} v{self.version}'


class SkillMarketItem(models.Model):
    """Skill 市场条目 — 社区分享的 Skill。

    一个 SkillDefinition 可发布到市场成为 SkillMarketItem，
    支持浏览/导入/评分/发布流程。
    """

    class StatusChoices(models.TextChoices):
        PENDING = 'pending', '待审核'
        APPROVED = 'approved', '已批准'
        REJECTED = 'rejected', '已拒绝'
        REMOVED = 'removed', '已下架'

    skill = models.OneToOneField(
        SkillDefinition,
        on_delete=models.CASCADE,
        related_name='market_item',
        verbose_name='关联 Skill',
    )
    publisher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='published_skills',
        verbose_name='发布者',
    )
    title = models.CharField(max_length=255, verbose_name='标题')
    description = models.TextField(blank=True, verbose_name='描述')
    tags = models.JSONField(default=list, verbose_name='标签')
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING,
        verbose_name='审核状态',
    )
    download_count = models.IntegerField(default=0, verbose_name='下载次数')
    rating_avg = models.FloatField(default=0.0, verbose_name='平均评分')
    rating_count = models.IntegerField(default=0, verbose_name='评分数量')
    version = models.CharField(max_length=50, default='1.0', verbose_name='版本号')
    published_at = models.DateTimeField(null=True, blank=True, verbose_name='发布时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'skills_marketitem'
        ordering = ['-created_at']
        verbose_name = 'Skill 市场条目'
        verbose_name_plural = 'Skill 市场条目'

    def __str__(self):
        return f'{self.title} (v{self.version})'


class SkillMarketReview(models.Model):
    """Skill 市场评分评论。"""

    item = models.ForeignKey(
        SkillMarketItem,
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name='市场条目',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='skill_reviews',
        verbose_name='评论者',
    )
    rating = models.IntegerField(verbose_name='评分')
    comment = models.TextField(blank=True, verbose_name='评论内容')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'skills_marketreview'
        unique_together = [('item', 'user')]
        ordering = ['-created_at']
        verbose_name = 'Skill 市场评论'
        verbose_name_plural = 'Skill 市场评论'

    def __str__(self):
        return f'{self.user} → {self.item} ({self.rating}★)'
