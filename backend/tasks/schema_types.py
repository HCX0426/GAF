"""DRF Spectacular inline schema definitions for tasks app.

spec-29f (TD-266 Phase 2a): TaskSerializer has 2 nested-list
SerializerMethodField fields (game_account_details / device_details)
whose return types DRF Spectacular regresses to `string` because it
cannot infer structure from a method's return value. The inline
serializers below give Spectacular explicit field definitions so the
generated OpenAPI schema matches the actual JSON response shape.

Kept in a dedicated module so `tasks/serializers.py` stays focused on
serialization logic. Importing this module has no side effects (no model
imports) so it is safe to load at module-init time without risking
circular imports.
"""

from rest_framework import serializers


class GameAccountDetailSchema(serializers.Serializer):
    """Schema for `TaskSerializer.get_game_account_details` list items."""
    id = serializers.IntegerField(read_only=True)
    game_name = serializers.CharField(read_only=True)
    username = serializers.CharField(read_only=True)


class DeviceDetailSchema(serializers.Serializer):
    """Schema for `TaskSerializer.get_device_details` list items."""
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)


class ResourcePackDetailSchema(serializers.Serializer):
    """Schema for `TaskSerializer.get_resource_pack_detail` return value.

    N197-8: Nested ResourcePack summary so the frontend can render the pack
    name and version without a second round-trip to /resources/resource-packs/.
    """
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    version = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
