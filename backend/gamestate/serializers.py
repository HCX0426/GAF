"""游戏状态追踪序列化器。"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from gamestate.models import (
    GameProfile,
    GameStateRule,
    GameStateSnapshot,
)


class GameProfileSerializer(serializers.ModelSerializer):
    """游戏档案序列化器（R37-P3 Stage 7: 从 tasks 迁入）。

    spec-29f (TD-266 Phase 3b): explicit ListField / DictField overrides
    for the 3 JSONField columns so DRF Spectacular emits precise types
    (`string[]` / `{ [key: string]: number }`) instead of `unknown`.
    """

    screenshot_methods = serializers.ListField(
        child=serializers.CharField(),
        read_only=False,
        default=list,
    )
    ui_reference_resolution = serializers.DictField(
        child=serializers.IntegerField(),
        read_only=False,
        default=dict,
    )
    known_popups = serializers.ListField(
        child=serializers.CharField(),
        read_only=False,
        default=list,
    )
    allowed_device_types = serializers.ListField(
        child=serializers.CharField(),
        read_only=False,
        default=list,
        required=False,
    )

    class Meta:
        model = GameProfile
        fields = [
            'id', 'game_name', 'screenshot_methods', 'ocr_language',
            'ui_reference_resolution', 'known_popups', 'resolution_strategy',
            'default_routine', 'routine_path', 'default_screenshot_method',
            'default_input_method', 'default_control_mode',
            'device_type_hint', 'allowed_device_types',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class GameStateRuleSerializer(serializers.ModelSerializer):
    """游戏状态规则序列化器。"""

    # spec 2026-08-29-game-account-game-name-retirement P5: 游戏维度唯一权威 =
    # GameProfile; 输出 game_profile FK + 展示名, game_name 字符串已删除.
    game_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = GameStateRule
        fields = [
            'id', 'name', 'game_profile', 'game_name', 'tracker_type',
            'ocr_region', 'ocr_regex', 'threshold', 'threshold_direction',
            'trigger_action', 'is_active',
        ]
        read_only_fields = ['id']

    @extend_schema_field(OpenApiTypes.STR)
    def get_game_name(self, obj):
        return obj.game_profile.game_name


class GameStateSnapshotSerializer(serializers.ModelSerializer):
    """游戏状态快照序列化器。"""

    class Meta:
        model = GameStateSnapshot
        fields = ['id', 'rule', 'value', 'raw_text', 'triggered', 'created_at']
