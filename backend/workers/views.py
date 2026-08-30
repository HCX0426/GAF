"""
Agent 和设备管理视图 — re-export 兼容层 (s34 拆分).

拆分前: 单文件 3983 行; 拆分后: view_sets/ 包 8 个模块.
引用方 (workers/urls.py, monitors/views.py, worker_runtime.py)
继续从 agents.views 导入, 此层转发到具体模块.
"""
from workers.view_sets.app_info import DeviceAppView, DeviceInfoView
from workers.view_sets.capability import (
    DeviceCompatibilityCheckView,
    EmulatorLifecycleView,
    PlatformCapabilitiesView,
)
from workers.view_sets.capture import (
    DeviceScreenshotView,
    DeviceTestScreenshotView,
    _capture_device_screenshot,
)
from workers.view_sets.crud import DeviceGroupViewSet, DeviceViewSet, WorkerViewSet
from workers.view_sets.input import DeviceClickView, DeviceInputView
from workers.view_sets.lock_stats import DeviceLockView, DeviceStatsView, DeviceUnlockView
from workers.view_sets.recognition import DeviceColorDetectView, DeviceTemplateMatchView
from workers.view_sets.scan_register import DeviceRegisterView, DeviceScanView

__all__ = [
    "WorkerViewSet",
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
