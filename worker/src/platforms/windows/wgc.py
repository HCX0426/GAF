"""WGC (Windows Graphics Capture) 高性能截图 — 通过 ctypes 调用 Win32 WGC API

支持 Windows 10 1903+ 系统，使用 Direct3D 11 + WinRT Graphics Capture 管线。

P2-1 事件驱动模式 (event-driven):
    WGC 原生支持 FrameArrived 事件回调。本模块通过纯 ctypes 构造一个
    TypedEventHandler<Direct3D11CaptureFramePool, IInspectable> COM delegate
    (see _com_delegate.py) 并调用 IDirect3D11CaptureFramePool::add_FrameArrived
    注册到 WinRT。WinRT 在帧到达时通过该 delegate 回调到 Python, 在回调中
    调用 TryGetNextFrame 消费该帧, 读取像素并缓存, 然后设置 frame_arrived_event.
    调用方通过 wait_for_frame() 等待事件, 通过 capture(wait_event=True) 取回
    缓存帧. 这避免了调用方忙等, 也避免了"轮询线程消费帧后丢弃"的 bug.

Vtable 索引 (IDirect3D11CaptureFramePool : IInspectable):
    0  QueryInterface          (IUnknown)
    1  AddRef                   (IUnknown)
    2  Release                  (IUnknown)
    3  GetIids                  (IInspectable)
    4  GetRuntimeClassName      (IInspectable)
    5  GetTrustLevel            (IInspectable)
    6  Recreate
    7  TryGetNextFrame
    8  add_FrameArrived
    9  remove_FrameArrived
    10 CreateCaptureSession
    11 get_DispatcherQueue
"""

import ctypes
import ctypes.wintypes
import logging
import threading
import uuid as _uuid

import numpy as np
from platforms.windows._com_delegate import (
    IID_FRAME_ARRIVED_HANDLER,
    create_typed_event_handler_delegate,
    release_delegate,
)

logger = logging.getLogger(__name__)

d3d11 = ctypes.windll.d3d11
dxgi = ctypes.windll.dxgi
combase = ctypes.windll.combase
user32 = ctypes.windll.user32

HRESULT = ctypes.c_long
S_OK = 0

D3D11_SDK_VERSION = 7
D3D_DRIVER_TYPE_HARDWARE = 1
D3D11_USAGE_STAGING = 3
D3D11_CPU_ACCESS_READ = 0x20000
D3D11_MAP_READ = 1
DXGI_FORMAT_B8G8R8A8_UNORM = 87
DXGI_MAP_READ = 1
RO_INIT_MULTITHREADED = 0

IID_IUnknown = _uuid.UUID("{00000000-0000-0000-C000-000000000046}")
IID_IDXGIDevice = _uuid.UUID("{54EC77FA-1377-44E6-8C32-88FD5F44C84C}")
IID_IDXGIResource = _uuid.UUID("{035F3AB4-482E-4E50-B41F-8A7F8BD8960B}")
IID_IDXGISurface = _uuid.UUID("{CAF8B8B1-513F-4357-8B26-509AE28C88DC}")
IID_ID3D11Device = _uuid.UUID("{DB6F6DDB-AC77-4E88-8253-819DF9BBF140}")
IID_ID3D11DeviceContext = _uuid.UUID("{C0BFA96C-E089-44FB-8EAF-26F8796190DA}")
IID_ID3D11Texture2D = _uuid.UUID("{6F15AAF2-D208-4E89-9AB4-489535D34F9C}")
IID_IGraphicsCaptureItemInterop = _uuid.UUID("{3628E81B-3C70-4C5C-8F20-8E9E4F08BF15}")
IID_IGraphicsCaptureItem = _uuid.UUID("{79C3F95B-31F7-4EC2-A464-632EF5D30760}")
IID_IDirect3D11CaptureFramePoolStatics = _uuid.UUID("{7B5A0C1E-6C3D-4E67-8D05-E0E61C6A32DC}")


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class D3D11_TEXTURE2D_DESC(ctypes.Structure):
    _fields_ = [
        ("Width", ctypes.c_uint),
        ("Height", ctypes.c_uint),
        ("MipLevels", ctypes.c_uint),
        ("ArraySize", ctypes.c_uint),
        ("Format", ctypes.c_uint),
        ("SampleCount", ctypes.c_uint),
        ("SampleQuality", ctypes.c_uint),
        ("Usage", ctypes.c_uint),
        ("BindFlags", ctypes.c_uint),
        ("CPUAccessFlags", ctypes.c_uint),
        ("MiscFlags", ctypes.c_uint),
    ]


class D3D11_MAPPED_SUBRESOURCE(ctypes.Structure):
    _fields_ = [
        ("pData", ctypes.c_void_p),
        ("RowPitch", ctypes.c_uint),
        ("DepthPitch", ctypes.c_uint),
    ]


class DXGI_MAPPED_RECT(ctypes.Structure):
    _fields_ = [
        ("Pitch", ctypes.c_uint),
        ("pBits", ctypes.c_void_p),
    ]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def _uuid_to_guid(u: _uuid.UUID) -> GUID:
    """将 Python UUID 转换为 COM GUID 结构"""
    g = GUID()
    g.Data1 = u.time_low
    g.Data2 = u.time_mid
    g.Data3 = u.time_hi_version
    g.Data4 = (ctypes.c_ubyte * 8)(*list(u.int.to_bytes(16, "big")[8:]))
    return g


def _com_call(this: int, vtable_index: int, restype, *argtypes):
    """获取 COM 接口 vtable 方法并返回可调用函数包装

    Args:
        this: COM 接口指针
        vtable_index: 方法在 vtable 中的索引
        restype: 返回值类型
        argtypes: 参数类型（不含 this 指针）

    Returns:
        可调用的 WINFUNCTYPE 实例
    """
    vtable = ctypes.cast(this, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))
    func_type = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    func_ptr = ctypes.cast(vtable[0][vtable_index], ctypes.POINTER(func_type))
    return func_ptr.contents


def _com_release(ptr) -> None:
    """安全释放 COM 对象"""
    if ptr:
        try:
            release_fn = _com_call(ptr, 2, ctypes.c_ulong)
            release_fn(ptr)
        except Exception:
            pass


class Win32WGC:
    """通过 ctypes 调用 Win32 WGC API 实现高性能窗口截图

    使用 Direct3D 11 + WinRT Graphics Capture 管线，
    支持 Windows 10 1903+，相比 GDI/BitBlt 具有更高的帧率和更低的延迟。
    """

    # Default polling rate kept for API backward compat (unused in callback mode).
    EVENT_POLL_INTERVAL_SEC = 1.0 / 60.0

    def __init__(self):
        self._hwnd: int = 0
        self._initialized: bool = False
        self._d3d_device = None
        self._d3d_context = None
        self._capture_item = None
        self._frame_pool = None
        self._session = None
        self._staging_texture = None
        self._width: int = 0
        self._height: int = 0
        self._ro_initialized: bool = False
        # P2-1 event-driven mode infrastructure (real COM FrameArrived callback).
        self._frame_arrived_event: threading.Event = threading.Event()
        self._event_mode_enabled: bool = False
        # COM delegate registration state.
        self._frame_arrived_delegate_ptr: int = 0
        # EventRegistrationToken (an int64 returned by add_FrameArrived).
        self._frame_arrived_token: int = 0
        # Latest frame consumed by the callback, awaiting pickup by capture().
        self._cached_frame: np.ndarray | None = None
        self._cached_frame_lock: threading.Lock = threading.Lock()
        # Sentinel set when the WGC session has been closed by the OS.
        self._session_closed: bool = False

    def initialize(self, hwnd: int) -> bool:
        """初始化 WGC 捕获会话

        Args:
            hwnd: 目标窗口句柄

        Returns:
            初始化成功返回 True，失败返回 False
        """
        if self._initialized:
            logger.debug("WGC 已初始化，跳过重复初始化")
            return True

        self._hwnd = hwnd

        try:
            self._init_winrt()
            self._init_d3d11()
            self._init_capture_item()
            self._init_frame_pool()
            self._init_staging_texture()
            self._init_session()
            self._initialized = True
            logger.info("WGC 初始化成功，hwnd=%d, 尺寸=%dx%d", hwnd, self._width, self._height)
            return True
        except Exception as exc:
            logger.error("WGC 初始化失败: %s", exc)
            self.release()
            return False

    def capture(self, wait_event: bool = False, event_timeout_sec: float = 1.0) -> np.ndarray | None:
        """截取一帧画面

        Args:
            wait_event: If True and event mode is enabled, wait for the
                frame_arrived_event before retrieving the cached frame.
                In callback mode the frame is consumed by the COM callback
                and cached; this method returns that cached frame without
                calling TryGetNextFrame again. Default False (synchronous
                mode, calls TryGetNextFrame directly).
            event_timeout_sec: Max seconds to wait for the event. Ignored
                when wait_event is False or event mode is disabled.

        Returns:
            BGR 格式的 numpy 数组，失败返回 None
        """
        if not self._initialized:
            logger.error("WGC 未初始化")
            return None

        # In callback mode, the COM callback consumes frames via
        # TryGetNextFrame and caches them. We must NOT call TryGetNextFrame
        # here — that would race with the callback and consume a frame the
        # callback was supposed to get.
        if self._event_mode_enabled and self._frame_arrived_delegate_ptr:
            if wait_event:
                self._frame_arrived_event.wait(timeout=event_timeout_sec)
                self._frame_arrived_event.clear()
            with self._cached_frame_lock:
                frame = self._cached_frame
                self._cached_frame = None
                return frame

        # Synchronous mode (event mode disabled, or wait_event=False without
        # a registered callback): optionally wait for the event, then call
        # TryGetNextFrame directly.
        if wait_event and self._event_mode_enabled:
            self._frame_arrived_event.wait(timeout=event_timeout_sec)
            self._frame_arrived_event.clear()

        try:
            frame_ptr = ctypes.c_void_p()

            # IDirect3D11CaptureFramePool::TryGetNextFrame — vtable index 7
            tryget_fn = _com_call(self._frame_pool, 7, HRESULT, ctypes.POINTER(ctypes.c_void_p))
            hr = tryget_fn(self._frame_pool, ctypes.byref(frame_ptr))
            if hr != S_OK or not frame_ptr:
                return None

            frame = frame_ptr.value
            try:
                surface_ptr = ctypes.c_void_p()

                # IDirect3D11CaptureFrame::get_Surface — vtable index 7
                get_surface_fn = _com_call(frame, 7, HRESULT, ctypes.POINTER(ctypes.c_void_p))
                get_surface_fn(frame, ctypes.byref(surface_ptr))
                surface = surface_ptr.value
                if not surface:
                    return None

                try:
                    return self._read_pixels(surface)
                finally:
                    _com_release(surface)
            finally:
                _com_release(frame)
        except Exception as exc:
            logger.debug("WGC 截图异常: %s", exc)
            return None

    # ---- P2-1 event-driven mode (real COM FrameArrived callback) ----

    def enable_event_mode(self, poll_interval_sec: float | None = None) -> bool:
        """Enable event-driven frame arrival notifications.

        Builds a TypedEventHandler<Direct3D11CaptureFramePool, IInspectable>
        COM delegate (see _com_delegate.py) and registers it on the frame
        pool via IDirect3D11CaptureFramePool::add_FrameArrived. WinRT then
        calls back into Python on a thread-pool thread whenever a frame
        arrives; the callback consumes the frame via TryGetNextFrame, reads
        pixels, caches the result, and signals frame_arrived_event.

        Callers can use wait_for_frame(timeout) to block until the next
        frame arrives, or capture(wait_event=True) to retrieve the cached
        frame directly.

        Args:
            poll_interval_sec: Unused (kept for API backward compat). The
                real COM callback is event-driven, not polled.

        Returns:
            True if event mode was enabled, False if already enabled,
            WGC not initialized, or COM callback registration failed.
        """
        if not self._initialized:
            logger.warning("Cannot enable event mode: WGC not initialized")
            return False
        if self._event_mode_enabled:
            logger.debug("Event mode already enabled")
            return False
        if not self._frame_pool:
            logger.warning("Cannot enable event mode: no frame pool")
            return False

        self._frame_arrived_event.clear()
        self._session_closed = False
        try:
            self._register_frame_arrived()
        except Exception as exc:
            logger.error("Failed to register FrameArrived callback: %s", exc)
            # Clean up any partial state.
            self._unregister_frame_arrived()
            return False

        self._event_mode_enabled = True
        logger.info("WGC event mode enabled (real COM FrameArrived callback)")
        return True

    def disable_event_mode(self) -> None:
        """Disable event-driven mode and unregister the COM callback."""
        if not self._event_mode_enabled:
            return
        self._unregister_frame_arrived()
        self._event_mode_enabled = False
        with self._cached_frame_lock:
            self._cached_frame = None
        self._frame_arrived_event.clear()
        logger.debug("WGC event mode disabled")

    def _register_frame_arrived(self) -> None:
        """Build a COM delegate and call add_FrameArrived on the frame pool.

        Stores the delegate pointer (for lifetime control via _refmap) and
        the EventRegistrationToken (for remove_FrameArrived on teardown).
        """
        delegate_ptr = create_typed_event_handler_delegate(
            IID_FRAME_ARRIVED_HANDLER,
            self._frame_arrived_callback,
        )
        if not delegate_ptr:
            raise RuntimeError("create_typed_event_handler_delegate returned null")

        # IDirect3D11CaptureFramePool::add_FrameArrived — vtable index 8.
        # Signature: HRESULT add_FrameArrived(
        #     ITypedEventHandler<FramePool, IInspectable>* handler,
        #     EventRegistrationToken* token)
        token = ctypes.c_int64(0)
        add_fn = _com_call(
            self._frame_pool, 8, HRESULT,
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_int64),
        )
        hr = add_fn(self._frame_pool, delegate_ptr, ctypes.byref(token))
        if hr != S_OK:
            release_delegate(delegate_ptr)
            raise RuntimeError(f"add_FrameArrived failed: 0x{hr & 0xFFFFFFFF:08X}")

        self._frame_arrived_delegate_ptr = delegate_ptr
        self._frame_arrived_token = int(token.value)
        logger.debug(
            "FrameArrived delegate registered: ptr=%#x token=%d",
            delegate_ptr, self._frame_arrived_token,
        )

    def _unregister_frame_arrived(self) -> None:
        """Call remove_FrameArrived and release the delegate.

        Safe to call multiple times — tracks state via _frame_arrived_delegate_ptr.
        """
        if self._frame_arrived_delegate_ptr and self._frame_pool:
            try:
                # IDirect3D11CaptureFramePool::remove_FrameArrived — vtable index 9.
                # Signature: HRESULT remove_FrameArrived(EventRegistrationToken token)
                remove_fn = _com_call(
                    self._frame_pool, 9, HRESULT, ctypes.c_int64,
                )
                hr = remove_fn(self._frame_pool, ctypes.c_int64(self._frame_arrived_token))
                if hr != S_OK:
                    logger.debug(
                        "remove_FrameArrived returned 0x%08X (token=%d)",
                        hr & 0xFFFFFFFF, self._frame_arrived_token,
                    )
            except Exception as exc:
                logger.debug("remove_FrameArrived exception: %s", exc)

        if self._frame_arrived_delegate_ptr:
            release_delegate(self._frame_arrived_delegate_ptr)
            self._frame_arrived_delegate_ptr = 0
        self._frame_arrived_token = 0

    def _frame_arrived_callback(self) -> None:
        """COM callback invoked by WinRT when a frame arrives.

        Consumes the frame via TryGetNextFrame, reads pixels, caches the
        result under _cached_frame_lock, and signals _frame_arrived_event.

        Runs on a WinRT thread-pool thread — must be fast, exception-safe,
        and never block on Python locks held by the main thread.
        """
        if self._session_closed:
            return
        try:
            frame_ptr = ctypes.c_void_p()
            # IDirect3D11CaptureFramePool::TryGetNextFrame — vtable index 7.
            tryget_fn = _com_call(
                self._frame_pool, 7, HRESULT,
                ctypes.POINTER(ctypes.c_void_p),
            )
            hr = tryget_fn(self._frame_pool, ctypes.byref(frame_ptr))
            if hr != S_OK or not frame_ptr:
                return

            frame = frame_ptr.value
            try:
                surface_ptr = ctypes.c_void_p()
                # IDirect3D11CaptureFrame::get_Surface — vtable index 7.
                get_surface_fn = _com_call(
                    frame, 7, HRESULT, ctypes.POINTER(ctypes.c_void_p),
                )
                get_surface_fn(frame, ctypes.byref(surface_ptr))
                surface = surface_ptr.value
                if not surface:
                    return
                try:
                    pixels = self._read_pixels(surface)
                finally:
                    _com_release(surface)
            finally:
                _com_release(frame)

            if pixels is not None:
                with self._cached_frame_lock:
                    self._cached_frame = pixels
                self._frame_arrived_event.set()
        except Exception as exc:
            logger.debug("FrameArrived callback exception: %s", exc)

    def wait_for_frame(self, timeout_sec: float = 1.0) -> bool:
        """Block until a frame is available or timeout expires.

        Args:
            timeout_sec: Max seconds to wait. 0 = non-blocking check.

        Returns:
            True if the frame_arrived_event was set, False on timeout.
        """
        if not self._event_mode_enabled:
            # Without event mode, fall back to immediate "frame available"
            # assumption so callers can use the same API in both modes.
            return True
        return self._frame_arrived_event.wait(timeout=timeout_sec)

    def release(self) -> None:
        """释放所有 WGC 资源"""
        # Unregister the FrameArrived callback and release the delegate first
        # to avoid WinRT calling back into Python after COM objects are freed.
        self.disable_event_mode()
        self._initialized = False

        if self._session:
            _com_release(self._session)
            self._session = None
        if self._frame_pool:
            _com_release(self._frame_pool)
            self._frame_pool = None
        if self._capture_item:
            _com_release(self._capture_item)
            self._capture_item = None
        if self._staging_texture:
            _com_release(self._staging_texture)
            self._staging_texture = None
        if self._d3d_context:
            _com_release(self._d3d_context)
            self._d3d_context = None
        if self._d3d_device:
            _com_release(self._d3d_device)
            self._d3d_device = None
        if self._ro_initialized:
            combase.RoUninitialize()
            self._ro_initialized = False

        self._hwnd = 0
        logger.debug("WGC 资源已释放")

    # ---- 内部初始化 ----

    def _init_winrt(self) -> None:
        """初始化 WinRT COM 运行时"""
        hr = combase.RoInitialize(RO_INIT_MULTITHREADED)
        if hr != S_OK and hr != 1:  # 1 = S_FALSE 表示已初始化
            raise RuntimeError(f"RoInitialize 失败: 0x{hr & 0xFFFFFFFF:08X}")
        self._ro_initialized = True

    def _init_d3d11(self) -> None:
        """创建 D3D11 设备和上下文"""
        device_ptr = ctypes.c_void_p()
        context_ptr = ctypes.c_void_p()

        create_device = d3d11.D3D11CreateDevice
        create_device.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.POINTER(ctypes.c_int),
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        create_device.restype = HRESULT

        feature_level = ctypes.c_int(0)
        hr = create_device(
            None, D3D_DRIVER_TYPE_HARDWARE, None, 0,
            None, 0, D3D11_SDK_VERSION,
            ctypes.byref(device_ptr), ctypes.byref(feature_level), ctypes.byref(context_ptr),
        )

        if hr != S_OK:
            raise RuntimeError(f"D3D11CreateDevice 失败: 0x{hr & 0xFFFFFFFF:08X}")

        self._d3d_device = device_ptr.value
        self._d3d_context = context_ptr.value
        logger.debug("D3D11 设备创建成功，功能级别=%d", feature_level.value)

    def _init_capture_item(self) -> None:
        """从窗口句柄创建 WGC GraphicsCaptureItem"""
        hstring = ctypes.c_void_p()
        interop_ptr = ctypes.c_void_p()
        item_ptr = ctypes.c_void_p()

        try:
            class_name = "Windows.Graphics.Capture.GraphicsCaptureItem"
            hr = combase.WindowsCreateString(class_name, len(class_name), ctypes.byref(hstring))
            if hr != S_OK:
                raise RuntimeError(f"WindowsCreateString 失败: 0x{hr & 0xFFFFFFFF:08X}")

            iid_interop = _uuid_to_guid(IID_IGraphicsCaptureItemInterop)
            hr = combase.RoGetActivationFactory(hstring, ctypes.byref(iid_interop), ctypes.byref(interop_ptr))
            if hr != S_OK:
                raise RuntimeError(f"RoGetActivationFactory(interop) 失败: 0x{hr & 0xFFFFFFFF:08X}")

            # IGraphicsCaptureItemInterop::CreateForWindow — vtable index 3
            capture_iid = _uuid_to_guid(IID_IGraphicsCaptureItem)
            create_fn = _com_call(
                interop_ptr.value, 3, HRESULT,
                ctypes.wintypes.HWND, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p),
            )
            hr = create_fn(interop_ptr.value, ctypes.wintypes.HWND(self._hwnd), ctypes.byref(capture_iid), ctypes.byref(item_ptr))
            if hr != S_OK:
                raise RuntimeError(f"CreateForWindow 失败: 0x{hr & 0xFFFFFFFF:08X}")

            self._capture_item = item_ptr.value

            rect = RECT()
            user32.GetWindowRect(ctypes.wintypes.HWND(self._hwnd), ctypes.byref(rect))
            self._width = rect.right - rect.left
            self._height = rect.bottom - rect.top
            if self._width <= 0 or self._height <= 0:
                raise RuntimeError(f"窗口尺寸无效: {self._width}x{self._height}")

        finally:
            if hstring:
                combase.WindowsDeleteString(hstring)
            if interop_ptr:
                _com_release(interop_ptr.value)

    def _init_frame_pool(self) -> None:
        """创建 WGC 帧池"""
        hstring = ctypes.c_void_p()
        factory_ptr = ctypes.c_void_p()
        pool_ptr = ctypes.c_void_p()

        try:
            class_name = "Windows.Graphics.Capture.Direct3D11CaptureFramePool"
            hr = combase.WindowsCreateString(class_name, len(class_name), ctypes.byref(hstring))
            if hr != S_OK:
                raise RuntimeError(f"WindowsCreateString(pool) 失败: 0x{hr & 0xFFFFFFFF:08X}")

            iid_statics = _uuid_to_guid(IID_IDirect3D11CaptureFramePoolStatics)
            hr = combase.RoGetActivationFactory(hstring, ctypes.byref(iid_statics), ctypes.byref(factory_ptr))
            if hr != S_OK:
                raise RuntimeError(f"RoGetActivationFactory(pool) 失败: 0x{hr & 0xFFFFFFFF:08X}")

            # IDirect3D11CaptureFramePoolStatics::CreateFreeThreaded — vtable index 7
            create_fn = _com_call(
                factory_ptr.value, 7, HRESULT,
                ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
            )
            hr = create_fn(factory_ptr.value, self._d3d_device, self._capture_item, ctypes.byref(pool_ptr))
            if hr != S_OK:
                raise RuntimeError(f"CreateFreeThreaded 失败: 0x{hr & 0xFFFFFFFF:08X}")

            self._frame_pool = pool_ptr.value

        finally:
            if hstring:
                combase.WindowsDeleteString(hstring)
            if factory_ptr:
                _com_release(factory_ptr.value)

    def _init_staging_texture(self) -> None:
        """创建 CPU 可读的 staging 纹理"""
        desc = D3D11_TEXTURE2D_DESC()
        desc.Width = self._width
        desc.Height = self._height
        desc.MipLevels = 1
        desc.ArraySize = 1
        desc.Format = DXGI_FORMAT_B8G8R8A8_UNORM
        desc.SampleCount = 1
        desc.SampleQuality = 0
        desc.Usage = D3D11_USAGE_STAGING
        desc.BindFlags = 0
        desc.CPUAccessFlags = D3D11_CPU_ACCESS_READ
        desc.MiscFlags = 0

        tex_ptr = ctypes.c_void_p()

        # ID3D11Device::CreateTexture2D — vtable index 5
        create_fn = _com_call(
            self._d3d_device, 5, HRESULT,
            ctypes.POINTER(D3D11_TEXTURE2D_DESC), ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        )
        hr = create_fn(self._d3d_device, ctypes.byref(desc), None, ctypes.byref(tex_ptr))
        if hr != S_OK:
            raise RuntimeError(f"CreateTexture2D(staging) 失败: 0x{hr & 0xFFFFFFFF:08X}")

        self._staging_texture = tex_ptr.value

    def _init_session(self) -> None:
        """创建并启动 WGC 捕获会话"""
        session_ptr = ctypes.c_void_p()

        # IDirect3D11CaptureFramePool::CreateCaptureSession — vtable index 10.
        # (Pool inherits IUnknown 0-2 + IInspectable 3-5, then Recreate=6,
        # TryGetNextFrame=7, add_FrameArrived=8, remove_FrameArrived=9,
        # CreateCaptureSession=10, get_DispatcherQueue=11.)
        create_fn = _com_call(
            self._frame_pool, 10, HRESULT,
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        )
        hr = create_fn(self._frame_pool, self._capture_item, ctypes.byref(session_ptr))
        if hr != S_OK:
            raise RuntimeError(f"CreateCaptureSession 失败: 0x{hr & 0xFFFFFFFF:08X}")

        self._session = session_ptr.value

        # IGraphicsCaptureSession::StartCapture — vtable index 6
        start_fn = _com_call(self._session, 6, HRESULT)
        hr = start_fn(self._session)
        if hr != S_OK:
            raise RuntimeError(f"StartCapture 失败: 0x{hr & 0xFFFFFFFF:08X}")

        logger.debug("WGC 捕获会话已启动")

    # ---- 内部像素读取 ----

    def _read_pixels(self, surface_ptr: int) -> np.ndarray | None:
        """从捕获帧的 D3D 表面读取像素数据

        先尝试 DXGISurface::Map 快速路径，失败则走 CopyResource + staging 路径。

        Args:
            surface_ptr: IDirect3DSurface 指针

        Returns:
            BGR 格式的 numpy 数组
        """
        result = self._read_pixels_dxgi_map(surface_ptr)
        if result is not None:
            return result
        return self._read_pixels_staging(surface_ptr)

    def _read_pixels_dxgi_map(self, surface_ptr: int) -> np.ndarray | None:
        """通过 DXGISurface::Map 快速读取像素"""
        dxgi_surface_ptr = ctypes.c_void_p()
        dxgi_iid = _uuid_to_guid(IID_IDXGISurface)

        qi_fn = _com_call(surface_ptr, 0, HRESULT, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
        hr = qi_fn(surface_ptr, ctypes.byref(dxgi_iid), ctypes.byref(dxgi_surface_ptr))
        if hr != S_OK or not dxgi_surface_ptr:
            return None

        try:
            mapped = DXGI_MAPPED_RECT()

            # IDXGISurface::Map — vtable index 8
            map_fn = _com_call(dxgi_surface_ptr.value, 8, HRESULT, ctypes.POINTER(DXGI_MAPPED_RECT), ctypes.c_uint)
            hr = map_fn(dxgi_surface_ptr.value, ctypes.byref(mapped), DXGI_MAP_READ)
            if hr != S_OK:
                return None

            try:
                buf_size = mapped.Pitch * self._height
                buf = ctypes.create_string_buffer(buf_size)
                ctypes.memmove(buf, mapped.pBits, buf_size)

                row_width = mapped.Pitch // 4
                img = np.frombuffer(buf, dtype=np.uint8).reshape((self._height, row_width, 4))
                img = img[:, :self._width, :]
                return img[:, :, :3].copy()
            finally:
                # IDXGISurface::Unmap — vtable index 9
                unmap_fn = _com_call(dxgi_surface_ptr.value, 9, HRESULT)
                unmap_fn(dxgi_surface_ptr.value)
        finally:
            _com_release(dxgi_surface_ptr.value)

    def _read_pixels_staging(self, surface_ptr: int) -> np.ndarray | None:
        """通过 CopyResource + staging 纹理读取像素（兼容路径）"""
        texture_ptr = ctypes.c_void_p()
        tex_iid = _uuid_to_guid(IID_ID3D11Texture2D)

        qi_fn = _com_call(surface_ptr, 0, HRESULT, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
        hr = qi_fn(surface_ptr, ctypes.byref(tex_iid), ctypes.byref(texture_ptr))
        if hr != S_OK or not texture_ptr:
            return None

        try:
            # ID3D11DeviceContext::CopyResource — vtable index 33
            copy_fn = _com_call(self._d3d_context, 33, None, ctypes.c_void_p, ctypes.c_void_p)
            copy_fn(self._d3d_context, self._staging_texture, texture_ptr.value)

            # ID3D11DeviceContext::Map — vtable index 14
            mapped = D3D11_MAPPED_SUBRESOURCE()
            map_fn = _com_call(
                self._d3d_context, 14, HRESULT,
                ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_uint,
                ctypes.POINTER(D3D11_MAPPED_SUBRESOURCE),
            )
            hr = map_fn(self._d3d_context, self._staging_texture, 0, D3D11_MAP_READ, 0, ctypes.byref(mapped))
            if hr != S_OK:
                return None

            try:
                buf_size = mapped.RowPitch * self._height
                buf = ctypes.create_string_buffer(buf_size)
                ctypes.memmove(buf, mapped.pData, buf_size)

                row_width = mapped.RowPitch // 4
                img = np.frombuffer(buf, dtype=np.uint8).reshape((self._height, row_width, 4))
                img = img[:, :self._width, :]
                return img[:, :, :3].copy()
            finally:
                # ID3D11DeviceContext::Unmap — vtable index 15
                unmap_fn = _com_call(self._d3d_context, 15, None, ctypes.c_void_p, ctypes.c_uint)
                unmap_fn(self._d3d_context, self._staging_texture, 0)
        finally:
            _com_release(texture_ptr.value)
