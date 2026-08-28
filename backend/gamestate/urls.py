from django.urls import include, path
from rest_framework.routers import DefaultRouter

from gamestate.views import (
    GameProfileViewSet,
    GameStateRuleViewSet,
    GameStateSnapshotViewSet,
)

router = DefaultRouter()
# Router prefixes are appended to the include prefix (config/urls.py mounts
# this app at /api/v2/gamestate/), so the final URLs become:
#   /api/v2/gamestate/game-profiles/
#   /api/v2/gamestate/rules/
#   /api/v2/gamestate/snapshots/
# Do NOT add a redundant `gamestate/` prefix here — that would create
# double prefixes like /api/v2/gamestate/gamestate/game-profiles/ (TD-100).
router.register(r'game-profiles', GameProfileViewSet, basename='game-profile')
router.register(r'rules', GameStateRuleViewSet, basename='gamestate-rule')
router.register(r'snapshots', GameStateSnapshotViewSet, basename='gamestate-snapshot')

urlpatterns = [
    path('', include(router.urls)),
]
