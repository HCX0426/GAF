from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from gamestate.serializers import GameProfileSerializer
from resources.models import ResourcePack, Tag, TemplateAnnotation, TemplateEffectiveness, TemplateVersion


class ResourcePackSerializer(serializers.ModelSerializer):
    """资源包序列化器，包含全部字段及关联计数。"""

    task_count = serializers.SerializerMethodField()
    template_count = serializers.SerializerMethodField()
    # R37-P1: nested GameProfile summary so the frontend can render the game
    # name Tag without a second round-trip to /api/v2/tasks/game-profiles/.
    game_profile_detail = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ResourcePack
        fields = [
            'id', 'name', 'version', 'target_app', 'author',
            'directory_path', 'is_active', 'gaf_version_compat',
            'description', 'config_data', 'game_profile', 'game_profile_detail',
            'created_at', 'updated_at',
            'task_count', 'template_count',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    @extend_schema_field(OpenApiTypes.INT)
    def get_task_count(self, obj):
        """Return the number of tasks in this resource pack.

        The source of truth is the `tasks/*.json` files in the resource
        pack directory — one JSON file = one task. Falls back to `pipelines/`
        (legacy) if `tasks/` doesn't exist, then to CustomTask + ScheduledTask
        count when neither directory is available.
        """
        from pathlib import Path

        if not obj.directory_path:
            return obj.custom_tasks.count() + obj.scheduled_tasks.count()

        pack_dir = Path(obj.directory_path)

        # Prefer tasks/ (current), fall back to pipelines/ (legacy)
        for subdir in ("tasks", "pipelines"):
            d = pack_dir / subdir
            if d.is_dir():
                count = 0
                for f in d.iterdir():
                    if f.is_file() and f.suffix.lower() == ".json":
                        count += 1
                return count

        return obj.custom_tasks.count() + obj.scheduled_tasks.count()

    @extend_schema_field(OpenApiTypes.INT)
    def get_template_count(self, obj):
        """Return the number of templates in this resource pack."""
        return obj.templates.count()

    @extend_schema_field(GameProfileSerializer)
    def get_game_profile_detail(self, obj):
        """Return nested GameProfile summary for frontend Tag rendering.

        R37-P3 Stage 7: GameProfileSerializer migrated to gamestate.serializers.

        spec-29f (TD-266 Phase 2a): top-level import is safe — gamestate
        only depends on gamestate.models (no circular import).
        """
        if not obj.game_profile_id:
            return None
        return GameProfileSerializer(obj.game_profile).data


class TemplateAnnotationSerializer(serializers.ModelSerializer):
    """模板标注序列化器，存储模板图片的区域标注数据。

    R37-P1: enables persistence for TemplateAnnotationPage Tab 2 (template
    annotation). Annotation CRUD is exposed via /api/v2/resources/annotations/.
    """

    class Meta:
        model = TemplateAnnotation
        fields = [
            'id', 'template', 'annotation_type', 'points', 'label', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class TagSerializer(serializers.ModelSerializer):
    """Serializer for Tag model with template count."""

    template_count = serializers.SerializerMethodField()

    class Meta:
        model = Tag
        fields = ['id', 'name', 'color', 'created_at', 'template_count']
        read_only_fields = ['id', 'created_at']

    @extend_schema_field(OpenApiTypes.INT)
    def get_template_count(self, obj):
        """Return the number of templates associated with this tag."""
        return obj.templates.count()


class TemplateVersionSerializer(serializers.ModelSerializer):
    """Serializer for TemplateVersion model."""

    class Meta:
        model = TemplateVersion
        fields = [
            'id', 'template', 'version_number', 'snapshot_data',
            'comment', 'created_by', 'created_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at']


class TemplateEffectivenessSerializer(serializers.ModelSerializer):
    """模板有效性序列化器，补充前端展示所需派生字段。

    R37-P3 Stage 7 Task 20a: migrated from tasks app. Exposes the same
    derived fields (failure_count, degraded, match_history) so the frontend
    contract is unchanged.
    """

    failure_count = serializers.IntegerField(source='fail_count', read_only=True)
    degraded = serializers.BooleanField(source='is_degraded', read_only=True)
    # Explicit field declaration so drf-spectacular infers the type from the
    # FloatField instead of falling back to the untyped model property
    # (model property alone yields a "field type cannot be inferred" warning).
    success_rate = serializers.FloatField(read_only=True)
    match_history = serializers.SerializerMethodField()

    class Meta:
        model = TemplateEffectiveness
        fields = [
            'id', 'template', 'template_name', 'total_attempts', 'success_count',
            'failure_count', 'success_rate', 'avg_confidence', 'degraded',
            'last_match_time', 'last_success_at', 'is_suspected_invalid',
            'match_history', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'success_rate', 'failure_count', 'degraded',
            'created_at', 'updated_at',
        ]

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_match_history(self, obj: TemplateEffectiveness):
        """Return empty match history; populated by execution integration in future."""
        return []


# ---------------------------------------------------------------------------
# R37-P2 C3 — ROI CRUD serializers (file-based storage, no DB model)
# ---------------------------------------------------------------------------


class RoiSerializer(serializers.Serializer):
    """Single ROI entry: name + 4-element coords [x, y, w, h].

    Used for POST (create single ROI) and as the building block of
    RoiTaskSerializer. Coords are validated to be a list of 4 integers
    >= 0 (BD2 base resolution is 1920x1080).
    """

    name = serializers.CharField(max_length=255)
    coords = serializers.ListField(
        child=serializers.IntegerField(min_value=0),
        min_length=4,
        max_length=4,
        help_text='ROI coordinates [x, y, w, h] at base resolution',
    )


class RoiTaskSerializer(serializers.Serializer):
    """All ROIs for a single task (or the public group).

    Used for GET/PUT on /resource-packs/{pk}/rois/{task_name}/.
    `task_name` is 'public' or a task name like 'login', 'get_email', ...
    `rois` is a map of {roi_name: [x, y, w, h]}.
    """

    task_name = serializers.CharField(max_length=255)
    rois = serializers.DictField(
        child=serializers.ListField(
            child=serializers.IntegerField(min_value=0),
            min_length=4,
            max_length=4,
        ),
        help_text='Map of roi_name -> [x, y, w, h]',
    )


class RoiFullSerializer(serializers.Serializer):
    """Full rois.json structure: {public: {...}, tasks: {task_name: {...}}}.

    Used for GET/PUT on /resource-packs/{pk}/rois/.
    """

    public = serializers.DictField(
        child=serializers.ListField(
            child=serializers.IntegerField(min_value=0),
            min_length=4,
            max_length=4,
        ),
        required=False,
    )
    tasks = serializers.DictField(
        child=serializers.DictField(
            child=serializers.ListField(
                child=serializers.IntegerField(min_value=0),
                min_length=4,
                max_length=4,
            ),
        ),
        required=False,
    )
