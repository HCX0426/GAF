from rest_framework import serializers

from skills.models import SkillDefinition, SkillMarketItem, SkillMarketReview


class SkillDefinitionSerializer(serializers.ModelSerializer):
    """Skill 定义序列化器，包含全部字段。"""

    class Meta:
        model = SkillDefinition
        fields = [
            'id', 'name', 'description', 'yaml_content', 'version',
            'applicable_scenarios', 'is_builtin', 'is_enabled',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'is_builtin', 'created_at', 'updated_at']


class SkillMarketItemSerializer(serializers.ModelSerializer):
    """Skill 市场条目序列化器（列表/详情）。"""

    publisher_name = serializers.CharField(source='publisher.username', read_only=True)
    skill_name = serializers.CharField(source='skill.name', read_only=True)
    skill_description = serializers.CharField(source='skill.description', read_only=True)
    skill_yaml_content = serializers.CharField(source='skill.yaml_content', read_only=True)
    skill_version = serializers.CharField(source='skill.version', read_only=True)
    skill_applicable_scenarios = serializers.JSONField(
        source='skill.applicable_scenarios', read_only=True
    )

    class Meta:
        model = SkillMarketItem
        fields = [
            'id', 'skill', 'skill_name', 'skill_description',
            'skill_yaml_content', 'skill_version', 'skill_applicable_scenarios',
            'publisher', 'publisher_name', 'title', 'description', 'tags',
            'status', 'download_count', 'rating_avg', 'rating_count',
            'version', 'published_at', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'publisher', 'status', 'download_count',
            'rating_avg', 'rating_count', 'published_at',
            'created_at', 'updated_at',
        ]


class SkillMarketItemCreateSerializer(serializers.ModelSerializer):
    """Skill 市场条目发布序列化器（创建时使用）。"""

    class Meta:
        model = SkillMarketItem
        fields = ['skill', 'title', 'description', 'tags', 'version']
        extra_kwargs = {
            'version': {'default': '1.0'},
            'tags': {'default': list},
            'description': {'default': ''},
        }


class SkillMarketReviewSerializer(serializers.ModelSerializer):
    """Skill 市场评论序列化器。"""

    user_name = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = SkillMarketReview
        fields = ['id', 'item', 'user', 'user_name', 'rating', 'comment', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']
