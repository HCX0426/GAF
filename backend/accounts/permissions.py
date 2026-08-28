from rest_framework.permissions import BasePermission


class RoleBasedPermission(BasePermission):
    """基于角色的权限控制类，根据用户角色判断是否具有所需权限。"""

    ROLE_PERMISSIONS = {
        'viewer': ['view'],
        'operator': ['view', 'execute', 'debug', 'llm_use'],
        'admin': ['view', 'execute', 'debug', 'llm_use', 'manage'],
    }

    def has_permission(self, request, view):
        """检查当前用户是否具有所需权限。"""
        user = request.user
        if not user.is_authenticated:
            return False
        required = getattr(view, 'required_permission', 'view')
        allowed = self.ROLE_PERMISSIONS.get(user.role, [])
        return required in allowed


class InitOrAuthenticatedPermission(BasePermission):
    """Allow unrestricted access during first-run setup (no users exist yet),
    but require authenticated access with role-based permissions afterward.

    C11/C12 fix: init wizard endpoints (health, env-check, device scan, import)
    must be accessible before the first admin account is created, but should
    be protected once setup is complete to prevent info leaks and unauthenticated
    writes.
    """

    def has_permission(self, request, view):
        from accounts.models import User

        # First-run: no users exist yet → allow anyone (init wizard)
        if not User.objects.exists():
            return True

        # Post-setup: require authentication + role-based permission
        user = request.user
        if not user.is_authenticated:
            return False
        required = getattr(view, 'required_permission', 'view')
        allowed = RoleBasedPermission.ROLE_PERMISSIONS.get(user.role, [])
        return required in allowed


def require_permission(permission):
    """Decorator that sets ``required_permission`` on a function-based view.

    Use together with ``@permission_classes([IsAuthenticated, RoleBasedPermission])``
    so RoleBasedPermission can read the required permission off the function object.
    """

    def decorator(func):
        func.required_permission = permission
        return func

    return decorator

