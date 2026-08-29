from django.contrib import admin

from .models import GameProfile, GameStateRule, GameStateSnapshot, GameVersionCheck


@admin.register(GameProfile)
class GameProfileAdmin(admin.ModelAdmin):
    """游戏档案管理后台配置（R37-P3 Stage 7: 从 tasks 迁入）。"""

    list_display = ('id', 'game_name', 'ocr_language', 'resolution_strategy', 'device_type_hint', 'allowed_device_types', 'updated_at')
    list_filter = ('ocr_language', 'resolution_strategy', 'device_type_hint')
    search_fields = ('game_name',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(GameStateRule)
class GameStateRuleAdmin(admin.ModelAdmin):
    """游戏状态规则管理后台配置。"""

    list_display = ('id', 'name', 'game_profile', 'tracker_type', 'is_active')
    list_filter = ('game_profile', 'tracker_type', 'is_active')
    search_fields = ('name', 'game_profile__game_name')


@admin.register(GameStateSnapshot)
class GameStateSnapshotAdmin(admin.ModelAdmin):
    """游戏状态快照管理后台配置。"""

    list_display = ('id', 'rule', 'value', 'triggered', 'created_at')
    list_filter = ('triggered',)
    search_fields = ('rule__name', 'raw_text')
    readonly_fields = ('created_at',)


@admin.register(GameVersionCheck)
class GameVersionCheckAdmin(admin.ModelAdmin):
    """游戏版本更新检测管理后台配置。"""

    list_display = ('id', 'game_profile', 'resource_pack', 'detected_at')
    list_filter = ('game_profile',)
    search_fields = ('game_profile__game_name',)
    readonly_fields = ('detected_at',)
    filter_horizontal = ('affected_templates',)
