"""i18n API views — language listing and catalog endpoint (P-033 Phase 4)."""
from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class LanguageListView(APIView):
    """GET /api/v2/i18n/languages/ — list available backend languages."""

    permission_classes = [AllowAny]

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT},
        description="List available backend languages with current/default code.",
    )
    def get(self, request):
        languages = [
            {"code": code, "name": name}
            for code, name in settings.LANGUAGES
        ]
        return Response({
            "languages": languages,
            "current": translation.get_language(),
            "default": settings.LANGUAGE_CODE,
        })


class MessageCatalogView(APIView):
    """GET /api/v2/i18n/catalog/<lang>/ — get backend message catalog."""

    permission_classes = [AllowAny]

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
        description="Return a flat dict of {msgid: msgstr} for the requested language.",
    )
    def get(self, request, lang):
        available_codes = {code for code, _ in settings.LANGUAGES}
        if lang not in available_codes:
            return Response(
                {"detail": _("Unsupported language code: {}").format(lang)},
                status=400,
            )

        with translation.override(lang):
            catalog = {
                "password_changed_successfully": str(_("密码修改成功")),
                "2fa_enabled": str(_("2FA 已启用")),
                "2fa_disabled": str(_("2FA 已禁用")),
                "reset_link_sent": str(_("重置链接已发送到您的邮箱")),
                "password_reset_success": str(_("密码重置成功")),
                "session_terminated": str(_("会话已下线")),
                "system_already_initialized": str(_("系统已存在用户，不能重复初始化")),
                "username_too_short": str(_("用户名至少 3 个字符")),
                "password_too_short": str(_("密码至少 8 个字符")),
                "login_history_forbidden": str(_("仅管理员可查看所有用户登录历史")),
                "unsupported_language": str(_("Unsupported language code: {}")),
            }
        return Response({"language": lang, "catalog": catalog})
