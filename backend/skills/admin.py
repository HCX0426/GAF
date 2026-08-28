from django.contrib import admin

from .models import SkillDefinition, SkillMarketItem, SkillMarketReview


@admin.register(SkillDefinition)
class SkillDefinitionAdmin(admin.ModelAdmin):
    """Skill 定义管理后台配置。"""

    list_display = ('id', 'name', 'version', 'is_builtin', 'created_at')
    list_filter = ('is_builtin',)
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(SkillMarketItem)
class SkillMarketItemAdmin(admin.ModelAdmin):
    """Skill 市场条目管理后台配置。"""

    list_display = ('id', 'title', 'publisher', 'status', 'download_count', 'rating_avg', 'created_at')
    list_filter = ('status',)
    search_fields = ('title', 'description', 'skill__name')
    readonly_fields = ('download_count', 'rating_avg', 'rating_count', 'published_at', 'created_at', 'updated_at')


@admin.register(SkillMarketReview)
class SkillMarketReviewAdmin(admin.ModelAdmin):
    """Skill 市场评论管理后台配置。"""

    list_display = ('id', 'item', 'user', 'rating', 'created_at')
    list_filter = ('rating',)
    search_fields = ('comment',)
    readonly_fields = ('created_at',)
