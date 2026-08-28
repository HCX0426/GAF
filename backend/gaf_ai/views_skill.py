"""Views for AI custom skills (skill editor)."""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import RoleBasedPermission

from .models import CustomSkill
from .serializers import CustomSkillSerializer


class CustomSkillViewSet(viewsets.ModelViewSet):
    """ViewSet for user-defined YAML skills.

    - GET    /api/ai/custom-skills/          list current user's skills
    - POST   /api/ai/custom-skills/          create skill
    - GET    /api/ai/custom-skills/<id>/     retrieve skill
    - PUT    /api/ai/custom-skills/<id>/     update skill
    - DELETE /api/ai/custom-skills/<id>/     delete skill
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'execute'
    serializer_class = CustomSkillSerializer
    filterset_fields = ['category', 'is_active']
    search_fields = ['name', 'description']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return CustomSkill.objects.none()
        return CustomSkill.objects.filter(created_by=self.request.user)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def update(self, request, *args, **kwargs):
        """Allow partial updates by default (frontend only sends changed fields)."""
        partial = kwargs.pop('partial', True)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)
