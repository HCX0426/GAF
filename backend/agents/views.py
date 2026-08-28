"""
Agent 和设备管理视图 — re-export 兼容层 (s34 拆分).

拆分前: 单文件 3983 行; 拆分后: view_sets/ 包 8 个模块.
引用方 (agents/urls.py, monitors/views.py, agent_runtime.py)
继续从 agents.views 导入, 此层转发到具体模块.
"""
from agents.view_sets.app_info import DeviceAppView, DeviceInfoView
from agents.view_sets.capability import (
    DeviceCompatibilityCheckView,
    EmulatorLifecycleView,
    PlatformCapabilitiesView,
)
from agents.view_sets.capture import (
    DeviceScreenshotView,
    DeviceTestScreenshotView,
    _capture_device_screenshot,
)
from agents.view_sets.crud import AgentViewSet, DeviceGroupViewSet, DeviceViewSet
from agents.view_sets.input import DeviceClickView, DeviceInputView
from agents.view_sets.lock_stats import DeviceLockView, DeviceStatsView, DeviceUnlockView
from agents.view_sets.recognition import DeviceColorDetectView, DeviceTemplateMatchView
from agents.view_sets.scan_register import DeviceRegisterView, DeviceScanView

__all__ = [
    "AgentViewSet",
    "DeviceViewSet",
    "DeviceGroupViewSet",
    "DeviceScanView",
    "DeviceRegisterView",
    "DeviceScreenshotView",
    "DeviceTestScreenshotView",
    "_capture_device_screenshot",
    "DeviceLockView",
    "DeviceUnlockView",
    "DeviceStatsView",
    "DeviceCompatibilityCheckView",
    "PlatformCapabilitiesView",
    "EmulatorLifecycleView",
    "DeviceClickView",
    "DeviceInputView",
    "DeviceTemplateMatchView",
    "DeviceColorDetectView",
    "DeviceAppView",
    "DeviceInfoView",
]
