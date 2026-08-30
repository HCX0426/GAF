"""WGC 截图模块单元测试

使用 mock 避免需要真实窗口和 WinRT 运行时。
"""

import time
from unittest import mock

import numpy as np
import pytest

pytestmark = pytest.mark.unit


class TestWin32WGC:
    """Win32WGC 类测试"""

    def test_init_default_state(self):
        """验证初始状态"""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        assert wgc._initialized is False
        assert wgc._hwnd == 0
        assert wgc._d3d_device is None
        assert wgc._d3d_context is None

    def test_capture_before_init_returns_none(self):
        """验证未初始化时截图返回 None"""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        result = wgc.capture()
        assert result is None

    def test_initialize_failure_returns_false(self):
        """验证初始化失败返回 False 并清理资源"""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        with mock.patch.object(wgc, "_init_winrt", side_effect=RuntimeError("mock error")):
            result = wgc.initialize(12345)
            assert result is False
            assert wgc._initialized is False

    def test_release_cleans_resources(self):
        """验证 release 清理所有资源"""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._hwnd = 12345
        wgc._initialized = True
        wgc._d3d_device = 1
        wgc._d3d_context = 2
        wgc._capture_item = 3
        wgc._frame_pool = 4
        wgc._session = 5
        wgc._staging_texture = 6

        with mock.patch("platforms.windows.wgc._com_release") as mock_release:
            wgc.release()

        assert wgc._initialized is False
        assert wgc._hwnd == 0
        assert mock_release.call_count >= 6

    def test_initialize_with_mock_winrt(self):
        """验证完整初始化流程（mock WinRT 和 D3D11）"""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._hwnd = 12345

        with mock.patch.object(wgc, "_init_winrt") as m_winrt, \
             mock.patch.object(wgc, "_init_d3d11") as m_d3d, \
             mock.patch.object(wgc, "_init_capture_item") as m_item, \
             mock.patch.object(wgc, "_init_frame_pool") as m_pool, \
             mock.patch.object(wgc, "_init_staging_texture") as m_staging, \
             mock.patch.object(wgc, "_init_session") as m_session:
            result = wgc.initialize(12345)

        assert result is True
        assert wgc._initialized is True
        m_winrt.assert_called_once()
        m_d3d.assert_called_once()
        m_item.assert_called_once()
        m_pool.assert_called_once()
        m_staging.assert_called_once()
        m_session.assert_called_once()

    def test_initialize_skips_when_already_initialized(self):
        """验证已初始化时跳过重复初始化"""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._initialized = True

        with mock.patch.object(wgc, "_init_winrt") as m_winrt:
            result = wgc.initialize(12345)

        assert result is True
        m_winrt.assert_not_called()


class TestWGCEventMode:
    """P2-1 WGC event-driven mode tests (real COM FrameArrived callback)."""

    def test_event_mode_constants(self):
        """EVENT_POLL_INTERVAL_SEC is kept for backward-compat API surface."""
        from platforms.windows.wgc import Win32WGC

        assert Win32WGC.EVENT_POLL_INTERVAL_SEC > 0
        assert abs(Win32WGC.EVENT_POLL_INTERVAL_SEC - 1.0 / 60.0) < 0.001

    def test_event_mode_state_after_init(self):
        """Newly-initialized WGC has event mode disabled and callback state zeroed."""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        assert wgc._event_mode_enabled is False
        assert wgc._frame_arrived_event is not None
        assert wgc._frame_arrived_delegate_ptr == 0
        assert wgc._frame_arrived_token == 0
        assert wgc._cached_frame is None
        assert wgc._session_closed is False

    def test_enable_event_mode_without_init_returns_false(self):
        """enable_event_mode should refuse if WGC not initialized."""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        assert wgc.enable_event_mode() is False
        assert wgc._event_mode_enabled is False

    def test_enable_event_mode_without_frame_pool_returns_false(self):
        """enable_event_mode should refuse if frame_pool is missing."""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._initialized = True
        wgc._frame_pool = None  # explicitly no pool
        assert wgc.enable_event_mode() is False
        assert wgc._event_mode_enabled is False

    def test_enable_event_mode_with_init_succeeds(self):
        """enable_event_mode should register the COM delegate when initialized."""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._initialized = True
        wgc._frame_pool = 0xDEADBEEF  # truthy placeholder

        with mock.patch("platforms.windows.wgc.create_typed_event_handler_delegate") as mock_create, \
             mock.patch("platforms.windows.wgc._com_call") as mock_com:
            mock_create.return_value = 0xC0FFEE  # delegate ptr
            add_fn = mock.MagicMock()
            add_fn.return_value = 0  # S_OK
            mock_com.return_value = add_fn

            try:
                result = wgc.enable_event_mode()
                assert result is True
                assert wgc._event_mode_enabled is True
                assert wgc._frame_arrived_delegate_ptr == 0xC0FFEE
                # add_FrameArrived is at vtable index 8 — verify _com_call was
                # called with index 8 at least once during registration.
                com_indices = [call.args[1] for call in mock_com.call_args_list]
                assert 8 in com_indices
            finally:
                wgc.disable_event_mode()

    def test_enable_event_mode_idempotent(self):
        """Second enable_event_mode call returns False without re-registering."""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._initialized = True
        wgc._frame_pool = 0xDEADBEEF

        with mock.patch("platforms.windows.wgc.create_typed_event_handler_delegate") as mock_create, \
             mock.patch("platforms.windows.wgc._com_call") as mock_com:
            mock_create.return_value = 0xC0FFEE
            mock_com.return_value = mock.MagicMock(return_value=0)

            try:
                assert wgc.enable_event_mode() is True
                first_call_count = mock_create.call_count
                # Second call should refuse without re-registering.
                assert wgc.enable_event_mode() is False
                assert mock_create.call_count == first_call_count
            finally:
                wgc.disable_event_mode()

    def test_enable_event_mode_rolls_back_on_failure(self):
        """If add_FrameArrived fails, delegate is released and mode stays disabled."""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._initialized = True
        wgc._frame_pool = 0xDEADBEEF

        with mock.patch("platforms.windows.wgc.create_typed_event_handler_delegate") as mock_create, \
             mock.patch("platforms.windows.wgc._com_call") as mock_com, \
             mock.patch("platforms.windows.wgc.release_delegate") as mock_release:
            mock_create.return_value = 0xC0FFEE
            add_fn = mock.MagicMock(return_value=0x80004005)  # E_FAIL
            mock_com.return_value = add_fn

            result = wgc.enable_event_mode()
            assert result is False
            assert wgc._event_mode_enabled is False
            assert wgc._frame_arrived_delegate_ptr == 0
            # Delegate must be released since add_FrameArrived failed.
            mock_release.assert_called_once_with(0xC0FFEE)

    def test_disable_event_mode_unregisters_callback(self):
        """disable_event_mode should call remove_FrameArrived and release delegate."""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._initialized = True
        wgc._frame_pool = 0xDEADBEEF
        wgc._frame_arrived_delegate_ptr = 0xC0FFEE
        wgc._frame_arrived_token = 12345
        wgc._event_mode_enabled = True

        with mock.patch("platforms.windows.wgc._com_call") as mock_com, \
             mock.patch("platforms.windows.wgc.release_delegate") as mock_release:
            mock_com.return_value = mock.MagicMock(return_value=0)  # S_OK

            wgc.disable_event_mode()
            assert wgc._event_mode_enabled is False
            assert wgc._frame_arrived_delegate_ptr == 0
            assert wgc._frame_arrived_token == 0
            # remove_FrameArrived is at vtable index 9.
            com_indices = [call.args[1] for call in mock_com.call_args_list]
            assert 9 in com_indices
            mock_release.assert_called_once_with(0xC0FFEE)

    def test_disable_event_mode_when_not_enabled_is_noop(self):
        """disable_event_mode without enable should be a no-op."""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        # Should not raise
        wgc.disable_event_mode()
        assert wgc._event_mode_enabled is False

    def test_unregister_frame_arrived_idempotent(self):
        """_unregister_frame_arrived is safe to call when delegate is already cleared."""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._frame_arrived_delegate_ptr = 0  # already cleared
        wgc._frame_pool = 0xDEADBEEF
        # Should not raise or call any COM functions.
        with mock.patch("platforms.windows.wgc._com_call") as mock_com, \
             mock.patch("platforms.windows.wgc.release_delegate") as mock_release:
            wgc._unregister_frame_arrived()
            mock_com.assert_not_called()
            mock_release.assert_not_called()

    def test_wait_for_frame_without_event_mode_returns_true(self):
        """wait_for_frame should return True immediately when event mode is off."""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        assert wgc.wait_for_frame(timeout_sec=0.01) is True

    def test_wait_for_frame_with_event_mode(self):
        """wait_for_frame should return True when the event is set."""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._event_mode_enabled = True
        wgc._frame_arrived_event.set()
        assert wgc.wait_for_frame(timeout_sec=0.5) is True

    def test_wait_for_frame_timeout(self):
        """wait_for_frame should return False on timeout."""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._event_mode_enabled = True
        # Event is not set; should time out quickly
        assert wgc.wait_for_frame(timeout_sec=0.05) is False

    def test_capture_with_wait_event_when_disabled(self):
        """capture(wait_event=True) when event mode is off should not block."""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._initialized = True
        wgc._frame_pool = 0
        wgc._event_mode_enabled = False

        # Patch _com_call to make TryGetNextFrame return no frame.
        with mock.patch("platforms.windows.wgc._com_call") as mock_com:
            mock_fn = mock.MagicMock()
            mock_fn.return_value = (0, None)  # hr=0 but no frame_ptr -> returns None
            mock_com.return_value = mock_fn
            # Should not block even though wait_event=True
            result = wgc.capture(wait_event=True, event_timeout_sec=5.0)
            # Returns None because frame_ptr is None
            assert result is None

    def test_capture_in_callback_mode_returns_cached_frame(self):
        """In callback mode, capture() returns the cached frame without calling TryGetNextFrame."""
        import numpy as np
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._initialized = True
        wgc._frame_pool = 0xDEADBEEF
        wgc._event_mode_enabled = True
        wgc._frame_arrived_delegate_ptr = 0xC0FFEE  # callback mode active
        cached = np.zeros((4, 4, 3), dtype=np.uint8)
        wgc._cached_frame = cached

        with mock.patch("platforms.windows.wgc._com_call") as mock_com:
            # capture() must NOT call _com_call in callback mode.
            result = wgc.capture()
            assert result is cached
            mock_com.assert_not_called()

        # Cached frame is consumed (set to None) after retrieval.
        assert wgc._cached_frame is None

    def test_capture_in_callback_mode_with_wait_event(self):
        """capture(wait_event=True) in callback mode waits for event, then returns cached frame."""
        import numpy as np
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._initialized = True
        wgc._frame_pool = 0xDEADBEEF
        wgc._event_mode_enabled = True
        wgc._frame_arrived_delegate_ptr = 0xC0FFEE
        cached = np.zeros((2, 2, 3), dtype=np.uint8)

        # Pre-set the event so wait_for_frame returns immediately.
        wgc._frame_arrived_event.set()
        wgc._cached_frame = cached

        with mock.patch("platforms.windows.wgc._com_call") as mock_com:
            result = wgc.capture(wait_event=True, event_timeout_sec=1.0)
            assert result is cached
            mock_com.assert_not_called()

    def test_capture_in_callback_mode_returns_none_when_no_cache(self):
        """In callback mode with no cached frame, capture() returns None (no TryGetNextFrame)."""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._initialized = True
        wgc._frame_pool = 0xDEADBEEF
        wgc._event_mode_enabled = True
        wgc._frame_arrived_delegate_ptr = 0xC0FFEE
        wgc._cached_frame = None  # no frame cached

        with mock.patch("platforms.windows.wgc._com_call") as mock_com:
            result = wgc.capture()
            assert result is None
            # Must NOT call TryGetNextFrame in callback mode (would race with callback).
            mock_com.assert_not_called()

    def test_frame_arrived_callback_consumes_and_caches_frame(self):
        """_frame_arrived_callback calls TryGetNextFrame (vtable index 7), reads pixels, caches + signals."""
        import numpy as np
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._initialized = True
        wgc._frame_pool = 0xDEADBEEF
        wgc._event_mode_enabled = True
        wgc._frame_arrived_delegate_ptr = 0xC0FFEE

        fake_frame = np.ones((2, 2, 3), dtype=np.uint8) * 7
        call_indices = []

        def make_set_ptr_side_effect(ptr_value):
            """Return a side_effect that mutates the byref'd c_void_p and returns S_OK."""
            def side_effect(this, ptr_ref):
                # ctypes.byref(obj) returns a CArgObject whose _obj is the original.
                ptr_ref._obj.value = ptr_value
                return 0  # S_OK
            return side_effect

        call_count = [0]

        def fake_com_call(this, index, restype, *argtypes):
            call_indices.append(index)
            fn = mock.MagicMock()
            if index == 7:  # TryGetNextFrame OR get_Surface (both at index 7 on different objs)
                call_count[0] += 1
                if call_count[0] == 1:
                    # TryGetNextFrame: set frame ptr to 0xAA.
                    fn.side_effect = make_set_ptr_side_effect(0xAA)
                else:
                    # get_Surface: set surface ptr to 0xBB.
                    fn.side_effect = make_set_ptr_side_effect(0xBB)
            return fn

        with mock.patch("platforms.windows.wgc._com_call", side_effect=fake_com_call), \
             mock.patch("platforms.windows.wgc._com_release"), \
             mock.patch.object(wgc, "_read_pixels", return_value=fake_frame):
            wgc._frame_arrived_callback()

        # Verify TryGetNextFrame (index 7) was called.
        assert 7 in call_indices
        # Verify frame was cached.
        assert wgc._cached_frame is fake_frame
        # Verify event was signaled.
        assert wgc._frame_arrived_event.is_set()

    def test_frame_arrived_callback_swallows_exceptions(self):
        """_frame_arrived_callback must not raise — exceptions are logged and swallowed."""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._initialized = True
        wgc._frame_pool = 0xDEADBEEF
        wgc._event_mode_enabled = True
        wgc._frame_arrived_delegate_ptr = 0xC0FFEE

        with mock.patch("platforms.windows.wgc._com_call", side_effect=RuntimeError("boom")):
            # Should not raise.
            wgc._frame_arrived_callback()
        # Event was NOT set because the callback failed before caching.
        assert not wgc._frame_arrived_event.is_set()

    def test_frame_arrived_callback_skipped_when_session_closed(self):
        """If _session_closed is True, the callback is a no-op."""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._initialized = True
        wgc._frame_pool = 0xDEADBEEF
        wgc._event_mode_enabled = True
        wgc._frame_arrived_delegate_ptr = 0xC0FFEE
        wgc._session_closed = True

        with mock.patch("platforms.windows.wgc._com_call") as mock_com:
            wgc._frame_arrived_callback()
            mock_com.assert_not_called()

    def test_release_disables_event_mode(self):
        """release() should unregister the callback before freeing COM resources."""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._initialized = True
        wgc._frame_pool = 0xDEADBEEF
        wgc._frame_arrived_delegate_ptr = 0xC0FFEE
        wgc._frame_arrived_token = 42
        wgc._event_mode_enabled = True

        with mock.patch("platforms.windows.wgc._com_call") as mock_com, \
             mock.patch("platforms.windows.wgc._com_release"), \
             mock.patch("platforms.windows.wgc.release_delegate") as mock_del_release:
            # remove_FrameArrived returns S_OK; other COM releases return None.
            mock_com.return_value = mock.MagicMock(return_value=0)
            wgc.release()
            # Event mode must be disabled (callback unregistered + delegate released).
            assert wgc._event_mode_enabled is False
            assert wgc._frame_arrived_delegate_ptr == 0
            # Delegate must be released via release_delegate().
            mock_del_release.assert_called_once_with(0xC0FFEE)

    # ---- Vtable index verification (P2-1 bug fix) ----

    def test_vtable_index_tryget_next_frame_is_7(self):
        """capture() in sync mode must call TryGetNextFrame at vtable index 7 (not 8)."""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._initialized = True
        wgc._frame_pool = 0xDEADBEEF
        wgc._event_mode_enabled = False  # sync mode

        with mock.patch("platforms.windows.wgc._com_call") as mock_com, \
             mock.patch("platforms.windows.wgc._com_release"):
            mock_fn = mock.MagicMock(return_value=(0, None))
            mock_com.return_value = mock_fn
            wgc.capture()
            # First _com_call should be for TryGetNextFrame at index 7.
            first_call = mock_com.call_args_list[0]
            assert first_call.args[1] == 7

    def test_vtable_index_create_capture_session_is_10(self):
        """_init_session must call CreateCaptureSession at vtable index 10 (not 7)."""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._frame_pool = 0xDEADBEEF
        wgc._capture_item = 0xBEEFCAFE

        with mock.patch("platforms.windows.wgc._com_call") as mock_com:
            # First call: CreateCaptureSession -> returns S_OK + session ptr.
            # Second call: StartCapture -> returns S_OK.
            session_fn = mock.MagicMock(return_value=0)
            start_fn = mock.MagicMock(return_value=0)
            mock_com.side_effect = [session_fn, start_fn]

            wgc._init_session()

            # First _com_call should be for CreateCaptureSession at index 10.
            create_call = mock_com.call_args_list[0]
            assert create_call.args[1] == 10
            # Second _com_call should be for StartCapture at index 6.
            start_call = mock_com.call_args_list[1]
            assert start_call.args[1] == 6

    def test_vtable_index_add_frame_arrived_is_8(self):
        """_register_frame_arrived must call add_FrameArrived at vtable index 8."""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._frame_pool = 0xDEADBEEF

        with mock.patch("platforms.windows.wgc.create_typed_event_handler_delegate") as mock_create, \
             mock.patch("platforms.windows.wgc._com_call") as mock_com:
            mock_create.return_value = 0xC0FFEE
            mock_com.return_value = mock.MagicMock(return_value=0)  # S_OK

            wgc._register_frame_arrived()

            add_call = mock_com.call_args_list[0]
            assert add_call.args[1] == 8
            assert wgc._frame_arrived_delegate_ptr == 0xC0FFEE

    def test_vtable_index_remove_frame_arrived_is_9(self):
        """_unregister_frame_arrived must call remove_FrameArrived at vtable index 9."""
        from platforms.windows.wgc import Win32WGC

        wgc = Win32WGC()
        wgc._frame_pool = 0xDEADBEEF
        wgc._frame_arrived_delegate_ptr = 0xC0FFEE
        wgc._frame_arrived_token = 99

        with mock.patch("platforms.windows.wgc._com_call") as mock_com, \
             mock.patch("platforms.windows.wgc.release_delegate"):
            mock_com.return_value = mock.MagicMock(return_value=0)

            wgc._unregister_frame_arrived()

            remove_call = mock_com.call_args_list[0]
            assert remove_call.args[1] == 9


class TestFramePool:
    """FramePool 帧缓存池测试"""

    def test_add_and_get_latest(self):
        """验证添加和获取最新帧"""
        from platforms.windows.frame_pool import FramePool

        pool = FramePool(max_frames=3)
        frame1 = np.ones((10, 10, 3), dtype=np.uint8)
        frame2 = np.full((10, 10, 3), 128, dtype=np.uint8)  # 非全黑帧

        pool.add(frame1, time.time())
        pool.add(frame2, time.time())

        latest = pool.get_latest()
        assert latest is not None
        np.testing.assert_array_equal(latest, frame2)

    def test_get_by_timestamp(self):
        """验证按时间戳查找最接近的帧"""
        from platforms.windows.frame_pool import FramePool

        pool = FramePool(max_frames=5)
        base_ts = 1000.0
        pool.add(np.full((10, 10, 3), 1, dtype=np.uint8), base_ts)
        pool.add(np.full((10, 10, 3), 2, dtype=np.uint8), base_ts + 0.1)
        pool.add(np.full((10, 10, 3), 3, dtype=np.uint8), base_ts + 0.2)

        result = pool.get_by_timestamp(base_ts + 0.09)
        assert result is not None
        assert result[0, 0, 0] == 2

    def test_get_latest_empty(self):
        """验证空缓存获取最新帧返回 None"""
        from platforms.windows.frame_pool import FramePool

        pool = FramePool()
        result = pool.get_latest()
        assert result is None

    def test_get_by_timestamp_empty(self):
        """验证空缓存按时间戳查找返回 None"""
        from platforms.windows.frame_pool import FramePool

        pool = FramePool()
        result = pool.get_by_timestamp(123.0)
        assert result is None

    def test_max_frames_limit(self):
        """验证缓存帧数上限"""
        from platforms.windows.frame_pool import FramePool

        pool = FramePool(max_frames=3)
        for i in range(5):
            pool.add(np.full((5, 5, 3), i, dtype=np.uint8), float(i))

        assert pool.size == 3
        latest = pool.get_latest()
        assert latest[0, 0, 0] == 4

    def test_clear(self):
        """验证清空缓存"""
        from platforms.windows.frame_pool import FramePool

        pool = FramePool()
        pool.add(np.ones((5, 5, 3), dtype=np.uint8), time.time())
        pool.clear()
        assert pool.size == 0
        assert pool.get_latest() is None

    def test_properties(self):
        """验证属性访问"""
        from platforms.windows.frame_pool import FramePool

        pool = FramePool(max_frames=10)
        assert pool.max_frames == 10
        pool.add(np.ones((5, 5, 3), dtype=np.uint8), time.time())
        assert pool.size == 1

    def test_frame_data_independence(self):
        """验证返回的帧数据是副本，修改不影响缓存"""
        from platforms.windows.frame_pool import FramePool

        pool = FramePool()
        original = np.ones((5, 5, 3), dtype=np.uint8)
        pool.add(original, time.time())

        retrieved = pool.get_latest()
        retrieved[0, 0] = [0, 0, 0]

        cached = pool.get_latest()
        np.testing.assert_array_equal(cached, original)


class TestBenchmark:
    """benchmark 竞速测试结构验证"""

    def test_import_benchmark(self):
        """验证 benchmark 模块可导入"""
        from platforms.windows.benchmark import benchmark_capture_methods

        assert callable(benchmark_capture_methods)

    def test_measure_method_fallback(self):
        """验证测量函数在截图失败时返回 None"""
        from platforms.windows.benchmark import _measure_method

        class FailingCapture:
            def capture(self):
                return None

        result = _measure_method(FailingCapture(), 5)
        assert result is None

    def test_measure_method_success(self):
        """验证测量函数能正确计算平均延迟"""
        from platforms.windows.benchmark import _measure_method

        class FakeCapture:
            def capture(self):
                return np.zeros((10, 10, 3), dtype=np.uint8)

        result = _measure_method(FakeCapture(), 3)
        assert result is not None
        assert result > 0
