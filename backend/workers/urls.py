from django.urls import include, path
from rest_framework.routers import DefaultRouter

from workers.views import (
    DeviceAppView,
    DeviceClickView,
    DeviceColorDetectView,
    DeviceCompatibilityCheckView,
    DeviceGroupViewSet,
    DeviceInfoView,
    DeviceInputView,
    DeviceLockView,
    DeviceRegisterView,
    DeviceScanView,
    DeviceScreenshotView,
    DeviceStatsView,
    DeviceTemplateMatchView,
    DeviceTestScreenshotView,
    DeviceUnlockView,
    DeviceViewSet,
    EmulatorLifecycleView,
    PlatformCapabilitiesView,
    WorkerViewSet,
)

router = DefaultRouter()
router.register(r'agents', WorkerViewSet, basename='agent')
router.register(r'devices', DeviceViewSet, basename='device')

urlpatterns = [
    path(
        'device-groups/',
        DeviceGroupViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='devicegroup-list',
    ),
    path(
        'device-groups/<int:pk>/',
        DeviceGroupViewSet.as_view({
            'get': 'retrieve',
            'put': 'update',
            'patch': 'partial_update',
            'delete': 'destroy',
        }),
        name='devicegroup-detail',
    ),
    path(
        'devices/scan/',
        DeviceScanView.as_view(),
        name='device-scan',
    ),
    path(
        'devices/register/',
        DeviceRegisterView.as_view(),
        name='device-register',
    ),
    path(
        'devices/check-compatibility/',
        DeviceCompatibilityCheckView.as_view(),
        name='device-compatibility-check',
    ),
    path(
        'devices/platform-capabilities/',
        PlatformCapabilitiesView.as_view(),
        name='platform-capabilities',
    ),
    path(
        'devices/<int:id>/screenshot/',
        DeviceScreenshotView.as_view(),
        name='device-screenshot',
    ),
    path(
        'devices/<int:id>/test-screenshot/',
        DeviceTestScreenshotView.as_view(),
        name='device-test-screenshot',
    ),
    path(
        'devices/<int:id>/lock/',
        DeviceLockView.as_view(),
        name='device-lock',
    ),
    path(
        'devices/<int:id>/unlock/',
        DeviceUnlockView.as_view(),
        name='device-unlock',
    ),
    path(
        'devices/<int:id>/stats/',
        DeviceStatsView.as_view(),
        name='device-stats',
    ),
    path(
        'devices/<int:id>/click/',
        DeviceClickView.as_view(),
        name='device-click',
    ),
    path(
        'devices/<int:id>/input/',
        DeviceInputView.as_view(),
        name='device-input',
    ),
    path(
        'devices/<int:id>/template-match/',
        DeviceTemplateMatchView.as_view(),
        name='device-template-match',
    ),
    path(
        'devices/<int:id>/color-detect/',
        DeviceColorDetectView.as_view(),
        name='device-color-detect',
    ),
    path(
        'devices/emulator-lifecycle/',
        EmulatorLifecycleView.as_view(),
        name='emulator-lifecycle',
    ),
    path(
        'devices/<int:id>/app/',
        DeviceAppView.as_view(),
        name='device-app',
    ),
    path(
        'devices/<int:id>/info/',
        DeviceInfoView.as_view(),
        name='device-info',
    ),
    path('', include(router.urls)),
]
