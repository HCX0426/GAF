from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import RoleBasedPermission
from skills.engine import extract_keywords, match_skills
from skills.models import SkillDefinition, SkillMarketItem, SkillMarketReview
from skills.serializers import (
    SkillDefinitionSerializer,
    SkillMarketItemCreateSerializer,
    SkillMarketItemSerializer,
    SkillMarketReviewSerializer,
)


class SkillDefinitionViewSet(viewsets.ReadOnlyModelViewSet):
    """Skill 定义视图集，内置 Skill 不可删除，支持自动匹配"""

    queryset = SkillDefinition.objects.all()
    serializer_class = SkillDefinitionSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'view'
    filterset_fields = ['is_builtin', 'version']
    search_fields = ['name', 'description']

    def get_permissions(self):
        # execute triggers LLM calls (costs money) -> require 'execute' perm
        if self.action == 'execute':
            self.required_permission = 'execute'
        else:
            self.required_permission = 'view'
        return super().get_permissions()

    @action(detail=False, methods=['post'], url_path='auto-match')
    def auto_match(self, request):
        """根据关键词和场景自动匹配最合适的 Skill

        请求体:
            keywords: str — 空格分隔的关键词文本
            scene: str (可选) — 场景标识
            limit: int (可选, 默认5) — 返回数量上限
        """
        text = request.data.get('query', '') or request.data.get('keywords', '')
        scene = request.data.get('scene')
        limit = request.data.get('limit', 5)

        keywords = extract_keywords(text)
        if not keywords:
            return Response({'matches': []})

        matches = match_skills(keywords, scene=scene, limit=limit)
        result_matches = []
        for m in matches:
            try:
                skill = SkillDefinition.objects.get(pk=m['skill_id'])
                result_matches.append({
                    'skill': SkillDefinitionSerializer(skill).data,
                    'score': m['score'],
                })
            except SkillDefinition.DoesNotExist:
                continue
        return Response({'matches': result_matches})

    @action(detail=True, methods=['post'], url_path='toggle')
    def toggle(self, request, pk=None):
        """切换 Skill 启用/禁用状态"""
        skill = self.get_object()
        skill.is_enabled = not skill.is_enabled
        skill.save(update_fields=['is_enabled'])
        return Response({'id': skill.id, 'is_enabled': skill.is_enabled})

    @action(detail=False, methods=['post'], url_path='sync-builtin')
    def sync_builtin(self, request):
        """同步内置 Skills 到数据库

        调用 SkillLoader.sync_to_database() 将内置 Skill 定义
        持久化到数据库中，返回同步的记录数量。

        Returns:
            Response: 包含 count 字段，表示同步的记录数量
        """
        from skills.loader import SkillLoader
        count = SkillLoader.sync_to_database()
        return Response({'count': count}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='execute')
    def execute(self, request, pk=None):
        """Execute a SkillDefinition with task context.

        Spec v3 §3.1 — canonical Skill execution path. Parses the
        Skill's YAML schema (system_prompt + user_prompt_template +
        context + parameters + output + cost_control), collects task
        context, checks budget, calls LLM via 4-level router, and
        returns structured result.

        Request body:
            task_context: dict (optional) — execution data containing
                log, screenshots, task_config, device_info, and any
                template variables referenced in user_prompt_template
            parameters: dict (optional) — override YAML parameter
                defaults (e.g. {"temperature": 0.7, "max_tokens": 3000})

        Response:
            {
                "skill_name": str,
                "skill_id": int,
                "model": str,          # actual model used
                "route": str,          # preferred/backup/local/offline
                "content": str,        # raw LLM response
                "parsed_output": dict, # parsed per output.format
                "usage": {
                    "input_tokens": int,
                    "output_tokens": int,
                    "cost": float
                }
            }

        Errors:
            400 — Skill disabled / budget exceeded / invalid YAML / LLM failure
        """
        from skills.executor import SkillExecutionError, execute_skill

        skill = self.get_object()
        if not skill.is_enabled:
            return Response(
                {'error': f"Skill '{skill.name}' is disabled"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        task_context = request.data.get('task_context', {})
        parameters = request.data.get('parameters')

        try:
            result = execute_skill(
                skill=skill,
                task_context=task_context,
                user=request.user,
                parameters=parameters,
            )
        except SkillExecutionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(result, status=status.HTTP_200_OK)


class SkillMarketViewSet(viewsets.ReadOnlyModelViewSet):
    """Skill 市场视图集 — 社区分享 Skill 的浏览/发布/导入/评分。

    Endpoints:
        GET    /skills/market/                  — 浏览已批准的 Skill (list)
        GET    /skills/market/{id}/             — 查看详情 (retrieve)
        POST   /skills/market/publish/          — 发布 Skill 到市场
        POST   /skills/market/{id}/import/      — 导入 Skill 到当前用户
        POST   /skills/market/{id}/review/      — 评分评论
        GET    /skills/market/my-published/     — 我的发布
    """

    serializer_class = SkillMarketItemSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'view'
    filterset_fields = ['status', 'version']
    search_fields = ['title', 'description', 'skill__name']

    def get_queryset(self):
        """列表仅返回已批准条目；my_published 返回当前用户全部条目；
        import/review 允许查询任何状态（视图内自行校验状态）。"""
        qs = SkillMarketItem.objects.select_related('skill', 'publisher')
        if self.action == 'my_published':
            return qs.filter(publisher=self.request.user)
        if self.action in ('retrieve', 'import_item', 'review'):
            return qs  # 详情/导入/评分允许查询任何状态（供发布者预览或视图内校验）
        return qs.filter(status=SkillMarketItem.StatusChoices.APPROVED)

    @action(detail=False, methods=['post'], url_path='publish')
    def publish(self, request):
        """发布 Skill 到市场。

        请求体:
            skill: int — SkillDefinition ID
            title: str — 市场标题
            description: str (可选) — 市场描述
            tags: list (可选) — 标签列表
            version: str (可选, 默认 '1.0') — 市场版本号
        """
        serializer = SkillMarketItemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # PrimaryKeyRelatedField returns the SkillDefinition instance directly.
        skill = serializer.validated_data['skill']

        # 检查是否已发布
        if hasattr(skill, 'market_item'):
            return Response(
                {'detail': '该 Skill 已发布到市场'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            item = SkillMarketItem.objects.create(
                skill=skill,
                publisher=request.user,
                title=serializer.validated_data['title'],
                description=serializer.validated_data.get('description', ''),
                tags=serializer.validated_data.get('tags', []),
                version=serializer.validated_data.get('version', '1.0'),
                status=SkillMarketItem.StatusChoices.PENDING,
                published_at=timezone.now(),
            )

        return Response(
            SkillMarketItemSerializer(item).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'], url_path='import')
    def import_item(self, request, pk=None):
        """导入市场 Skill 到当前用户（复制 SkillDefinition）。

        创建一个新的 SkillDefinition，名称加后缀避免冲突，
        并增加原条目的 download_count。
        """
        item = self.get_object()
        if item.status != SkillMarketItem.StatusChoices.APPROVED:
            return Response(
                {'detail': '该 Skill 未通过审核，无法导入'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        src_skill = item.skill
        new_name = f'{src_skill.name}_imported_{request.user.id}'

        # 名称冲突时追加序号
        base_name = new_name
        counter = 1
        while SkillDefinition.objects.filter(name=new_name).exists():
            new_name = f'{base_name}_{counter}'
            counter += 1

        with transaction.atomic():
            new_skill = SkillDefinition.objects.create(
                name=new_name,
                description=src_skill.description,
                yaml_content=src_skill.yaml_content,
                version=src_skill.version,
                applicable_scenarios=src_skill.applicable_scenarios,
                is_builtin=False,
                is_enabled=True,
            )
            item.download_count = item.download_count + 1
            item.save(update_fields=['download_count'])

        return Response(
            {
                'detail': '导入成功',
                'skill_id': new_skill.id,
                'skill_name': new_skill.name,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'], url_path='review')
    def review(self, request, pk=None):
        """对市场 Skill 评分评论。

        请求体:
            rating: int — 评分 1-5
            comment: str (可选) — 评论内容
        """
        item = self.get_object()
        if item.status != SkillMarketItem.StatusChoices.APPROVED:
            return Response(
                {'detail': '该 Skill 未通过审核，无法评分'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rating = request.data.get('rating')
        if rating is None or not isinstance(rating, int) or not (1 <= rating <= 5):
            return Response(
                {'detail': 'rating 必须为 1-5 的整数'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        comment = request.data.get('comment', '')

        with transaction.atomic():
            review, created = SkillMarketReview.objects.update_or_create(
                item=item,
                user=request.user,
                defaults={'rating': rating, 'comment': comment},
            )
            self._update_item_rating(item)

        serializer = SkillMarketReviewSerializer(review)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='my-published')
    def my_published(self, request):
        """获取当前用户发布的全部 Skill 市场条目（含待审核/拒绝）。"""
        qs = self.get_queryset()
        items = qs.order_by('-created_at')
        page = self.paginate_queryset(items)
        if page is not None:
            serializer = SkillMarketItemSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = SkillMarketItemSerializer(items, many=True)
        return Response(serializer.data)

    @staticmethod
    def _update_item_rating(item: SkillMarketItem) -> None:
        """重新计算条目的 rating_avg 和 rating_count。"""
        reviews = item.reviews.all()
        count = reviews.count()
        if count == 0:
            item.rating_avg = 0.0
            item.rating_count = 0
        else:
            total = sum(r.rating for r in reviews)
            item.rating_avg = round(total / count, 2)
            item.rating_count = count
        item.save(update_fields=['rating_avg', 'rating_count'])
