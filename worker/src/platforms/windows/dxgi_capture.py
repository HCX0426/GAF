"""DXGI Desktop Duplication Screenshot Capture — Pure ctypes COM Implementation

Captures desktop frames using the Windows Desktop Duplication API (IDXGIOutputDuplication).
This is a high-performance GPU-based screen capture method available on Windows 8+.

Reference sources:
    - ok-script's DXGICapture class (d3dshot-based approach)
    - MaaFramework's DirectX screenshot implementation
    - Microsoft Desktop Duplication API documentation:
      https://learn.microsoft.com/en-us/windows/win32/direct3ddxgi/desktop-dup-api

Implementation notes:
    - Pure ctypes, no third-party COM libraries (comtypes/d3dshot not required)
    - Uses D3D11 for texture staging and CPU-readable pixel access
    - Returns BGR numpy array consistent with existing screenshot.py format
    - Full COM lifecycle management (CoInitialize/CoUninitialize)
    - Frame timeout handling via AcquireNextFrame with configurable timeout
    - DXGI_OUTPUT_DESC for output monitor information retrieval
"""

import contextlib
import ctypes
import ctypes.wintypes
import logging
import time
import uuid as _uuid

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HRESULT = ctypes.c_long
S_OK = 0
S_FALSE = 1
E_ACCESSDENIED = ctypes.c_long(0x80070005).value
DXGI_ERROR_WAIT_TIMEOUT = ctypes.c_long(0x887A0027).value
DXGI_ERROR_ACCESS_LOST = ctypes.c_long(0x887A0026).value
DXGI_ERROR_ALREADY_EXIST = ctypes.c_long(0x887A0015).value
# DXGI_ERROR_INVALID_CALL — returned by AcquireNextFrame when the previous
# frame was not released. On AMD Radeon 610M, ReleaseFrame (vtable[9]) crashes
# inside the driver, so the frame is never released. We work around this by
# recreating the OutputDuplication object (see _recreate_output_duplication).
DXGI_ERROR_INVALID_CALL = ctypes.c_long(0x887A0001).value

COINIT_MULTITHREADED = 0
COINIT_APARTMENTTHREADED = 0x2

D3D11_SDK_VERSION = 7
D3D_DRIVER_TYPE_HARDWARE = 1
D3D11_USAGE_DEFAULT = 0
D3D11_USAGE_STAGING = 3
D3D11_CPU_ACCESS_READ = 0x20000
D3D11_BIND_RENDER_TARGET = 0x20
D3D11_MAP_READ = 1
D3D11_RESOURCE_MISC_GDI_COMPATIBLE = 0x20

DXGI_FORMAT_B8G8R8A8_UNORM = 87
DXGI_MODE_SCALING_UNSPECIFIED = 0
DXGI_MODE_SCANLINE_ORDER_UNSPECIFIED = 0
DXGI_MODE_ROTATION_IDENTITY = 1

DXGI_MAP_READ = 1

DEFAULT_FRAME_TIMEOUT_MS = 1000

# ---------------------------------------------------------------------------
# GUID definitions for COM interfaces
# ---------------------------------------------------------------------------

IID_IUnknown = _uuid.UUID("{00000000-0000-0000-C000-000000000046}")
IID_ID3D11Device = _uuid.UUID("{DB6F6DDB-AC77-4E88-8253-819DF9BBF140}")
IID_ID3D11DeviceContext = _uuid.UUID("{C0BFA96C-E089-44FB-8EAF-26F8796190DA}")
IID_ID3D11Texture2D = _uuid.UUID("{6F15AAF2-D208-4E89-9AB4-489535D34F9C}")
IID_IDXGIObject = _uuid.UUID("{54EC77FA-1377-44E6-8C32-88FD5F44C84C}")
IID_IDXGIDevice = _uuid.UUID("{54EC77FA-1377-44E6-8C32-88FD5F44C84C}")
IID_IDXGIAdapter = _uuid.UUID("{2411E733-1AC1-4F93-BB38-61C280C49694}")
IID_IDXGIOutput = _uuid.UUID("{AE02EFB9-BC4C-447B-A64A-C06CF5F066D0}")
# IDXGIOutput1 : IDXGIOutput — required for DuplicateOutput (Windows 8+).
# DuplicateOutput is on IDXGIOutput1 (vtable[22]), NOT on IDXGIOutput.
IID_IDXGIOutput1 = _uuid.UUID("{00CDDEA8-939B-4D83-AA37-9F2404224539}")
IID_IDXGIOutputDuplication = _uuid.UUID("{191CFAC3-A341-470D-B26E-A864F428319C}")
IID_IDXGIResource = _uuid.UUID("{035F3AB4-482E-4E50-B41F-8A7F8BD8960B}")
IID_IDXGISurface = _uuid.UUID("{CAF8B8B1-513F-4357-8B26-509AE28C88DC}")


def _uuid_to_guid(u: _uuid.UUID) -> bytes:
    """Convert a UUID object to the raw 16-byte GUID representation used by COM"""
    return bytes(u.bytes_le)


# ---------------------------------------------------------------------------
# Helper functions for COM vtable method calls
# ---------------------------------------------------------------------------

def _com_call(vtable_idx: int, restype, *argtypes):
    """Create a COM vtable method callable with the given signature.

    Returns a closure that, when called with (this_ptr, *method_args), looks up
    the vtable entry at vtable_idx and invokes the COM method on this_ptr.

    This fixes the previous broken implementation which ignored vtable_idx and
    returned a bare WINFUNCTYPE prototype class — causing the calling code to
    treat the COM object pointer as a function address, which overflowed
    c_long on 64-bit Python ("Python int too large to convert to C long").

    The correct vtable indexing pattern reads the vtable pointer from the first
    pointer-sized field of the COM object, then reads the function pointer at
    vtable + vtable_idx * sizeof(void*). This avoids the broken
    `ctypes.cast(addr, POINTER(func_type)).contents` pattern (which tries to
    read a WINFUNCTYPE structure from machine code bytes at the function
    address). Instead, `proto(func_addr)` creates a proper callable instance
    bound to the function address.

    Args:
        vtable_idx: Zero-based index into the interface vtable
        restype: Return type of the method
        *argtypes: Parameter types for the method (NOT including 'this')

    Returns:
        A callable _invoke(this_ptr, *args) that performs the vtable lookup
        and COM method call. The first argument is the COM interface pointer
        ('this'); remaining arguments are forwarded to the method.
    """
    proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    ptr_size = ctypes.sizeof(ctypes.c_void_p)

    def _invoke(this_ptr, *args):
        # Read vtable pointer (first pointer-sized field at this_ptr)
        vtable_addr = ctypes.cast(this_ptr, ctypes.POINTER(ctypes.c_void_p))[0]
        # Read function pointer at vtable[vtable_idx]
        func_addr = ctypes.cast(
            vtable_addr + vtable_idx * ptr_size,
            ctypes.POINTER(ctypes.c_void_p),
        )[0]
        # Create WINFUNCTYPE instance bound to func_addr and call
        func = proto(func_addr)
        return func(this_ptr, *args)

    return _invoke


def _com_release(ptr: int) -> None:
    """Release a COM interface pointer (calls IUnknown::Release)

    Args:
        ptr: Raw pointer to a COM interface instance
    """
    if not ptr:
        return
    try:
        release_fn = _com_call(2, ctypes.c_uint)
        release_fn(ptr)
    except Exception:
        pass


def _create_guid_struct():
    """Create a GUID structure for COM interface identification"""
    class _GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong),
            ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort),
            ("Data4", ctypes.c_ubyte * 8),
        ]
    return _GUID


_GUID = _create_guid_struct()


def _fill_guid(guid_bytes: bytes) -> _GUID:
    """Fill a GUID structure from raw bytes"""
    g = _GUID()
    ctypes.memmove(ctypes.byref(g), guid_bytes, ctypes.sizeof(_GUID))
    return g


# ---------------------------------------------------------------------------
# Structure definitions for D3D11 and DXGI APIs
# ---------------------------------------------------------------------------

class D3D11_TEXTURE2D_DESC(ctypes.Structure):
    """Describes a 2D texture resource for D3D11 device creation"""
    _fields_ = [
        ("Width", ctypes.c_uint),
        ("Height", ctypes.c_uint),
        ("MipLevels", ctypes.c_uint),
        ("ArraySize", ctypes.c_uint),
        ("Format", ctypes.c_int),
        ("SampleDesc_Count", ctypes.c_uint),
        ("SampleDesc_Quality", ctypes.c_uint),
        ("Usage", ctypes.c_uint),
        ("BindFlags", ctypes.c_uint),
        ("CPUAccessFlags", ctypes.c_uint),
        ("MiscFlags", ctypes.c_uint),
    ]


class D3D11_MAPPED_SUBRESOURCE(ctypes.Structure):
    """Represents mapped subresource data from ID3D11DeviceContext::Map"""
    _fields_ = [
        ("pData", ctypes.c_void_p),
        ("RowPitch", ctypes.c_uint),
        ("DepthPitch", ctypes.c_uint),
    ]


class DXGI_MAPPED_RECT(ctypes.Structure):
    """Represents mapped surface data from IDXGISurface::Map"""
    _fields_ = [
        ("Pitch", ctypes.c_uint),
        ("pBits", ctypes.c_void_p),
    ]


class DXGI_MODE_DESC(ctypes.Structure):
    """Describes display mode properties for a DXGI output"""
    _fields_ = [
        ("Width", ctypes.c_uint),
        ("Height", ctypes.c_uint),
        ("RefreshRate_Numerator", ctypes.c_uint),
        ("RefreshRate_Denominator", ctypes.c_uint),
        ("Format", ctypes.c_int),
        ("Scaling", ctypes.c_int),
        ("ScanlineOrdering", ctypes.c_int),
    ]


class DXGI_OUTPUT_DESC(ctypes.Structure):
    """Describes an output (monitor) attached to an adapter

    Attributes:
        DeviceName: The name of the output device (e.g., \\\\.\\DISPLAY1)
        DesktopCoordinates: The coordinates of the output on the desktop
        AttachedToDesktop: Whether the output is part of the desktop
        Rotation: How the output image is physically rotated
        Monitor: Handle to the HMONITOR associated with this output
    """
    _fields_ = [
        # WCHAR DeviceName[32] — wide chars (2 bytes each), NOT c_char.
        # Using c_char * 32 causes a 32-byte misalignment that shifts
        # DesktopCoordinates and makes the dimensions read as 0x0.
        ("DeviceName", ctypes.c_wchar * 32),
        ("DesktopCoordinates", ctypes.wintypes.RECT),
        ("AttachedToDesktop", ctypes.c_bool),
        ("Rotation", ctypes.c_int),
        ("Monitor", ctypes.wintypes.HANDLE),
    ]


class DXGI_OUTDUPL_FRAME_INFO(ctypes.Structure):
    """Contains frame information from IDXGIOutputDuplication::AcquireNextFrame

    Attributes:
        LastPresentTime: Time of the last present operation
        LastMouseUpdateTime: Time of the last mouse position update
        AccumulatedFrames: Number of frames accumulated since last AcquireNextFrame
        RectsCoalesced: Whether dirty/move rects were coalesced
        ProtectedContentMask: Mask indicating protected content regions
        PointerPosition: Current pointer position and visibility
        TotalMetadataBufferSize: Size of metadata buffer needed
        PointerShapeBufferSize: Size of pointer shape buffer needed
    """
    _fields_ = [
        ("LastPresentTime_LowPart", ctypes.c_ulong),
        ("LastPresentTime_HighPart", ctypes.c_long),
        ("LastMouseUpdateTime_LowPart", ctypes.c_ulong),
        ("LastMouseUpdateTime_HighPart", ctypes.c_long),
        ("AccumulatedFrames", ctypes.c_uint),
        ("RectsCoalesced", ctypes.c_bool),
        ("ProtectedContentMask_Present", ctypes.c_bool),
        ("ProtectedContentMask_Reserved", ctypes.c_ubyte * 3),
        ("PointerPosition_Position_x", ctypes.c_int),
        ("PointerPosition_Position_y", ctypes.c_int),
        ("PointerPosition_Visible", ctypes.c_bool),
        ("TotalMetadataBufferSize", ctypes.c_uint),
        ("PointerShapeBufferSize", ctypes.c_uint),
    ]


class _DXGI_OUTDUPL_POINTER_POSITION(ctypes.Structure):
    """Nested structure for pointer position within frame info"""
    _fields_ = [
        ("Position_x", ctypes.c_int),
        ("Position_y", ctypes.c_int),
        ("Visible", ctypes.c_bool),
    ]


class _DXGI_OUTDUPL_POINTER_SHAPE_INFO(ctypes.Structure):
    """Nested structure for pointer shape info within frame info"""
    _fields_ = [
        ("Type", ctypes.c_uint),
        ("Width", ctypes.c_uint),
        ("Height", ctypes.c_uint),
        ("Pitch", ctypes.c_uint),
        ("HotSpot_x", ctypes.c_int),
        ("HotSpot_y", ctypes.c_int),
    ]


# ---------------------------------------------------------------------------
# DXGICapture main class
# ---------------------------------------------------------------------------

class DXGICapture:
    """DXGI Desktop Duplication screenshot capture using pure ctypes COM

    Provides high-performance GPU-accelerated screen capture through the
    Windows Desktop Duplication API (IDXGIOutputDuplication). This method
    captures the entire desktop output at the GPU level, offering lower
    latency than GDI-based methods on systems with capable hardware.

    Lifecycle:
        initialize(hwnd) → [capture() → ...] → release()

    Usage example::

        cap = DXGICapture()
        if cap.initialize(0):  # 0 for primary monitor
            frame = cap.capture()
            if frame is not None:
                # frame is BGR numpy array (height, width, 3)
                pass
            cap.release()

    Reference:
        ok-script DXGICapture (based on d3dshot approach)
        MaaFramework DirectX screenshot module
        MSDN Desktop Duplication API documentation
    """

    def __init__(self):
        """Initialize internal state to None/uninitialized values"""
        self._d3d11_device: int | None = None
        self._d3d11_context: int | None = None
        self._dxgi_device: int | None = None
        self._dxgi_adapter: int | None = None
        self._dxgi_output: int | None = None
        # IDXGIOutput1 interface (QI'd from _dxgi_output) — DuplicateOutput is here.
        self._dxgi_output1: int | None = None
        self._output_dup: int | None = None
        self._staging_texture: int | None = None
        self._width: int = 0
        self._height: int = 0
        self._initialized: bool = False
        self._frame_timeout_ms: int = DEFAULT_FRAME_TIMEOUT_MS
        self._output_desc: DXGI_OUTPUT_DESC | None = None

    def initialize(self, hwnd: int = 0) -> bool:
        """Initialize DXGI Desktop Duplication capture session

        Sets up the full COM/D3D11/DXGI pipeline required for desktop duplication.
        This includes COM initialization, D3D11 device creation, DXGI adapter
        enumeration, output discovery, and desktop duplication interface creation.

        Args:
            hwnd: Target window handle (currently unused; DXGI captures full output).
                  Pass 0 or any value — the entire monitor output is captured.

        Returns:
            True if initialization succeeded, False otherwise

        Raises:
            RuntimeError: If critical initialization steps fail (COM init,
                         D3D11 device creation, adapter/output enumeration,
                         or DuplicateOutput call)
        """
        if self._initialized:
            logger.warning("DXGICapture already initialized, releasing previous session")
            self.release()

        d3d11 = None
        combase = None

        try:
            d3d11 = ctypes.windll.d3d11
            combase = ctypes.windll.combase
        except OSError as exc:
            raise RuntimeError(
                f"Failed to load required DLLs (d3d11/dxgi/combase): {exc}"
            ) from exc

        hr = combase.CoInitializeEx(None, COINIT_MULTITHREADED)
        if hr not in (S_OK, S_FALSE, 1):
            raise RuntimeError(f"CoInitializeEx failed with HRESULT: 0x{hr & 0xFFFFFFFF:08X}")

        try:
            self._d3d11_device = ctypes.c_void_p()
            self._d3d11_context = ctypes.c_void_p()

            create_device_fn = (
                ctypes.WINFUNCTYPE(
                    HRESULT,
                    ctypes.c_void_p,                          # 1. pAdapter (IDXGIAdapter*)
                    ctypes.c_uint,                            # 2. DriverType (D3D_DRIVER_TYPE)
                    ctypes.c_void_p,                          # 3. Software (HMODULE)
                    ctypes.c_uint,                            # 4. Flags (UINT)
                    ctypes.POINTER(ctypes.c_uint),            # 5. pFeatureLevels (const D3D_FEATURE_LEVEL*)
                    ctypes.c_uint,                            # 6. FeatureLevels (UINT count)
                    ctypes.c_uint,                            # 7. SDKVersion (UINT)
                    ctypes.POINTER(ctypes.c_void_p),          # 8. ppDevice (ID3D11Device**)
                    ctypes.POINTER(ctypes.c_uint),            # 9. pFeatureLevel (D3D_FEATURE_LEVEL* out)
                    ctypes.POINTER(ctypes.c_void_p),          # 10. ppImmediateContext (ID3D11DeviceContext**)
                )
            )(("D3D11CreateDevice", d3d11))

            hr = create_device_fn(
                None,
                D3D_DRIVER_TYPE_HARDWARE,
                None,
                0,
                None,
                0,
                D3D11_SDK_VERSION,
                ctypes.byref(self._d3d11_device),
                None,
                ctypes.byref(self._d3d11_context),
            )

            if hr != S_OK or not self._d3d11_device.value:
                raise RuntimeError(
                    f"D3D11CreateDevice failed with HRESULT: 0x{hr & 0xFFFFFFFF:08X}"
                )

            qi_fn = _com_call(0, HRESULT, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))
            dxgi_iid = _fill_guid(_uuid_to_guid(IID_IDXGIDevice))
            self._dxgi_device = ctypes.c_void_p()
            hr = qi_fn(self._d3d11_device.value, ctypes.byref(dxgi_iid), ctypes.byref(self._dxgi_device))
            if hr != S_OK or not self._dxgi_device.value:
                raise RuntimeError(
                    f"QueryInterface(IDXGIDevice) failed: 0x{hr & 0xFFFFFFFF:08X}"
                )

            # IDXGIDevice::GetAdapter — vtable[7]. Signature: HRESULT GetAdapter(IDXGIAdapter** ppAdapter)
            # (only 1 out-param; the old code wrongly passed an extra leading UINT).
            get_adapter_fn = _com_call(7, HRESULT, ctypes.POINTER(ctypes.c_void_p))
            self._dxgi_adapter = ctypes.c_void_p()
            hr = get_adapter_fn(self._dxgi_device.value, ctypes.byref(self._dxgi_adapter))
            if hr != S_OK or not self._dxgi_adapter.value:
                raise RuntimeError(
                    f"IDXGIDevice::GetAdapter failed: 0x{hr & 0xFFFFFFFF:08X}"
                )

            # IDXGIAdapter::EnumOutputs — vtable[7] (not [5]).
            # IDXGIAdapter: [0-2] IUnknown, [3-6] IDXGIObject, [7] EnumOutputs.
            enum_outputs_fn = _com_call(7, HRESULT, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))
            self._dxgi_output = ctypes.c_void_p()
            hr = enum_outputs_fn(self._dxgi_adapter.value, 0, ctypes.byref(self._dxgi_output))

            if hr != S_OK or not self._dxgi_output.value:
                raise RuntimeError(
                    f"IDXGIAdapter::EnumOutputs(0) failed: 0x{hr & 0xFFFFFFFF:08X}. "
                    "No outputs found on this adapter."
                )

            # DuplicateOutput lives on IDXGIOutput1 (not IDXGIOutput).
            # Standard path: QI the output for IDXGIOutput1, then call
            # DuplicateOutput on the QI'd interface.
            #
            # AMD driver bug fallback (TD-002): The AMD Radeon 610M driver's
            # EnumOutputs returns an output object whose vtable layout IS
            # IDXGIOutput1 (DuplicateOutput works at vtable[22]), but whose
            # QueryInterface wrongly returns E_NOINTERFACE for IDXGIOutput AND
            # IDXGIOutput1 (a clear violation of the COM contract). When QI
            # fails, we fall back to calling DuplicateOutput directly on the
            # output via vtable[22] — this works because the vtable layout is
            # correct even though QI is broken. See:
            #   test_enum_adapters1_vs_enum_adapters.py — confirms QI fails
            #   test_duplicateoutput_no_qi.py — confirms vtable[22] works
            output1_iid = _fill_guid(_uuid_to_guid(IID_IDXGIOutput1))
            self._dxgi_output1 = ctypes.c_void_p()
            hr = qi_fn(
                self._dxgi_output.value,
                ctypes.byref(output1_iid),
                ctypes.byref(self._dxgi_output1),
            )

            dup_output_fn = _com_call(
                22, HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
            )
            self._output_dup = ctypes.c_void_p()

            if hr == S_OK and self._dxgi_output1.value:
                # Standard path: call DuplicateOutput on the QI'd IDXGIOutput1.
                hr = dup_output_fn(
                    self._dxgi_output1.value,
                    self._d3d11_device.value,
                    ctypes.byref(self._output_dup),
                )
            else:
                # AMD driver bug fallback: QI for IDXGIOutput1 failed, but the
                # output's vtable layout is still IDXGIOutput1. Call
                # DuplicateOutput directly on the output via vtable[22].
                logger.warning(
                    "QueryInterface(IDXGIOutput1) returned 0x%08X on the "
                    "DXGI output — falling back to direct vtable[22] call. "
                    "This is a known driver bug (TD-002).",
                    hr & 0xFFFFFFFF,
                )
                hr = dup_output_fn(
                    self._dxgi_output.value,
                    self._d3d11_device.value,
                    ctypes.byref(self._output_dup),
                )

            if hr == DXGI_ERROR_ALREADY_EXIST:
                logger.warning(
                    "Desktop Duplication already in use by another application"
                )
                raise RuntimeError(
                    "Desktop Duplication API is already in use by another process"
                )
            elif hr != S_OK or not self._output_dup.value:
                raise RuntimeError(
                    f"IDXGIOutput1::DuplicateOutput failed: 0x{hr & 0xFFFFFFFF:08X}"
                )

            self._output_desc = self._get_output_description()
            if self._output_desc:
                rect = self._output_desc.DesktopCoordinates
                self._width = rect.right - rect.left
                self._height = rect.bottom - rect.top
            else:
                user32 = ctypes.windll.user32
                self._width = user32.GetSystemMetrics(0)
                self._height = user32.GetSystemMetrics(1)

            if self._width <= 0 or self._height <= 0:
                raise RuntimeError(f"Invalid output dimensions: {self._width}x{self._height}")

            self._create_staging_texture()

            self._initialized = True
            logger.info(
                "DXGICapture initialized successfully: %dx%d",
                self._width, self._height,
            )
            return True

        except Exception:
            self._cleanup_internal()
            raise

    def capture(self) -> np.ndarray | None:
        """Capture a single frame from the desktop duplication interface

        Acquires the next available desktop frame, copies it to a CPU-accessible
        staging texture, maps it to system memory, and returns as BGR numpy array.

        Handles frame timeout gracefully — if no new frame is available within
        the configured timeout period, returns None instead of blocking forever.

        Returns:
            BGR numpy array with shape (height, width, 3), or None if:
            - Frame acquisition timed out (no new frame available)
            - Access was lost (mode change, fullscreen exclusive, etc.)
            - Any other DXGI error occurred

        Raises:
            RuntimeError: If called before initialize() or after release()
        """
        if not self._initialized or not self._output_dup:
            raise RuntimeError("DXGICapture not initialized. Call initialize() first.")

        # IDXGIOutputDuplication::AcquireNextFrame — vtable[8] (not [1]).
        # IDXGIOutputDuplication: [0-2] IUnknown, [3-6] IDXGIObject,
        # [7] GetDesc, [8] AcquireNextFrame, [9] ReleaseFrame.
        acquire_frame_fn = _com_call(
            8,
            HRESULT,
            ctypes.c_uint,
            ctypes.POINTER(DXGI_OUTDUPL_FRAME_INFO),
            ctypes.POINTER(ctypes.c_void_p),
        )

        frame_info = DXGI_OUTDUPL_FRAME_INFO()
        resource_ptr = ctypes.c_void_p()

        hr = acquire_frame_fn(
            self._output_dup.value,
            self._frame_timeout_ms,
            ctypes.byref(frame_info),
            ctypes.byref(resource_ptr),
        )

        if hr == DXGI_ERROR_WAIT_TIMEOUT:
            logger.debug("AcquireNextFrame timed out (%d ms)", self._frame_timeout_ms)
            return None

        if hr == DXGI_ERROR_ACCESS_LOST:
            logger.warning("Desktop Duplication access lost (mode change / fullscreen)")
            self._release_frame_if_acquired()
            return None

        if hr == E_ACCESSDENIED:
            logger.debug("AcquireNextFrame returned ACCESS_DENIED")
            self._release_frame_if_acquired()
            return None

        # AMD driver bug workaround (TD-002): ReleaseFrame (vtable[9]) crashes
        # inside the AMD Radeon 610M driver, so the previous frame is never
        # released. This causes AcquireNextFrame to return
        # DXGI_ERROR_INVALID_CALL on the next call. Work around this by
        # recreating the OutputDuplication object and retrying once.
        if hr == DXGI_ERROR_INVALID_CALL:
            logger.debug(
                "AcquireNextFrame returned DXGI_ERROR_INVALID_CALL — "
                "recreating OutputDuplication (AMD ReleaseFrame bug, TD-002)"
            )
            if not self._recreate_output_duplication():
                logger.warning("Failed to recreate OutputDuplication")
                return None
            # Retry AcquireNextFrame with the fresh OutputDuplication.
            frame_info = DXGI_OUTDUPL_FRAME_INFO()
            resource_ptr = ctypes.c_void_p()
            hr = acquire_frame_fn(
                self._output_dup.value,
                self._frame_timeout_ms,
                ctypes.byref(frame_info),
                ctypes.byref(resource_ptr),
            )
            if hr != S_OK or not resource_ptr.value:
                logger.warning(
                    "AcquireNextFrame retry failed after recreate: 0x%08X",
                    hr & 0xFFFFFFFF,
                )
                return None

        elif hr != S_OK or not resource_ptr.value:
            logger.warning("AcquireNextFrame failed: 0x%08X", hr & 0xFFFFFFFF)
            self._release_frame_if_acquired()
            return None

        try:
            return self._read_frame_pixels(resource_ptr.value)
        finally:
            self._release_frame_if_acquired()

    def release(self) -> None:
        """Release all COM resources and shut down the capture session

        Releases the staging texture, output duplication interface, output,
        adapter, DXGI device, D3D11 device context, and D3D11 device in order.
        Finally calls CoUninitialize to clean up the COM apartment.
        Must be called when capture operations are complete to avoid resource leaks.
        """
        if not self._initialized:
            return

        self._cleanup_internal()
        self._initialized = False
        logger.info("DXGICapture released")

    def set_frame_timeout(self, timeout_ms: int) -> None:
        """Configure the timeout for AcquireNextFrame in milliseconds

        Args:
            timeout_ms: Maximum time to wait for a new frame before returning None.
                        Default is 1000ms. Set to 0 for immediate return.
        """
        self._frame_timeout_ms = max(0, timeout_ms)

    def get_output_info(self) -> dict | None:
        """Retrieve information about the current output (monitor)

        Returns:
            Dictionary containing output description fields, or None if
            not initialized. Fields include:
            - device_name: Output device name string
            - desktop_rect: (left, top, right, bottom) coordinates
            - attached_to_desktop: Boolean indicating desktop attachment
            - rotation: Rotation mode integer
            - width: Output width in pixels
            - height: Output height in pixels
        """
        if not self._output_desc:
            return None

        r = self._output_desc.DesktopCoordinates
        return {
            "device_name": self._output_desc.DeviceName.decode("ascii", errors="replace").rstrip("\x00"),
            "desktop_rect": (r.left, r.top, r.right, r.bottom),
            "attached_to_desktop": bool(self._output_desc.AttachedToDesktop),
            "rotation": self._output_desc.Rotation,
            "width": self._width,
            "height": self._height,
        }

    @property
    def is_initialized(self) -> bool:
        """Check whether the capture session has been successfully initialized"""
        return self._initialized

    @property
    def resolution(self) -> tuple[int, int]:
        """Get the current capture resolution as (width, height) tuple"""
        return (self._width, self._height)

    # -------------------------------------------------------------------------
    # Internal methods
    # -------------------------------------------------------------------------

    def _get_output_description(self) -> DXGI_OUTPUT_DESC | None:
        """Query DXGI_OUTPUT_DESC from the output interface

        Retrieves detailed information about the output (monitor) including
        device name, desktop coordinates, attachment status, rotation, etc.

        Returns:
            DXGI_OUTPUT_DESC structure filled with output data, or None on failure
        """
        if not self._dxgi_output:
            return None

        # IDXGIOutput::GetDesc — vtable[7] (not [4], which is SetPrivateDataInterface).
        # IDXGIOutput: [0-2] IUnknown, [3-6] IDXGIObject, [7] GetDesc.
        get_desc_fn = _com_call(7, None, ctypes.POINTER(DXGI_OUTPUT_DESC))
        desc = DXGI_OUTPUT_DESC()
        try:
            get_desc_fn(self._dxgi_output.value, ctypes.byref(desc))
            return desc
        except Exception as exc:
            logger.warning("IDXGIOutput::GetDesc failed: %s", exc)
            return None

    def _create_staging_texture(self) -> None:
        """Create a CPU-readable staging texture for frame data transfer

        Creates a D3D11 Texture2D with Staging usage that allows CPU read access.
        This texture serves as the intermediate buffer between GPU desktop
        duplication output and CPU-accessible memory for numpy conversion.

        ID3D11Device::CreateTexture2D is a COM method on the D3D11 device, NOT
        a DLL export. It lives at vtable[5] on ID3D11Device:
            [0-2] IUnknown, [3] CreateBuffer, [4] CreateTexture1D,
            [5] CreateTexture2D.
        """
        tex_desc = D3D11_TEXTURE2D_DESC()
        tex_desc.Width = self._width
        tex_desc.Height = self._height
        tex_desc.MipLevels = 1
        tex_desc.ArraySize = 1
        tex_desc.Format = DXGI_FORMAT_B8G8R8A8_UNORM
        tex_desc.SampleDesc_Count = 1
        tex_desc.SampleDesc_Quality = 0
        tex_desc.Usage = D3D11_USAGE_STAGING
        tex_desc.BindFlags = 0
        tex_desc.CPUAccessFlags = D3D11_CPU_ACCESS_READ
        tex_desc.MiscFlags = 0

        # ID3D11Device::CreateTexture2D — vtable[5].
        # Signature: HRESULT CreateTexture2D(
        #     const D3D11_TEXTURE2D_DESC* pDesc,
        #     const D3D11_SUBRESOURCE_DATA* pInitialData,
        #     ID3D11Texture2D** ppTexture2D)
        create_texture_fn = _com_call(
            5, HRESULT,
            ctypes.POINTER(D3D11_TEXTURE2D_DESC),
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        )

        self._staging_texture = ctypes.c_void_p()
        hr = create_texture_fn(
            self._d3d11_device.value,
            ctypes.byref(tex_desc),
            None,
            ctypes.byref(self._staging_texture),
        )

        if hr != S_OK or not self._staging_texture.value:
            raise RuntimeError(
                f"ID3D11Device::CreateTexture2D (staging) failed: "
                f"0x{hr & 0xFFFFFFFF:08X}"
            )

    def _read_frame_pixels(self, resource_ptr: int) -> np.ndarray | None:
        """Read pixel data from acquired frame resource into numpy array

        Standard Desktop Duplication readback pattern (matches MaaFramework
        DesktopDupScreencap.cpp:376-384):

        1. QI acquired IDXGIResource → ID3D11Texture2D (the GPU-only frame).
        2. ID3D11DeviceContext::CopyResource from GPU texture → CPU-readable
           staging texture.
        3. ID3D11DeviceContext::Map on the staging texture (NO QI for
           IDXGISurface needed — Map takes ID3D11Resource* directly).
        4. Convert BGRA → BGR numpy array.
        5. ID3D11DeviceContext::Unmap.

        Why ID3D11DeviceContext::Map instead of IDXGISurface::Map:
          The AMD Radeon 610M driver has a QueryInterface bug — QI for
          IDXGISurface (and IDXGIOutput, IDXGIOutput1) returns E_NOINTERFACE
          (0x80004002) on objects whose vtable layout IS correct. To work
          around this, we avoid QI for IDXGISurface entirely and use
          ID3D11DeviceContext::Map, which takes ID3D11Resource* directly
          (ID3D11Texture2D IS an ID3D11Resource, no QI needed). This is
          also the pattern MaaFramework uses.

        Vtable indices (ID3D11DeviceContext : ID3D11DeviceChild : IUnknown):
          [0-2]   IUnknown (QI, AddRef, Release)
          [3-6]   ID3D11DeviceChild (GetDevice, GetPrivateData,
                  SetPrivateData, SetPrivateDataInterface)
          [7]     VSSetConstantBuffers
          [8]     PSSetShaderResources
          [9]     PSSetShader
          [10]    PSSetSamplers
          [11]    VSSetShader
          [12]    DrawIndexed
          [13]    Draw
          [14]    Map           <-- this one
          [15]    Unmap         <-- this one
          ...
          [47]    CopyResource  <-- this one

        Args:
            resource_ptr: Pointer to the IDXGIResource from AcquireNextFrame

        Returns:
            BGR numpy array (height, width, 3), or None on failure
        """
        qi_fn = _com_call(0, HRESULT, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))

        # Step 1: QI acquired resource → ID3D11Texture2D.
        texture_iid = _fill_guid(_uuid_to_guid(IID_ID3D11Texture2D))
        texture_ptr = ctypes.c_void_p()
        hr = qi_fn(resource_ptr, ctypes.byref(texture_iid), ctypes.byref(texture_ptr))
        if hr != S_OK or not texture_ptr.value:
            logger.warning(
                "Failed to QI acquired resource to ID3D11Texture2D: 0x%08X",
                hr & 0xFFFFFFFF,
            )
            return None

        try:
            # Step 2: ID3D11DeviceContext::CopyResource — vtable[47].
            # ID3D11DeviceContext vtable layout: [0-2] IUnknown,
            # [3-6] ID3D11DeviceChild, [7-46] various methods
            # (VSSetConstantBuffers, PSSetShader, Draw, Map, Unmap, ...,
            # CopySubresourceRegion), [47] CopyResource.
            # Signature: void CopyResource(ID3D11Resource* pDst, ID3D11Resource* pSrc)
            # Note: returns void (not HRESULT) — restype is None.
            copy_resource_fn = _com_call(47, None, ctypes.c_void_p, ctypes.c_void_p)
            copy_resource_fn(
                self._d3d11_context.value,
                self._staging_texture.value,
                texture_ptr.value,
            )

            # Step 3: ID3D11DeviceContext::Map — vtable[14].
            # Signature: HRESULT Map(
            #     ID3D11Resource* pResource,
            #     UINT Subresource,
            #     D3D11_MAP MapType,
            #     UINT MapFlags,
            #     D3D11_MAPPED_SUBRESOURCE* pMappedResource)
            # Note: NO QI for IDXGISurface needed — Map takes ID3D11Resource*
            # directly, and ID3D11Texture2D IS an ID3D11Resource. This works
            # around the AMD driver QI bug (QI for IDXGISurface returns
            # E_NOINTERFACE on AMD Radeon 610M, TD-002).
            map_fn = _com_call(
                14, HRESULT,
                ctypes.c_void_p,           # pResource (staging texture as ID3D11Resource*)
                ctypes.c_uint,             # Subresource
                ctypes.c_uint,             # MapType (D3D11_MAP)
                ctypes.c_uint,             # MapFlags
                ctypes.POINTER(D3D11_MAPPED_SUBRESOURCE),  # pMappedResource
            )
            mapped = D3D11_MAPPED_SUBRESOURCE()
            hr = map_fn(
                self._d3d11_context.value,
                self._staging_texture.value,
                0,                          # Subresource = 0
                D3D11_MAP_READ,             # MapType
                0,                          # MapFlags
                ctypes.byref(mapped),
            )
            if hr != S_OK:
                logger.warning(
                    "ID3D11DeviceContext::Map(staging) failed: 0x%08X",
                    hr & 0xFFFFFFFF,
                )
                return None

            try:
                # Step 4: BGRA → BGR numpy.
                # RowPitch is in bytes; 4 bytes per BGRA pixel.
                row_width = mapped.RowPitch // 4
                buf_size = mapped.RowPitch * self._height
                buf = (ctypes.c_ubyte * buf_size).from_address(mapped.pData)
                img = np.frombuffer(buf, dtype=np.uint8).reshape(
                    (self._height, row_width, 4)
                )
                img_cropped = img[:, :self._width, :].copy()
                bgr = img_cropped[:, :, :3].copy()
                return bgr
            finally:
                # Step 5: ID3D11DeviceContext::Unmap — vtable[15].
                # Signature: void Unmap(ID3D11Resource* pResource, UINT Subresource)
                # Note: returns void (not HRESULT) — restype is None.
                unmap_fn = _com_call(15, None, ctypes.c_void_p, ctypes.c_uint)
                unmap_fn(
                    self._d3d11_context.value,
                    self._staging_texture.value,
                    0,  # Subresource = 0
                )
        finally:
            _com_release(texture_ptr.value)

        return None

    def _release_frame_if_acquired(self) -> None:
        """Safely release the currently acquired frame

        Calls IDXGIOutputDuplication::ReleaseFrame to return the frame to the
        desktop duplication API. Must be called after every successful
        AcquireNextFrame to prevent frame queue starvation.

        AMD driver bug (TD-002): On AMD Radeon 610M, ReleaseFrame crashes
        inside the driver with an access violation. The exception is caught
        here, but the frame is NOT released. The next AcquireNextFrame will
        return DXGI_ERROR_INVALID_CALL, which triggers
        _recreate_output_duplication() in capture() as a workaround.
        """
        if not self._output_dup:
            return

        try:
            # IDXGIOutputDuplication::ReleaseFrame — vtable[9] (not [3]).
            release_frame_fn = _com_call(9, HRESULT)
            release_frame_fn(self._output_dup.value)
        except Exception as exc:
            logger.debug("ReleaseFrame error (may be expected): %s", exc)

    def _recreate_output_duplication(self) -> bool:
        """Recreate the IDXGIOutputDuplication object.

        This is a workaround for the AMD Radeon 610M driver bug where
        ReleaseFrame (vtable[9]) crashes inside the driver, leaving the
        frame permanently acquired. After the crash, AcquireNextFrame
        returns DXGI_ERROR_INVALID_CALL. The only recovery is to release
        the old OutputDuplication object and create a new one via
        DuplicateOutput.

        The dxgi_output and d3d11_device are reused — only the
        OutputDuplication and the IDXGIOutput1 QI result (if any) are
        recreated. The staging texture is also reused (its dimensions
        haven't changed).

        Returns:
            True if recreation succeeded, False otherwise.
        """
        # Release the old OutputDuplication and IDXGIOutput1 (if any).
        if self._output_dup:
            _com_release(self._output_dup.value)
            self._output_dup = None
        if self._dxgi_output1:
            _com_release(self._dxgi_output1.value)
            self._dxgi_output1 = None

        if not self._dxgi_output or not self._d3d11_device:
            logger.error("Cannot recreate OutputDuplication: missing dxgi_output or d3d11_device")
            return False

        # Re-create OutputDuplication via DuplicateOutput (vtable[22]).
        # Same logic as initialize(): try QI for IDXGIOutput1 first, fall
        # back to direct vtable[22] call on AMD (where QI is broken).
        qi_fn = _com_call(0, HRESULT, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))
        output1_iid = _fill_guid(_uuid_to_guid(IID_IDXGIOutput1))
        self._dxgi_output1 = ctypes.c_void_p()
        hr = qi_fn(
            self._dxgi_output.value,
            ctypes.byref(output1_iid),
            ctypes.byref(self._dxgi_output1),
        )

        dup_output_fn = _com_call(
            22, HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
        )
        self._output_dup = ctypes.c_void_p()

        if hr == S_OK and self._dxgi_output1.value:
            # Standard path: DuplicateOutput on the QI'd IDXGIOutput1.
            hr = dup_output_fn(
                self._dxgi_output1.value,
                self._d3d11_device.value,
                ctypes.byref(self._output_dup),
            )
        else:
            # AMD fallback: DuplicateOutput directly on the output via vtable[22].
            hr = dup_output_fn(
                self._dxgi_output.value,
                self._d3d11_device.value,
                ctypes.byref(self._output_dup),
            )

        if hr != S_OK or not self._output_dup.value:
            logger.error(
                "Failed to recreate OutputDuplication: 0x%08X",
                hr & 0xFFFFFFFF,
            )
            return False

        # Give the fresh OutputDuplication a moment to capture the desktop.
        # Without this delay, the first AcquireNextFrame on the new duplication
        # returns S_OK with an empty (all-black) frame — the duplication hasn't
        # had time to composite the desktop yet. 200ms is enough on AMD Radeon
        # 610M; shorter delays still produce black frames.
        time.sleep(0.2)

        logger.debug("OutputDuplication recreated successfully (AMD ReleaseFrame workaround)")
        return True

    def _cleanup_internal(self) -> None:
        """Internal cleanup helper that releases all COM resources in reverse order

        Releases resources in LIFO order: staging texture → output duplication →
        output → adapter → DXGI device → D3D11 context → D3D11 device → CoUninit.
        Each step uses try/except to ensure all resources are attempted even if
        one release fails.
        """
        if self._staging_texture:
            _com_release(self._staging_texture.value)
            self._staging_texture = None

        if self._output_dup:
            try:
                # IDXGIOutputDuplication::ReleaseFrame — vtable[9] (not [3]).
                release_frame_fn = _com_call(9, HRESULT)
                release_frame_fn(self._output_dup.value)
            except Exception:
                pass
            _com_release(self._output_dup.value)
            self._output_dup = None

        if self._dxgi_output1:
            _com_release(self._dxgi_output1.value)
            self._dxgi_output1 = None

        if self._dxgi_output:
            _com_release(self._dxgi_output.value)
            self._dxgi_output = None

        if self._dxgi_adapter:
            _com_release(self._dxgi_adapter.value)
            self._dxgi_adapter = None

        if self._dxgi_device:
            _com_release(self._dxgi_device.value)
            self._dxgi_device = None

        if self._d3d11_context:
            _com_release(self._d3d11_context.value)
            self._d3d11_context = None

        if self._d3d11_device:
            _com_release(self._d3d11_device.value)
            self._d3d11_device = None

        with contextlib.suppress(Exception):
            ctypes.windll.combase.CoUninitialize()

        self._output_desc = None
        self._width = 0
        self._height = 0
