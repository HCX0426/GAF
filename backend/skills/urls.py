from django.urls import include, path
from rest_framework.routers import DefaultRouter

from skills.views import SkillDefinitionViewSet, SkillMarketViewSet

router = DefaultRouter()
router.register(r'skills', SkillDefinitionViewSet, basename='skill')
router.register(r'market', SkillMarketViewSet, basename='skill-market')

urlpatterns = [
    path('', include(router.urls)),
]
