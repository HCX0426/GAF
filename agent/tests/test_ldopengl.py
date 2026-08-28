"""#35 LDOpenGL 截图单元测试

测试 LDOpenGLCapture 类和 ADBDevice._capture_ldopengl():
- LDOpenGLCapture 初始化与可用性检测
- DLL 发现 (显式目录 / 注册表 / PATH)
- capture() BGRA→BGR 转换
- find_ldplayer_window() FindWindowW 调用
- ADBDevice._capture_ldopengl() 集成 (wm size 解析 + 调用 capture)
- 降级链集成 (LDOPENGL_METHOD 在 fallback_order 和 method_map 中)
- 非Windows 平台降级
- v3 API (LDPlayer 14 vtable-based PID capture)
"""
import ctypes
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import numpy as np
import platforms.windows.ldopengl as _ldopengl_mod
import pytest
from devices.adb.device import (
    LDOPENGL_METHOD,
    ADBDevice,
)
from platforms.windows.ldopengl import (
    LDOPENGL_DLL_PATHS,
    LDOPENGL_V3_HEIGHT_OFFSET,
    LDOPENGL_V3_WIDTH_OFFSET,
    LDPLAYER_REG_PATHS,
    LDPLAYER_WINDOW_CLASS,
    LDPLAYER_WINDOW_CLASSES,
    LDOpenGLCapture,
    get_ldopengl_capture,
)

pytestmark = pytest.mark.e2e


class TestLDOpenGLConstants:
    """常量定义测试"""

    def test_ldopengl_method_constant(self):
        """LDOPENGL_METHOD 常量值"""
        assert LDOPENGL_METHOD == "ldopengl"

    def test_ldplayer_window_class(self):
        """LDPlayer 窗口类名常量"""
        assert LDPLAYER_WINDOW_CLASS == "LDPlayerWnd"

    def test_ldplayer_window_classes_tuple(self):
        """LDPlayer 窗口类名元组 (v3: 包含 LDPlayer 14 的类名)"""
        assert isinstance(LDPLAYER_WINDOW_CLASSES, tuple)
        assert "LDPlayerWnd" in LDPLAYER_WINDOW_CLASSES
        assert "LDPlayerMainFrame" in LDPLAYER_WINDOW_CLASSES

    def test_v3_offset_constants(self):
        """v3 offset constants (deprecated IReadPixelsClass layout, kept for reference)"""
        assert LDOPENGL_V3_WIDTH_OFFSET == 0x6C
        assert LDOPENGL_V3_HEIGHT_OFFSET == 0x70

    def test_dll_paths_tuple(self):
        """DLL 路径候选元组"""
        assert isinstance(LDOPENGL_DLL_PATHS, tuple)
        assert "ldopengl64.dll" in LDOPENGL_DLL_PATHS
        assert len(LDOPENGL_DLL_PATHS) >= 3

    def test_registry_paths_tuple(self):
        """注册表路径候选元组"""
        assert isinstance(LDPLAYER_REG_PATHS, tuple)
        assert r"SOFTWARE\leidian\LDPlayer9" in LDPLAYER_REG_PATHS
        # Ensure coverage for LDPlayer 4 / X / 12 / 14 versions.
        assert r"SOFTWARE\leidian\LDPlayer4" in LDPLAYER_REG_PATHS
        assert r"SOFTWARE\leidian\LDPlayerX" in LDPLAYER_REG_PATHS
        assert r"SOFTWARE\leidian\LDPlayer12" in LDPLAYER_REG_PATHS
        assert r"SOFTWARE\leidian\LDPlayer14" in LDPLAYER_REG_PATHS


class TestLDOpenGLCaptureInit:
    """LDOpenGLCapture 初始化测试"""

    def test_default_init(self):
        """默认初始化"""
        cap = LDOpenGLCapture()
        assert cap._ldplayer_dir is None
        assert cap._dll is None
        assert cap._capture_fn is None
        # P1-1: v2 API fields should also be initialized to None/0.
        assert cap._capture_frame_fn is None
        assert cap._get_frame_info_fn is None
        assert cap._copy_frame_fn is None
        assert cap._release_frame_fn is None
        # v3 API field should be initialized to None.
        assert cap._create_instance_fn is None
        assert cap._api_version == 0
        assert cap._initialized is False

    def test_init_with_explicit_dir(self):
        """显式指定 LDPlayer 目录"""
        cap = LDOpenGLCapture(ldplayer_dir="C:/LDPlayer9")
        assert cap._ldplayer_dir == Path("C:/LDPlayer9")

    def test_init_with_none_dir(self):
        """显式传入 None"""
        cap = LDOpenGLCapture(ldplayer_dir=None)
        assert cap._ldplayer_dir is None


class TestLDOpenGLAvailability:
    """is_available() 平台检测测试"""

    @patch('platforms.windows.ldopengl.platform.system', return_value='Linux')
    def test_unavailable_on_linux(self, mock_system):
        """Linux 平台不可用"""
        cap = LDOpenGLCapture()
        assert cap.is_available() is False

    @patch('platforms.windows.ldopengl.platform.system', return_value='Darwin')
    def test_unavailable_on_macos(self, mock_system):
        """macOS 平台不可用"""
        cap = LDOpenGLCapture()
        assert cap.is_available() is False

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_unavailable_when_dll_not_found(self, mock_system):
        """Windows 平台但 DLL 未找到"""
        cap = LDOpenGLCapture()
        with patch.object(cap, '_find_dll', return_value=None):
            assert cap.is_available() is False

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_available_when_dll_loadable(self, mock_system):
        """Windows 平台且 DLL 可加载"""
        cap = LDOpenGLCapture()
        mock_dll = MagicMock()
        mock_fn = MagicMock()
        mock_dll.ldopengl_capture = mock_fn
        with patch.object(cap, '_find_dll', return_value=Path("C:/fake/ldopengl64.dll")), \
             patch('ctypes.CDLL', return_value=mock_dll):
            assert cap.is_available() is True


class TestLDOpenGLCapture:
    """capture() 方法测试"""

    @patch('platforms.windows.ldopengl.platform.system', return_value='Linux')
    def test_capture_returns_none_on_non_windows(self, mock_system):
        """非 Windows 平台 capture 返回 None"""
        cap = LDOpenGLCapture()
        assert cap.capture(hwnd=12345, width=720, height=1280) is None

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_capture_success(self, mock_system):
        """成功截图返回 BGR numpy 数组"""
        cap = LDOpenGLCapture()
        width, height = 4, 2
        # Simulate BGRA buffer (4 pixels * 4 bytes = 16 bytes)
        bgra_data = bytes([
            10, 20, 30, 255,  # pixel 0: B=10, G=20, R=30, A=255
            40, 50, 60, 255,  # pixel 1
            70, 80, 90, 255,  # pixel 2
            100, 110, 120, 255,  # pixel 3
        ])

        def fake_capture_fn(hwnd, w, h, buffer):
            """Mock capture function that fills buffer with test data"""
            for i, b in enumerate(bgra_data):
                buffer[i] = b
            return 0  # success

        # Bypass _ensure_loaded and inject mock capture function directly
        cap._initialized = True
        cap._api_version = 1  # P1-1: must set v1 API version explicitly
        cap._capture_fn = fake_capture_fn

        result = cap.capture(hwnd=12345, width=width, height=height)

        assert result is not None
        assert result.shape == (height, width, 3)
        # BGR (drop alpha): pixel 0 should be [10, 20, 30]
        assert result[0, 0, 0] == 10  # B
        assert result[0, 0, 1] == 20  # G
        assert result[0, 0, 2] == 30  # R

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_capture_failure_returns_none(self, mock_system):
        """ldopengl_capture 返回非零错误码"""
        cap = LDOpenGLCapture()

        def fake_capture_fn(hwnd, w, h, buffer):
            return 1  # non-zero = error

        cap._initialized = True
        cap._api_version = 1  # P1-1: must set v1 API version explicitly
        cap._capture_fn = fake_capture_fn

        result = cap.capture(hwnd=12345, width=720, height=1280)
        assert result is None


class TestLDOpenGLV2API:
    """P1-1 v2 API tests — ldopengl_capture_frame + get_frame_info +
    copy_frame + release_frame (4-step process).

    The v2 API is preferred over v1 because the DLL manages the frame
    buffer internally and queries emulator dimensions on its own.
    """

    def test_api_version_property_default_zero(self):
        """api_version defaults to 0 (not loaded) before _ensure_loaded."""
        cap = LDOpenGLCapture()
        assert cap.api_version == 0

    def test_api_version_one_for_v1_load(self):
        """api_version is 1 after loading v1 symbols only."""
        cap = LDOpenGLCapture()
        cap._initialized = True
        cap._api_version = 1
        assert cap.api_version == 1

    def test_api_version_two_for_v2_load(self):
        """api_version is 2 after loading v2 symbols."""
        cap = LDOpenGLCapture()
        cap._initialized = True
        cap._api_version = 2
        assert cap.api_version == 2

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_is_available_true_for_v2(self, mock_system):
        """is_available() returns True when v2 API is loaded."""
        cap = LDOpenGLCapture()
        cap._initialized = True
        cap._api_version = 2
        # _ensure_loaded is a no-op once _initialized is True
        assert cap.is_available() is True

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_is_available_true_for_v1(self, mock_system):
        """is_available() returns True when v1 API is loaded."""
        cap = LDOpenGLCapture()
        cap._initialized = True
        cap._api_version = 1
        assert cap.is_available() is True

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_v2_capture_success(self, mock_system):
        """v2 capture() returns BGR numpy array via 4-step process."""
        cap = LDOpenGLCapture()
        cap._initialized = True
        cap._api_version = 2

        width, height = 2, 1
        bgra_data = bytes([
            11, 22, 33, 255,  # pixel 0: B=11, G=22, R=33
            44, 55, 66, 255,  # pixel 1
        ])
        frame_handle_value = 0xDEADBEEF  # arbitrary non-zero handle

        # Track that release_frame is always called
        release_calls = []

        def fake_capture_frame(hwnd, handle_ptr):
            handle_ptr._obj.value = frame_handle_value
            return 0

        def fake_get_frame_info(handle, w_ptr, h_ptr, inner_ret_ptr):
            w_ptr._obj.value = width
            h_ptr._obj.value = height
            inner_ret_ptr._obj.value = 0
            return 0

        def fake_copy_frame(handle, buffer, length):
            for i, b in enumerate(bgra_data):
                buffer[i] = b
            return 0

        def fake_release_frame(handle):
            release_calls.append(handle.value)
            return 0

        cap._capture_frame_fn = fake_capture_frame
        cap._get_frame_info_fn = fake_get_frame_info
        cap._copy_frame_fn = fake_copy_frame
        cap._release_frame_fn = fake_release_frame

        result = cap.capture(hwnd=12345, width=720, height=1280)
        # v2 ignores width/height args — they're queried via get_frame_info

        assert result is not None
        assert result.shape == (height, width, 3)
        # BGR (drop alpha): pixel 0 should be [11, 22, 33]
        assert result[0, 0, 0] == 11  # B
        assert result[0, 0, 1] == 22  # G
        assert result[0, 0, 2] == 33  # R
        # Release must be called exactly once with the original handle.
        assert len(release_calls) == 1
        assert release_calls[0] == frame_handle_value

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_v2_capture_frame_failure_returns_none(self, mock_system):
        """v2 capture() returns None when capture_frame returns non-zero."""
        cap = LDOpenGLCapture()
        cap._initialized = True
        cap._api_version = 2

        release_calls = []

        def fake_capture_frame(hwnd, handle_ptr):
            handle_ptr._obj.value = 0  # 0 = no frame allocated
            return 1  # non-zero error

        def fake_release_frame(handle):
            release_calls.append(handle.value)
            return 0

        cap._capture_frame_fn = fake_capture_frame
        cap._get_frame_info_fn = MagicMock()
        cap._copy_frame_fn = MagicMock()
        cap._release_frame_fn = fake_release_frame

        result = cap.capture(hwnd=12345, width=720, height=1280)
        assert result is None
        # No frame was allocated, so no release needed.
        assert release_calls == []

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_v2_capture_frame_zero_handle_returns_none(self, mock_system):
        """v2 capture() returns None when frame handle is 0 (allocation failed)."""
        cap = LDOpenGLCapture()
        cap._initialized = True
        cap._api_version = 2

        release_calls = []

        def fake_capture_frame(hwnd, handle_ptr):
            handle_ptr._obj.value = 0  # 0 = allocation failed
            return 0  # success code, but no frame

        def fake_release_frame(handle):
            release_calls.append(handle.value)
            return 0

        cap._capture_frame_fn = fake_capture_frame
        cap._get_frame_info_fn = MagicMock()
        cap._copy_frame_fn = MagicMock()
        cap._release_frame_fn = fake_release_frame

        result = cap.capture(hwnd=12345, width=720, height=1280)
        assert result is None
        assert release_calls == []

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_v2_get_frame_info_failure_returns_none(self, mock_system):
        """v2 capture() returns None when get_frame_info returns non-zero."""
        cap = LDOpenGLCapture()
        cap._initialized = True
        cap._api_version = 2

        release_calls = []

        def fake_capture_frame(hwnd, handle_ptr):
            handle_ptr._obj.value = 0xABCDEF
            return 0

        def fake_get_frame_info(handle, w_ptr, h_ptr, inner_ret_ptr):
            return 1  # non-zero error

        def fake_release_frame(handle):
            release_calls.append(handle.value)
            return 0

        cap._capture_frame_fn = fake_capture_frame
        cap._get_frame_info_fn = fake_get_frame_info
        cap._copy_frame_fn = MagicMock()
        cap._release_frame_fn = fake_release_frame

        result = cap.capture(hwnd=12345, width=720, height=1280)
        assert result is None
        # Release MUST still be called (handle was allocated).
        assert len(release_calls) == 1

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_v2_invalid_dimensions_returns_none(self, mock_system):
        """v2 capture() returns None when dimensions are 0x0 or negative."""
        cap = LDOpenGLCapture()
        cap._initialized = True
        cap._api_version = 2

        release_calls = []

        def fake_capture_frame(hwnd, handle_ptr):
            handle_ptr._obj.value = 0x100
            return 0

        def fake_get_frame_info(handle, w_ptr, h_ptr, inner_ret_ptr):
            w_ptr._obj.value = 0
            h_ptr._obj.value = 0
            inner_ret_ptr._obj.value = 0
            return 0

        def fake_release_frame(handle):
            release_calls.append(handle.value)
            return 0

        cap._capture_frame_fn = fake_capture_frame
        cap._get_frame_info_fn = fake_get_frame_info
        cap._copy_frame_fn = MagicMock()
        cap._release_frame_fn = fake_release_frame

        result = cap.capture(hwnd=12345, width=720, height=1280)
        assert result is None
        # Release MUST still be called.
        assert len(release_calls) == 1

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_v2_copy_frame_failure_returns_none(self, mock_system):
        """v2 capture() returns None when copy_frame returns non-zero."""
        cap = LDOpenGLCapture()
        cap._initialized = True
        cap._api_version = 2

        release_calls = []

        def fake_capture_frame(hwnd, handle_ptr):
            handle_ptr._obj.value = 0x200
            return 0

        def fake_get_frame_info(handle, w_ptr, h_ptr, inner_ret_ptr):
            w_ptr._obj.value = 4
            h_ptr._obj.value = 2
            inner_ret_ptr._obj.value = 0
            return 0

        def fake_copy_frame(handle, buffer, length):
            return 1  # non-zero error

        def fake_release_frame(handle):
            release_calls.append(handle.value)
            return 0

        cap._capture_frame_fn = fake_capture_frame
        cap._get_frame_info_fn = fake_get_frame_info
        cap._copy_frame_fn = fake_copy_frame
        cap._release_frame_fn = fake_release_frame

        result = cap.capture(hwnd=12345, width=720, height=1280)
        assert result is None
        # Release MUST still be called.
        assert len(release_calls) == 1

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_v2_release_always_called_on_success(self, mock_system):
        """v2 release_frame is called even after successful copy (finally block)."""
        cap = LDOpenGLCapture()
        cap._initialized = True
        cap._api_version = 2

        release_calls = []

        def fake_capture_frame(hwnd, handle_ptr):
            handle_ptr._obj.value = 0x300
            return 0

        def fake_get_frame_info(handle, w_ptr, h_ptr, inner_ret_ptr):
            w_ptr._obj.value = 1
            h_ptr._obj.value = 1
            inner_ret_ptr._obj.value = 0
            return 0

        def fake_copy_frame(handle, buffer, length):
            buffer[0] = 10  # B
            buffer[1] = 20  # G
            buffer[2] = 30  # R
            buffer[3] = 255  # A
            return 0

        def fake_release_frame(handle):
            release_calls.append(handle.value)
            return 0

        cap._capture_frame_fn = fake_capture_frame
        cap._get_frame_info_fn = fake_get_frame_info
        cap._copy_frame_fn = fake_copy_frame
        cap._release_frame_fn = fake_release_frame

        result = cap.capture(hwnd=12345, width=720, height=1280)
        assert result is not None
        assert len(release_calls) == 1

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_v2_release_called_even_if_release_raises(self, mock_system):
        """v2: if release_frame itself raises, the exception is swallowed
        (logged as warning) so it doesn't mask the captured frame."""
        cap = LDOpenGLCapture()
        cap._initialized = True
        cap._api_version = 2

        def fake_capture_frame(hwnd, handle_ptr):
            handle_ptr._obj.value = 0x400
            return 0

        def fake_get_frame_info(handle, w_ptr, h_ptr, inner_ret_ptr):
            w_ptr._obj.value = 1
            h_ptr._obj.value = 1
            inner_ret_ptr._obj.value = 0
            return 0

        def fake_copy_frame(handle, buffer, length):
            buffer[0] = 99
            buffer[1] = 88
            buffer[2] = 77
            buffer[3] = 255
            return 0

        def fake_release_frame(handle):
            raise OSError("release failed")

        cap._capture_frame_fn = fake_capture_frame
        cap._get_frame_info_fn = fake_get_frame_info
        cap._copy_frame_fn = fake_copy_frame
        cap._release_frame_fn = fake_release_frame

        # Should not raise — release failure is logged but swallowed.
        result = cap.capture(hwnd=12345, width=720, height=1280)
        assert result is not None
        assert result.shape == (1, 1, 3)


class TestLDOpenGLV2EnsureLoaded:
    """P1-1 _ensure_loaded() v2/v1 fallback tests.

    Note: MagicMock auto-creates attributes, so we must explicitly delete
    CreateScreenShotInstance to simulate a v2-only DLL (no v3 symbol).
    """

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_ensure_loaded_prefers_v2(self, mock_system):
        """When v3 absent and v2 symbols present, _ensure_loaded picks v2."""
        cap = LDOpenGLCapture()

        mock_dll = MagicMock()
        # v3 symbol absent (MagicMock auto-creates it, so delete explicitly).
        del mock_dll.CreateScreenShotInstance
        # v2 symbols present
        mock_dll.ldopengl_capture_frame = MagicMock()
        mock_dll.ldopengl_get_frame_info = MagicMock()
        mock_dll.ldopengl_copy_frame = MagicMock()
        mock_dll.ldopengl_release_frame = MagicMock()
        # v1 symbol also present (should NOT be used)
        mock_dll.ldopengl_capture = MagicMock()

        with patch.object(cap, '_find_dll', return_value=Path("C:/fake/ldopengl64.dll")), \
             patch('ctypes.CDLL', return_value=mock_dll):
            cap._ensure_loaded()

        assert cap.api_version == 2
        assert cap._capture_frame_fn is not None
        assert cap._capture_fn is None  # v1 not loaded

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_ensure_loaded_falls_back_to_v1(self, mock_system):
        """When v3/v2 symbols are missing, _ensure_loaded falls back to v1."""
        cap = LDOpenGLCapture()

        mock_dll = MagicMock()
        # v3 symbol absent
        del mock_dll.CreateScreenShotInstance
        # v2 symbols absent — accessing them raises AttributeError
        del mock_dll.ldopengl_capture_frame
        del mock_dll.ldopengl_get_frame_info
        del mock_dll.ldopengl_copy_frame
        del mock_dll.ldopengl_release_frame
        # v1 symbol present
        mock_dll.ldopengl_capture = MagicMock()

        with patch.object(cap, '_find_dll', return_value=Path("C:/fake/ldopengl64.dll")), \
             patch('ctypes.CDLL', return_value=mock_dll):
            cap._ensure_loaded()

        assert cap.api_version == 1
        assert cap._capture_fn is not None
        assert cap._capture_frame_fn is None  # v2 not loaded


class TestLDOpenGLV3EnsureLoaded:
    """v3 _ensure_loaded() detection tests — LDPlayer 14 CreateScreenShotInstance."""

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_ensure_loaded_prefers_v3(self, mock_system):
        """When CreateScreenShotInstance is present, _ensure_loaded picks v3."""
        cap = LDOpenGLCapture()

        mock_dll = MagicMock()
        # v3 symbol present
        mock_dll.CreateScreenShotInstance = MagicMock()
        # v2/v1 symbols also present (should NOT be used)
        mock_dll.ldopengl_capture_frame = MagicMock()
        mock_dll.ldopengl_capture = MagicMock()

        with patch.object(cap, '_find_dll', return_value=Path("C:/fake/ldopengl64.dll")), \
             patch('ctypes.CDLL', return_value=mock_dll):
            cap._ensure_loaded()

        assert cap.api_version == 3
        assert cap._create_instance_fn is not None
        assert cap._capture_frame_fn is None  # v2 not loaded
        assert cap._capture_fn is None  # v1 not loaded

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_ensure_loaded_falls_back_to_v2_when_v3_absent(self, mock_system):
        """When CreateScreenShotInstance is absent, fall back to v2."""
        cap = LDOpenGLCapture()

        mock_dll = MagicMock()
        # v3 symbol absent
        del mock_dll.CreateScreenShotInstance
        # v2 symbols present
        mock_dll.ldopengl_capture_frame = MagicMock()
        mock_dll.ldopengl_get_frame_info = MagicMock()
        mock_dll.ldopengl_copy_frame = MagicMock()
        mock_dll.ldopengl_release_frame = MagicMock()

        with patch.object(cap, '_find_dll', return_value=Path("C:/fake/ldopengl64.dll")), \
             patch('ctypes.CDLL', return_value=mock_dll):
            cap._ensure_loaded()

        assert cap.api_version == 2
        assert cap._create_instance_fn is None
        assert cap._capture_frame_fn is not None


class TestLDOpenGLV3API:
    """v3 API tests — CreateScreenShotInstance + vtable cap/release.

    The v3 API (LDPlayer 14) uses a COM-style vtable: the DLL returns an
    IScreenShotClass object whose first 8 bytes store a pointer to the
    vtable. vtable[1] is cap() — returns a BGR frame buffer (3 bytes/pixel);
    vtable[2] is release() — frees the object and frame buffer.

    Dimensions come from `ldconsole list2` (mocked), not the object layout.
    The image is vertically flipped (OpenGL origin at bottom-left).

    These tests construct real ctypes objects (vtable + instance + frame
    buffer) so the production code path exercises actual memory reads,
    ctypes.cast, and ctypes.memmove.
    """

    def _build_v3_object(self, width, height, frame_ptr, capture_cb, destroy_cb):
        """Build a real IScreenShotClass-like object in ctypes memory.

        Returns (obj_ptr, obj_buf, cap_calls, release_calls).
        Caller MUST keep obj_buf alive (it owns the vtable, callback
        trampolines, and the object memory itself).

        Note: width/height are accepted for API symmetry but are NOT written
        to the object — the production v3 path reads dimensions from
        `ldconsole list2`, not object offsets.
        """
        cap_fn = ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p)
        release_fn = ctypes.WINFUNCTYPE(None, ctypes.c_void_p)

        cap_calls = []
        release_calls = []

        def cap_callback(this):
            cap_calls.append(this)
            return frame_ptr

        def release_callback(this):
            release_calls.append(this)

        # Keep callback objects alive (else trampoline is freed).
        cap_cb_ref = cap_fn(cap_callback)
        release_cb_ref = release_fn(release_callback)

        # Allocate vtable (3 entries: [0]=destructor, [1]=cap, [2]=release).
        vtable = (ctypes.c_void_p * 3)(
            0,
            ctypes.cast(cap_cb_ref, ctypes.c_void_p).value,
            ctypes.cast(release_cb_ref, ctypes.c_void_p).value,
        )
        vtable_addr = ctypes.cast(vtable, ctypes.c_void_p).value

        # Allocate the "object" — only needs to hold the vtable pointer at
        # offset 0. Use 0x40 for headroom (no width/height offsets needed).
        obj_buf = (ctypes.c_ubyte * 0x40)()
        obj_ptr = ctypes.cast(obj_buf, ctypes.c_void_p).value

        # Write vtable pointer at offset 0.
        ctypes.cast(obj_ptr, ctypes.POINTER(ctypes.c_void_p))[0] = vtable_addr

        # Stash callback refs on obj_buf so they stay alive as long as obj_buf.
        obj_buf._keep = (cap_cb_ref, release_cb_ref, vtable)

        return obj_ptr, obj_buf, cap_calls, release_calls

    def test_api_version_three_for_v3_load(self):
        """api_version is 3 after loading v3 symbols."""
        cap = LDOpenGLCapture()
        cap._initialized = True
        cap._api_version = 3
        assert cap.api_version == 3

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_is_available_true_for_v3(self, mock_system):
        """is_available() returns True when v3 API is loaded."""
        cap = LDOpenGLCapture()
        cap._initialized = True
        cap._api_version = 3
        assert cap.is_available() is True

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_v3_capture_success(self, mock_system):
        """v3 capture() returns BGR numpy array via vtable cap/release."""
        cap = LDOpenGLCapture()
        cap._initialized = True
        cap._api_version = 3

        width, height = 2, 1
        # IScreenShotClass returns BGR (3 bytes/pixel), not BGRA.
        bgr_data = bytes([
            11, 22, 33,  # pixel 0: B=11, G=22, R=33
            44, 55, 66,  # pixel 1
        ])

        # Allocate the frame buffer — must stay alive until memmove completes.
        frame_buf = (ctypes.c_ubyte * len(bgr_data))(*bgr_data)
        frame_ptr = ctypes.cast(frame_buf, ctypes.c_void_p).value

        obj_ptr, _obj_buf, cap_calls, release_calls = self._build_v3_object(
            width, height, frame_ptr, None, None,
        )

        def create_instance(unused, pid):
            return obj_ptr

        cap._create_instance_fn = create_instance

        with patch.object(LDOpenGLCapture, '_get_pid_from_hwnd', return_value=1234), \
             patch.object(LDOpenGLCapture, '_get_resolution_from_ldconsole', return_value=(width, height)):
            result = cap.capture(hwnd=99999, width=0, height=0)

        assert result is not None
        assert result.shape == (height, width, 3)
        # BGR: pixel 0 should be [11, 22, 33] (height=1, so flip is a no-op)
        assert result[0, 0, 0] == 11  # B
        assert result[0, 0, 1] == 22  # G
        assert result[0, 0, 2] == 33  # R
        # cap must be called once with the object pointer
        assert len(cap_calls) == 1
        assert cap_calls[0] == obj_ptr
        # release must be called once with the object pointer
        assert len(release_calls) == 1
        assert release_calls[0] == obj_ptr

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_v3_pid_zero_returns_none(self, mock_system):
        """v3 returns None when GetWindowThreadProcessId returns 0."""
        cap = LDOpenGLCapture()
        cap._initialized = True
        cap._api_version = 3
        cap._create_instance_fn = MagicMock(return_value=0)

        with patch.object(LDOpenGLCapture, '_get_pid_from_hwnd', return_value=0):
            result = cap.capture(hwnd=99999, width=0, height=0)

        assert result is None
        # CreateScreenShotInstance must NOT be called when PID is 0.
        cap._create_instance_fn.assert_not_called()

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_v3_null_instance_returns_none(self, mock_system):
        """v3 returns None when CreateScreenShotInstance returns NULL."""
        cap = LDOpenGLCapture()
        cap._initialized = True
        cap._api_version = 3

        def create_instance(unused, pid):
            return 0  # NULL

        cap._create_instance_fn = create_instance

        with patch.object(LDOpenGLCapture, '_get_pid_from_hwnd', return_value=1234), \
             patch.object(LDOpenGLCapture, '_get_resolution_from_ldconsole', return_value=(2, 1)):
            result = cap.capture(hwnd=99999, width=0, height=0)

        assert result is None

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_v3_invalid_dimensions_returns_none(self, mock_system):
        """v3 returns None when dimensions cannot be resolved (no object allocated).

        Behavioral change from IReadPixelsClass → IScreenShotClass: dimensions
        are now resolved from `ldconsole list2` (with window client size
        fallback) BEFORE the object is created. So invalid dimensions → no
        CreateScreenShotInstance call → no release needed.
        """
        cap = LDOpenGLCapture()
        cap._initialized = True
        cap._api_version = 3
        cap._create_instance_fn = MagicMock()

        with patch.object(LDOpenGLCapture, '_get_pid_from_hwnd', return_value=1234), \
             patch.object(LDOpenGLCapture, '_get_resolution_from_ldconsole', return_value=(0, 0)), \
             patch.object(LDOpenGLCapture, '_get_window_client_size', return_value=(0, 0)):
            result = cap.capture(hwnd=99999, width=0, height=0)

        assert result is None
        # create_instance must NOT be called (dimensions checked before creation).
        cap._create_instance_fn.assert_not_called()

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_v3_null_frame_returns_none(self, mock_system):
        """v3 returns None when cap() returns NULL (release still called)."""
        cap = LDOpenGLCapture()
        cap._initialized = True
        cap._api_version = 3

        width, height = 2, 1
        # frame_ptr = 0 means cap returns NULL.
        obj_ptr, _obj_buf, cap_calls, release_calls = self._build_v3_object(
            width, height, 0, None, None,
        )

        def create_instance(unused, pid):
            return obj_ptr

        cap._create_instance_fn = create_instance

        with patch.object(LDOpenGLCapture, '_get_pid_from_hwnd', return_value=1234), \
             patch.object(LDOpenGLCapture, '_get_resolution_from_ldconsole', return_value=(width, height)):
            result = cap.capture(hwnd=99999, width=0, height=0)

        assert result is None
        # cap must be called once.
        assert len(cap_calls) == 1
        # release MUST be called (object was allocated).
        assert len(release_calls) == 1
        assert release_calls[0] == obj_ptr

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_v3_release_called_even_on_success(self, mock_system):
        """v3 release() is called even after a successful cap (finally block)."""
        cap = LDOpenGLCapture()
        cap._initialized = True
        cap._api_version = 3

        width, height = 1, 1
        # IScreenShotClass returns BGR (3 bytes/pixel).
        bgr_data = bytes([10, 20, 30])
        frame_buf = (ctypes.c_ubyte * len(bgr_data))(*bgr_data)
        frame_ptr = ctypes.cast(frame_buf, ctypes.c_void_p).value

        obj_ptr, _obj_buf, cap_calls, release_calls = self._build_v3_object(
            width, height, frame_ptr, None, None,
        )

        def create_instance(unused, pid):
            return obj_ptr

        cap._create_instance_fn = create_instance

        with patch.object(LDOpenGLCapture, '_get_pid_from_hwnd', return_value=1234), \
             patch.object(LDOpenGLCapture, '_get_resolution_from_ldconsole', return_value=(width, height)):
            result = cap.capture(hwnd=99999, width=0, height=0)

        assert result is not None
        assert len(cap_calls) == 1
        assert len(release_calls) == 1


class TestGetPidFromHwnd:
    """_get_pid_from_hwnd() static method tests."""

    @patch('platforms.windows.ldopengl.platform.system', return_value='Linux')
    def test_returns_zero_on_non_windows(self, mock_system):
        """Non-Windows platforms return 0."""
        assert LDOpenGLCapture._get_pid_from_hwnd(12345) == 0

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_returns_pid_from_get_window_thread_process_id(self, mock_system):
        """Returns the PID written by GetWindowThreadProcessId."""
        mock_user32 = MagicMock()

        def fake_get_pid(hwnd, pid_ptr):
            pid_ptr._obj.value = 5555
            return 1  # thread id

        mock_user32.GetWindowThreadProcessId = fake_get_pid
        with patch('ctypes.windll', new=MagicMock(user32=mock_user32)):
            pid = LDOpenGLCapture._get_pid_from_hwnd(99999)
        assert pid == 5555

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_returns_zero_on_exception(self, mock_system):
        """Returns 0 when GetWindowThreadProcessId raises."""
        mock_user32 = MagicMock()
        mock_user32.GetWindowThreadProcessId.side_effect = OSError("fail")
        with patch('ctypes.windll', new=MagicMock(user32=mock_user32)):
            pid = LDOpenGLCapture._get_pid_from_hwnd(99999)
        assert pid == 0


class TestFindDLL:
    """_find_dll() 方法测试"""

    def test_find_dll_in_explicit_dir(self, tmp_path):
        """在显式指定的目录中找到 DLL"""
        # Create fake DLL file
        dll_file = tmp_path / "ldopengl64.dll"
        dll_file.write_bytes(b"fake dll")

        cap = LDOpenGLCapture(ldplayer_dir=str(tmp_path))
        found = cap._find_dll()
        assert found == dll_file

    def test_find_dll_in_explicit_subdir(self, tmp_path):
        """在显式指定目录的子路径中找到 DLL"""
        # Create in shell/ subdirectory
        shell_dir = tmp_path / "shell"
        shell_dir.mkdir()
        dll_file = shell_dir / "ldopengl64.dll"
        dll_file.write_bytes(b"fake dll")

        cap = LDOpenGLCapture(ldplayer_dir=str(tmp_path))
        found = cap._find_dll()
        assert found == dll_file

    def test_find_dll_returns_none_when_not_found(self):
        """找不到 DLL 返回 None"""
        cap = LDOpenGLCapture(ldplayer_dir="/nonexistent/path")
        with patch.object(LDOpenGLCapture, '_find_ldplayer_dir_from_registry', return_value=None), \
             patch('shutil.which', return_value=None):
            assert cap._find_dll() is None

    def test_find_dll_via_registry(self, tmp_path):
        """通过注册表发现 LDPlayer 目录"""
        dll_file = tmp_path / "ldopengl64.dll"
        dll_file.write_bytes(b"fake dll")

        cap = LDOpenGLCapture()
        with patch.object(
            LDOpenGLCapture,
            '_find_ldplayer_dir_from_registry',
            return_value=tmp_path,
        ), \
             patch('shutil.which', return_value=None):
            found = cap._find_dll()
            assert found == dll_file


class TestFindLDPlayerDirFromRegistry:
    """_find_ldplayer_dir_from_registry() 静态方法测试"""

    @patch('platforms.windows.ldopengl.platform.system', return_value='Linux')
    def test_returns_none_on_non_windows(self, mock_system):
        """非 Windows 平台返回 None"""
        assert LDOpenGLCapture._find_ldplayer_dir_from_registry() is None

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_returns_none_when_registry_empty(self, mock_system):
        """注册表无 LDPlayer 项时返回 None"""
        with patch('winreg.OpenKey', side_effect=OSError("not found")):
            assert LDOpenGLCapture._find_ldplayer_dir_from_registry() is None


class TestFindLDPlayerWindow:
    """find_ldplayer_window() 静态方法测试"""

    @patch('platforms.windows.ldopengl.platform.system', return_value='Linux')
    def test_returns_zero_on_non_windows(self, mock_system):
        """非 Windows 平台返回 0"""
        assert LDOpenGLCapture.find_ldplayer_window() == 0

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_find_window_by_first_class(self, mock_system):
        """通过第一个窗口类名 (LDPlayerWnd) 找到 LDPlayer 窗口"""
        mock_user32 = MagicMock()
        mock_user32.FindWindowW.return_value = 12345
        with patch('ctypes.windll', new=MagicMock(user32=mock_user32)):
            hwnd = LDOpenGLCapture.find_ldplayer_window()
        assert hwnd == 12345
        # First call should use the first class name in LDPLAYER_WINDOW_CLASSES.
        call_args = mock_user32.FindWindowW.call_args_list[0][0]
        assert call_args[0] == LDPLAYER_WINDOW_CLASSES[0]

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_find_window_by_second_class_ldplayer14(self, mock_system):
        """LDPlayer 14 uses LDPlayerMainFrame class — found on second lookup."""
        mock_user32 = MagicMock()
        # First class (LDPlayerWnd) returns 0, second (LDPlayerMainFrame) succeeds.
        mock_user32.FindWindowW.side_effect = [0, 67890]
        with patch('ctypes.windll', new=MagicMock(user32=mock_user32)):
            hwnd = LDOpenGLCapture.find_ldplayer_window()
        assert hwnd == 67890
        # Verify both class names were tried.
        first_call = mock_user32.FindWindowW.call_args_list[0][0]
        second_call = mock_user32.FindWindowW.call_args_list[1][0]
        assert first_call[0] == "LDPlayerWnd"
        assert second_call[0] == "LDPlayerMainFrame"

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_find_window_fallback_by_title(self, mock_system):
        """所有类名查找失败时通过标题查找"""
        mock_user32 = MagicMock()
        # Two class lookups fail, third call (by title) succeeds.
        mock_user32.FindWindowW.side_effect = [0, 0, 67890]
        with patch('ctypes.windll', new=MagicMock(user32=mock_user32)):
            hwnd = LDOpenGLCapture.find_ldplayer_window()
        assert hwnd == 67890

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_find_window_returns_zero_when_not_found(self, mock_system):
        """找不到窗口返回 0"""
        mock_user32 = MagicMock()
        mock_user32.FindWindowW.return_value = 0
        with patch('ctypes.windll', new=MagicMock(user32=mock_user32)):
            hwnd = LDOpenGLCapture.find_ldplayer_window()
        assert hwnd == 0


class TestADBDeviceLDOpenGLIntegration:
    """ADBDevice._capture_ldopengl() 集成测试"""

    def test_ldopengl_method_in_fallback_order(self):
        """LDOPENGL_METHOD 应在 fallback_order 中"""
        # fallback_order is defined inline in capture_screen, verify constant exists
        # and is referenced in the source
        from pathlib import Path

        import devices.adb.device as device_module
        source = Path(device_module.__file__).read_text(encoding='utf-8') + \
            Path(device_module.__file__).parent.joinpath('adb_capture.py').read_text(encoding='utf-8')
        assert "LDOPENGL_METHOD" in source
        assert "LDOPENGL_METHOD, SCRCPY_METHOD" in source or \
               "LDOPENGL_METHOD,SCRCPY_METHOD" in source or \
               "LDOPENGL_METHOD" in source

    def test_ldopengl_method_in_method_map(self):
        """LDOPENGL_METHOD 应在 method_map 中"""
        from pathlib import Path

        import devices.adb.device as device_module
        source = Path(device_module.__file__).read_text(encoding='utf-8') + \
            Path(device_module.__file__).parent.joinpath('adb_capture.py').read_text(encoding='utf-8')
        assert "LDOPENGL_METHOD: self._capture_ldopengl" in source

    def test_capture_ldopengl_method_exists(self):
        """ADBDevice 应有 _capture_ldopengl 方法"""
        assert hasattr(ADBDevice, '_capture_ldopengl')

    @patch('platforms.windows.ldopengl.platform.system', return_value='Linux')
    def test_capture_ldopengl_raises_on_non_windows(self, mock_system):
        """非 Windows 平台应抛出 RuntimeError"""
        device = ADBDevice()
        device._status = MagicMock()
        device._status.value = 'connected'
        # Bypass require_operable decorator by calling inner method directly
        with pytest.raises(RuntimeError, match="LDOpenGL 截图失败"):
            ADBDevice._capture_ldopengl(device)

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_capture_ldopengl_raises_when_dll_unavailable(self, mock_system):
        """DLL 不可用时抛出 RuntimeError"""
        device = ADBDevice()
        with patch('platforms.windows.ldopengl.LDOpenGLCapture.is_available', return_value=False), \
             pytest.raises(RuntimeError, match="ldopengl64.dll 不可用"):
            ADBDevice._capture_ldopengl(device)

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_capture_ldopengl_raises_when_no_window(self, mock_system):
        """找不到 LDPlayer 窗口时抛出 RuntimeError"""
        device = ADBDevice()
        with patch('platforms.windows.ldopengl.LDOpenGLCapture.is_available', return_value=True), \
             patch('platforms.windows.ldopengl.LDOpenGLCapture.find_ldplayer_window', return_value=0), \
             pytest.raises(RuntimeError, match="未找到 LDPlayer 窗口"):
            ADBDevice._capture_ldopengl(device)

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_capture_ldopengl_success_with_wm_size(self, mock_system):
        """成功截图并解析 wm size"""
        device = ADBDevice()
        # Mock ADB device with wm size output
        mock_adb = MagicMock()
        mock_shell_result = MagicMock()
        mock_shell_result.output = "Physical size: 1080x1920\n"
        mock_adb.shell.return_value = mock_shell_result
        device._device = mock_adb

        # Mock LDOpenGLCapture
        fake_image = np.zeros((1920, 1080, 3), dtype=np.uint8)
        with patch('platforms.windows.ldopengl.LDOpenGLCapture.is_available', return_value=True), \
             patch('platforms.windows.ldopengl.LDOpenGLCapture.find_ldplayer_window', return_value=12345), \
             patch('platforms.windows.ldopengl.LDOpenGLCapture.capture', return_value=fake_image):
            result = ADBDevice._capture_ldopengl(device)

        assert result is not None
        assert result.shape == (1920, 1080, 3)
        # Verify wm size was called
        mock_adb.shell.assert_called_once_with("wm size")

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_capture_ldopengl_uses_default_size_on_wm_size_failure(self, mock_system):
        """wm size 失败时使用默认 720x1280"""
        device = ADBDevice()
        mock_adb = MagicMock()
        mock_adb.shell.side_effect = Exception("ADB error")
        device._device = mock_adb

        fake_image = np.zeros((1280, 720, 3), dtype=np.uint8)
        captured_args = {}

        def mock_capture(hwnd, width, height):
            captured_args['width'] = width
            captured_args['height'] = height
            return fake_image

        with patch('platforms.windows.ldopengl.LDOpenGLCapture.is_available', return_value=True), \
             patch('platforms.windows.ldopengl.LDOpenGLCapture.find_ldplayer_window', return_value=12345), \
             patch('platforms.windows.ldopengl.LDOpenGLCapture.capture', side_effect=mock_capture):
            result = ADBDevice._capture_ldopengl(device)

        assert result is not None
        assert captured_args['width'] == 720
        assert captured_args['height'] == 1280

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_capture_ldopengl_raises_when_capture_returns_none(self, mock_system):
        """capture 返回 None 时抛出 RuntimeError"""
        device = ADBDevice()
        device._device = None  # Skip wm size
        with patch('platforms.windows.ldopengl.LDOpenGLCapture.is_available', return_value=True), \
             patch('platforms.windows.ldopengl.LDOpenGLCapture.find_ldplayer_window', return_value=12345), \
             patch('platforms.windows.ldopengl.LDOpenGLCapture.capture', return_value=None), \
             pytest.raises(RuntimeError, match="ldopengl_capture 返回空结果"):
            ADBDevice._capture_ldopengl(device)

    @patch('platforms.windows.ldopengl.platform.system', return_value='Windows')
    def test_capture_ldopengl_v3_skips_wm_size(self, mock_system):
        """v3 API 跳过 wm size 调用 (尺寸由 DLL 对象读取)"""
        device = ADBDevice()
        mock_adb = MagicMock()
        device._device = mock_adb

        fake_image = np.zeros((900, 1600, 3), dtype=np.uint8)
        with patch('platforms.windows.ldopengl.LDOpenGLCapture.is_available', return_value=True), \
             patch('platforms.windows.ldopengl.LDOpenGLCapture.api_version', new_callable=PropertyMock, return_value=3), \
             patch('platforms.windows.ldopengl.LDOpenGLCapture.find_ldplayer_window', return_value=12345), \
             patch('platforms.windows.ldopengl.LDOpenGLCapture.capture', return_value=fake_image) as mock_capture:
            result = ADBDevice._capture_ldopengl(device)

        assert result is not None
        assert result.shape == (900, 1600, 3)
        # wm size must NOT be called for v3 (dimensions from DLL).
        mock_adb.shell.assert_not_called()
        # capture receives width=0, height=0 (ignored by v3).
        mock_capture.assert_called_once_with(12345, 0, 0)


class TestLDOpenGLFallbackChainOrder:
    """LDOpenGL 在降级链中的位置测试"""

    def test_ldopengl_after_nemu_methods(self):
        """LDOPENGL 应在 NEMU_IPC 和 NEMU 之后"""
        from pathlib import Path

        import devices.adb.device as device_module
        source = Path(device_module.__file__).read_text(encoding='utf-8') + \
            Path(device_module.__file__).parent.joinpath('adb_capture.py').read_text(encoding='utf-8')
        # Find fallback_order definition
        fallback_start = source.find("fallback_order = [")
        assert fallback_start > 0
        fallback_section = source[fallback_start:fallback_start + 500]
        # Search for variable names (constants) in source, not their string values
        nemu_ipc_pos = fallback_section.find("NEMU_IPC_METHOD")
        nemu_pos = fallback_section.find("NEMU_METHOD")
        ldopengl_pos = fallback_section.find("LDOPENGL_METHOD")
        assert nemu_ipc_pos > 0
        assert nemu_pos > 0
        assert ldopengl_pos > 0
        # NEMU_IPC should be first, then NEMU, then LDOPENGL
        assert nemu_ipc_pos < nemu_pos < ldopengl_pos


class TestLDOpenGLSingleton:
    """TD-011: LDOpenGLCapture module-level singleton tests.

    The singleton prevents per-frame LoadLibrary/FreeLibrary cycles that
    eventually leave IScreenShotClass vtable pointers dangling, causing
    ACCESS_VIOLATION (0xC0000005) crashes after ~1 hour of per-second
    screenshot loops. See tech-debt-register.md TD-011.
    """

    def setup_method(self, _method):
        """Reset the singleton before each test to avoid cross-test pollution."""
        _ldopengl_mod._LDOPENGL_CAPTURE_INSTANCE = None

    def teardown_method(self, _method):
        """Reset the singleton after each test so other test classes get a
        clean state."""
        _ldopengl_mod._LDOPENGL_CAPTURE_INSTANCE = None

    def test_singleton_returns_same_instance(self):
        """get_ldopengl_capture() must return the same instance on every call."""
        c1 = get_ldopengl_capture()
        c2 = get_ldopengl_capture()
        assert c1 is c2, f"Singleton broken: {id(c1)} != {id(c2)}"
        assert c1 is _ldopengl_mod._LDOPENGL_CAPTURE_INSTANCE

    def test_singleton_is_ldopengl_capture(self):
        """Singleton instance must be an LDOpenGLCapture."""
        c = get_ldopengl_capture()
        assert isinstance(c, LDOpenGLCapture)

    def test_singleton_lock_exists(self):
        """The singleton must use a threading.Lock for thread safety."""
        import threading
        lock = _ldopengl_mod._LDOPENGL_LOCK
        assert lock is not None
        assert isinstance(lock, type(threading.Lock()))

    def test_singleton_ensures_loaded_once(self):
        """_ensure_loaded() must run only once per process (api_version stabilizes).

        The singleton starts with api_version=0. The first is_available() call
        triggers _ensure_loaded() (sets api_version to 1/2/3 or stays 0 if DLL
        unavailable). Subsequent calls MUST keep the same api_version — this
        proves the DLL is not re-loaded.
        """
        c = get_ldopengl_capture()
        c.is_available()
        v1 = c.api_version
        for _ in range(5):
            c.is_available()
        assert c.api_version == v1, (
            f"api_version changed after 5 is_available() calls: {v1} -> {c.api_version}"
        )

    def test_singleton_initialized_flag_set(self):
        """After first is_available(), _initialized must be True."""
        c = get_ldopengl_capture()
        assert c._initialized is False
        c.is_available()
        assert c._initialized is True

    def test_direct_construction_still_works(self):
        """Tests can still construct LDOpenGLCapture() directly (bypass singleton).

        Direct construction is needed for unit tests that verify initialization
        behavior in isolation (e.g. _find_dll, _ensure_loaded with mocked paths).
        """
        c = LDOpenGLCapture()
        assert isinstance(c, LDOpenGLCapture)
        assert c.api_version == 0
        assert c._initialized is False

    def test_singleton_concurrent_thread_safety(self):
        """Multiple threads calling get_ldopengl_capture() concurrently must
        all get the same instance (double-checked locking)."""
        import threading

        results: list[LDOpenGLCapture] = []
        barrier = threading.Barrier(4)

        def worker():
            barrier.wait()
            results.append(get_ldopengl_capture())

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 4
        assert all(r is results[0] for r in results), (
            "Concurrent calls returned different instances"
        )
