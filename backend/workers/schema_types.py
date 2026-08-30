"""DRF Spectacular inline schema definitions for agents app.

spec-29f (TD-266 Phase 1): Device serializer has 6 SerializerMethodField
fields whose return types DRF Spectacular regresses to `string` because it
cannot infer structure from a method's return value. The inline serializers
below give Spectacular explicit field definitions so the generated OpenAPI
schema matches the actual JSON response shape.

Kept in a dedicated module so `workers/serializers.py` stays focused on
serialization logic. Importing this module has no side effects (no model
imports) so it is safe to load at module-init time without risking circular
imports.
"""

from rest_framework import serializers


class WorkerInfoSchema(serializers.Serializer):
    """Schema for `DeviceSerializer.get_agent_info` return value.

    Mirrors the dict returned by `DeviceSerializer.get_agent_info` (a
    6-field summary of the related Worker). `ip_address` and
    `last_heartbeat` are nullable on the Worker model.
    """

    id = serializers.IntegerField(read_only=True)
    agent_id = serializers.CharField(read_only=True)
    hostname = serializers.CharField(read_only=True)
    ip_address = serializers.CharField(read_only=True, allow_null=True)
    status = serializers.CharField(read_only=True)
    last_heartbeat = serializers.DateTimeField(read_only=True, allow_null=True)


class ResolutionSchema(serializers.Serializer):
    """Schema for `DeviceSerializer.get_resolution` return value.

    Two-integer dict (`{width, height}`) or `None` when the device has no
    resolution recorded.
    """

    width = serializers.IntegerField(read_only=True)
    height = serializers.IntegerField(read_only=True)


class ResolvedDeviceMethodsSchema(serializers.Serializer):
    """Schema for `DeviceSerializer.get_resolved_methods` return value.

    Mirrors the dict returned by `agents.models.resolve_device_methods`:
    resolved screenshot/input/control_mode after GameProfile inheritance,
    plus `multi_game_restricted` flag and `original_*` diagnostics keys
    for P-011 multi-game parallel mode.
    """

    screenshot_method = serializers.CharField(read_only=True)
    input_method = serializers.CharField(read_only=True)
    control_mode = serializers.CharField(read_only=True)
    multi_game_restricted = serializers.BooleanField(read_only=True)
    original_screenshot_method = serializers.CharField(read_only=True)
    original_input_method = serializers.CharField(read_only=True)


class DeviceStatsSchema(serializers.Serializer):
    """Schema for `DeviceSerializer.device_stats` return value.

    spec-29k (TD-259 #7 Phase 2d): `device_stats` is a `JSONField` whose
    value is a dynamic dict written by `Device.update_screenshot_stats`
    (screenshot_latency_avg_ms / screenshot_fps / screenshot_method /
    total_screenshots) and `DevicePerformanceStatsView` (fps_avg / fps_min
    / fps_max / input_latency_avg_ms / uptime_seconds / dpi). DRF
    Spectacular regresses `DictField` to `{ [key: string]: unknown }`,
    breaking frontend consumers that access typed numeric fields like
    `device.device_stats?.screenshot_latency_avg_ms.toFixed(0)`.

    Explicit field declarations here let Spectacular emit a precise
    schema so the frontend `Device` type can migrate to
    `API.components['schemas']['Device']`. All fields are optional
    because the dict is populated incrementally — a fresh device may
    have only a subset populated.
    """

    fps_avg = serializers.FloatField(read_only=True, allow_null=True)
    fps_min = serializers.FloatField(read_only=True, allow_null=True)
    fps_max = serializers.FloatField(read_only=True, allow_null=True)
    screenshot_latency_avg_ms = serializers.FloatField(read_only=True, allow_null=True)
    input_latency_avg_ms = serializers.FloatField(read_only=True, allow_null=True)
    uptime_seconds = serializers.FloatField(read_only=True, allow_null=True)
    total_screenshots = serializers.IntegerField(read_only=True)
    screenshot_method = serializers.CharField(read_only=True, allow_null=True)
    screenshot_fps = serializers.FloatField(read_only=True, allow_null=True)
    dpi = serializers.IntegerField(read_only=True, allow_null=True)
