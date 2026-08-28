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

# When the desktop has not changed since DuplicateOutput was created, the first
# AcquireNextFrame returns S_OK with AccumulatedFrames=0 and an empty/black
# source texture. Retry until AccumulatedFrames > 0 (real desktop content).
EMPTY_FRAME_MAX_RETRIES = 5

# After recreating the IDXGIOutputDuplication (workaround for ReleaseFrame
# crash — see _recreate_duplication), wait briefly for the desktop to
# accumulate changes before calling AcquireNextFrame. Without this delay,
# the first AcquireNextFrame returns AccumulatedFrames=0 (empty/black frame).
RECREATE_SETTLE_TIME_SEC = 0.05

# ---------------------------------------------------------------------------
# GUID definitions for COM interfaces
# ---------------------------------------------------------------------------

IID_IUnknown = _uuid.UUID("{00000000-0000-0000-C000-000000000046}")
IID_ID3D11Device = _uuid.UUID("{DB6F6DDB-AC77-4E88-8253-819DF9BBF140}")
IID_ID3D11DeviceContext = _uuid.UUID("{C0BFA96C-E089-44FB-8EAF-26F8796190DA}")
IID_ID3D11Texture2D = _uuid.UUID("{6F15AAF2-D208-4E89-9AB4-489535D34F9C}")
IID_IDXGIObject = _uuid.UUID("{AEC22FB8-76F3-4639-9BE0-4B7661B4656C}")
IID_IDXGIDevice = _uuid.UUID("{54EC77FA-1377-44E6-8C32-88FD5F44C84C}")
IID_IDXGIAdapter = _uuid.UUID("{2411E733-1AC1-4F93-BB38-61C280C49694}")
IID_IDXGIOutput = _uuid.UUID("{AE02EFB9-BC4C-447B-A64A-C06CF5F066D0}")
# IID_IDXGIOutput1 — required for DuplicateOutput (which lives on IDXGIOutput1,
# not on the base IDXGIOutput interface). Must QI from IDXGIOutput before call.
IID_IDXGIOutput1 = _uuid.UUID("{00CDADB8-9C1C-4E85-A2F2-64E930D4F4D8}")
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

    The returned callable expects the COM interface pointer as its first
    argument, resolves the vtable entry at ``vtable_idx``, and invokes the
    method with the interface pointer plus any additional arguments.

    Args:
        vtable_idx: Zero-based index into the interface vtable
        restype: Return type of the method
        *argtypes: Parameter types for the method (excluding the this pointer)

    Returns:
        A callable that takes (interface_ptr, *args) and returns the HRESULT.
    """
    prototype = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)

    def caller(interface_ptr: ctypes.c_void_p | int, *args):
        # Resolve the vtable function pointer from the interface pointer.
        ptr_value = interface_ptr.value if isinstance(interface_ptr, ctypes.c_void_p) else interface_ptr
        vtable_pptr = ctypes.cast(ptr_value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))
        vtable_ptr = vtable_pptr.contents
        fn_ptr = vtable_ptr[vtable_idx]
        fn = prototype(fn_ptr)
        # Pass the raw integer value, NOT the c_void_p object. A c_void_p that
        # was filled via ctypes.byref() (e.g. self._output_dup after
        # DuplicateOutput) can cause access violations when passed directly to
        # a WINFUNCTYPE callable — observed with IDXGIOutputDuplication::
        # ReleaseFrame crashing with "access violation reading 0xFFFFFFFF..."
        # Passing the int value avoids this entirely.
        return fn(ptr_value, *args)

    return caller


def _com_release(ptr: ctypes.c_void_p | int) -> None:
    """Release a COM interface pointer (calls IUnknown::Release)

    Args:
        ptr: COM interface pointer to release
    """
    if not ptr:
        return
    try:
        release_fn = _com_call(2, ctypes.c_uint)
        release_fn(ptr)
    except Exception:
        logger.debug('COM Release failed', exc_info=True)


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

class D3D11_TEXTURE2D_DESC(ctypes.Structure):  # noqa: N801
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


class D3D11_MAPPED_SUBRESOURCE(ctypes.Structure):  # noqa: N801
    """Represents mapped subresource data from ID3D11DeviceContext::Map"""
    _fields_ = [
        ("pData", ctypes.c_void_p),
        ("RowPitch", ctypes.c_uint),
        ("DepthPitch", ctypes.c_uint),
    ]


class DXGI_MAPPED_RECT(ctypes.Structure):  # noqa: N801
    """Represents mapped surface data from IDXGISurface::Map"""
    _fields_ = [
        ("Pitch", ctypes.c_uint),
        ("pBits", ctypes.c_void_p),
    ]


class DXGI_MODE_DESC(ctypes.Structure):  # noqa: N801
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


class DXGI_OUTPUT_DESC(ctypes.Structure):  # noqa: N801
    """Describes an output (monitor) attached to an adapter

    Attributes:
        DeviceName: The name of the output device (e.g., \\\\.\\DISPLAY1)
        DesktopCoordinates: The coordinates of the output on the desktop
        AttachedToDesktop: Whether the output is part of the desktop
        Rotation: How the output image is physically rotated
        Monitor: Handle to the HMONITOR associated with this output
    """
    _fields_ = [
        # WCHAR DeviceName[32] — 64 bytes (WCHAR is 2 bytes on Windows).
        # Using c_char*32 here previously caused a 32-byte layout shift that
        # corrupted all subsequent fields (DesktopCoordinates etc.), yielding
        # 0x0 dimensions.
        ("DeviceName", ctypes.c_wchar * 32),
        ("DesktopCoordinates", ctypes.wintypes.RECT),
        ("AttachedToDesktop", ctypes.c_bool),
        ("Rotation", ctypes.c_int),
        ("Monitor", ctypes.wintypes.HANDLE),
    ]


class DXGI_OUTDUPL_FRAME_INFO(ctypes.Structure):  # noqa: N801
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

    Note: Windows BOOL is 4 bytes (int-sized), not 1 byte. Using c_bool for
    BOOL fields caused a 3-byte-per-field layout shift that corrupted all
    fields after the first BOOL (RectsCoalesced).
    """
    _fields_ = [
        ("LastPresentTime_LowPart", ctypes.c_ulong),
        ("LastPresentTime_HighPart", ctypes.c_long),
        ("LastMouseUpdateTime_LowPart", ctypes.c_ulong),
        ("LastMouseUpdateTime_HighPart", ctypes.c_long),
        ("AccumulatedFrames", ctypes.c_uint),
        # BOOL is 4 bytes on Windows (c_int), NOT 1 byte (c_bool).
        ("RectsCoalesced", ctypes.c_int),
        ("ProtectedContentMask_Present", ctypes.c_int),
        ("PointerPosition_Position_x", ctypes.c_int),
        ("PointerPosition_Position_y", ctypes.c_int),
        ("PointerPosition_Visible", ctypes.c_int),
        ("TotalMetadataBufferSize", ctypes.c_uint),
        ("PointerShapeBufferSize", ctypes.c_uint),
    ]


class _DXGI_OUTDUPL_POINTER_POSITION(ctypes.Structure):  # noqa: N801
    """Nested structure for pointer position within frame info"""
    _fields_ = [
        ("Position_x", ctypes.c_int),
        ("Position_y", ctypes.c_int),
        ("Visible", ctypes.c_bool),
    ]


class _DXGI_OUTDUPL_POINTER_SHAPE_INFO(ctypes.Structure):  # noqa: N801
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
        # IDXGIOutput1 interface (QI'd from _dxgi_output). Required because
        # DuplicateOutput lives on IDXGIOutput1 (vtable 22), not IDXGIOutput.
        self._dxgi_output1: int | None = None
        self._output_dup: int | None = None
        self._staging_texture: int | None = None
        self._width: int = 0
        self._height: int = 0
        self._initialized: bool = False
        self._frame_timeout_ms: int = DEFAULT_FRAME_TIMEOUT_MS
        self._output_desc: DXGI_OUTPUT_DESC | None = None
        # Tracks whether AcquireNextFrame has been called and the frame has
        # not yet been "released" (via dup recreation). Used to avoid calling
        # ReleaseFrame (which crashes on this system — see _recreate_duplication).
        self._frame_held: bool = False

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
            # Ensure DXGI DLL is loaded in process space even though we access
            # it through COM later.
            _ = ctypes.windll.dxgi
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
                    ctypes.c_void_p,
                    ctypes.c_uint,
                    ctypes.c_void_p,
                    ctypes.c_uint,
                    ctypes.c_void_p,
                    ctypes.c_uint,
                    ctypes.c_uint,
                    ctypes.POINTER(ctypes.c_void_p),
                    ctypes.POINTER(ctypes.c_uint),
                    ctypes.POINTER(ctypes.c_void_p),
                )
            )(("D3D11CreateDevice", d3d11))

            feature_level = ctypes.c_uint()
            hr = create_device_fn(
                None,
                D3D_DRIVER_TYPE_HARDWARE,
                None,
                0,
                None,
                0,
                D3D11_SDK_VERSION,
                ctypes.byref(self._d3d11_device),
                ctypes.byref(feature_level),
                ctypes.byref(self._d3d11_context),
            )

            if hr != S_OK or not self._d3d11_device.value:
                raise RuntimeError(
                    f"D3D11CreateDevice failed with HRESULT: 0x{hr & 0xFFFFFFFF:08X}"
                )

            qi_fn = _com_call(0, HRESULT, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))
            dxgi_iid = _fill_guid(_uuid_to_guid(IID_IDXGIDevice))
            self._dxgi_device = ctypes.c_void_p()
            hr = qi_fn(self._d3d11_device, ctypes.byref(dxgi_iid), ctypes.byref(self._dxgi_device))
            if hr != S_OK or not self._dxgi_device.value:
                raise RuntimeError(
                    f"QueryInterface(IDXGIDevice) failed: 0x{hr & 0xFFFFFFFF:08X}"
                )

            get_adapter_fn = _com_call(7, HRESULT, ctypes.POINTER(ctypes.c_void_p))
            self._dxgi_adapter = ctypes.c_void_p()
            hr = get_adapter_fn(self._dxgi_device, ctypes.byref(self._dxgi_adapter))
            if hr != S_OK or not self._dxgi_adapter.value:
                raise RuntimeError(
                    f"IDXGIDevice::GetAdapter failed: 0x{hr & 0xFFFFFFFF:08X}"
                )

            # IDXGIAdapter::EnumOutputs is at vtable index 7:
            # IUnknown(0-2) + IDXGIObject(3-6) + IDXGIAdapter::EnumOutputs(7).
            # The previous code used index 5 (IDXGIObject::GetPrivateData), which
            # caused an access violation when called with the wrong arg signature.
            enum_outputs_fn = _com_call(
                7, HRESULT, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)
            )
            self._dxgi_output = ctypes.c_void_p()
            hr = enum_outputs_fn(self._dxgi_adapter, 0, ctypes.byref(self._dxgi_output))

            if hr != S_OK or not self._dxgi_output.value:
                raise RuntimeError(
                    f"IDXGIAdapter::EnumOutputs(0) failed: 0x{hr & 0xFFFFFFFF:08X}. "
                    "No outputs found on this adapter."
                )

            # DuplicateOutput lives on IDXGIOutput1 (vtable index 22), NOT on the
            # base IDXGIOutput interface. IDXGIOutput1 inherits from IDXGIOutput,
            # so on Windows 8+ the output object returned by EnumOutputs is
            # vtable-compatible with IDXGIOutput1 and we can call DuplicateOutput
            # directly at vtable 22 without QueryInterface.
            #
            # We deliberately skip QI for IID_IDXGIOutput1 because empirical
            # testing (see diag_qi.py) showed QI returns E_NOINTERFACE on this
            # system even though the DuplicateOutput call at vtable 22 succeeds
            # and the returned object passes QI for IID_IDXGIOutputDuplication
            # (verified by diag_qi_v2.py). This matches the pattern used by
            # d3dshot and other pure-ctypes Desktop Duplication implementations.
            # IDXGIOutput1 vtable: IUnknown(0-2) + IDXGIObject(3-6) + IDXGIOutput
            # (7-18, 12 methods) + IDXGIOutput1(19=GetDisplayModeList1,
            # 20=FindClosestMatchingMode1, 21=GetDisplaySurfaceData1, 22=DuplicateOutput).
            #
            # IMPORTANT: IDXGIOutputDuplication::ReleaseFrame (vtable 9) crashes
            # on this system with "access violation reading 0xFFFFFFFFFFFFFFFF"
            # whenever a frame is held (regardless of AccumulatedFrames value).
            # As a workaround, we NEVER call ReleaseFrame. Instead, to release a
            # held frame, we destroy the entire IDXGIOutputDuplication interface
            # (IUnknown::Release) and call DuplicateOutput again to create a
            # fresh one. See _recreate_duplication() and capture() for details.
            self._dxgi_output1 = None  # Not QI'd; calling directly on _dxgi_output.

            # DuplicateOutput signature: HRESULT(IUnknown *pDevice, IDXGIOutputDuplication **ppOut)
            dup_output_fn = _com_call(
                22, HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
            )
            self._output_dup = ctypes.c_void_p()
            hr = dup_output_fn(
                self._dxgi_output,
                self._d3d11_device,
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

            self._create_staging_texture(d3d11)

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

        **ReleaseFrame crash workaround**: On this system, IDXGIOutputDuplication::
        ReleaseFrame (vtable 9) crashes with "access violation reading
        0xFFFFFFFFFFFFFFFF" whenever a frame is held. As a workaround, this
        method NEVER calls ReleaseFrame. Instead, to "release" a held frame,
        it destroys the entire IDXGIOutputDuplication interface (IUnknown::
        Release) and calls DuplicateOutput again to create a fresh one. This
        is more expensive than ReleaseFrame but is the only reliable approach
        on this system.

        Frame lifecycle:
        1. If a frame is held from a previous capture, recreate the duplication
           (releases the old dup + held frame, creates a fresh dup).
        2. AcquireNextFrame — if AccumulatedFrames=0 (empty/black texture),
           release the resource, recreate the dup, sleep briefly, and retry.
        3. If AccumulatedFrames>0, read pixels and release the IDXGIResource.
           The frame remains "held" by the dup until the next capture() call
           recreates it.

        Returns:
            BGR numpy array with shape (height, width, 3), or None if:
            - Frame acquisition timed out (no new frame available)
            - Access was lost (mode change, fullscreen exclusive, etc.)
            - All retries returned empty frames (desktop idle too long)
            - Duplication recreation failed
            - Any other DXGI error occurred

        Raises:
            RuntimeError: If called before initialize() or after release()
        """
        if not self._initialized or not self._output_dup:
            raise RuntimeError("DXGICapture not initialized. Call initialize() first.")

        # IDXGIOutputDuplication::AcquireNextFrame is at vtable index 8:
        # IUnknown(0-2) + IDXGIObject(3-6) + IDXGIOutputDuplication::GetDesc(7) +
        # AcquireNextFrame(8). Previous code used index 1 (IUnknown::AddRef),
        # which silently returned an int (refcount) instead of an HRESULT,
        # breaking frame acquisition.
        acquire_frame_fn = _com_call(
            8,
            HRESULT,
            ctypes.c_uint,
            ctypes.POINTER(DXGI_OUTDUPL_FRAME_INFO),
            ctypes.POINTER(ctypes.c_void_p),
        )

        # Retry loop: AccumulatedFrames=0 means no new desktop content has been
        # accumulated since DuplicateOutput was created. The acquired texture is
        # empty/black in this state. Retry until AccumulatedFrames > 0 to ensure
        # real desktop content.
        # Verified empirically: with AccumulatedFrames=0, CopyResource copies
        # an all-black texture; with AccumulatedFrames>0, it copies real
        # desktop content (min=0, max=255, mean≈100).
        for attempt in range(EMPTY_FRAME_MAX_RETRIES):
            # If a frame is held from a previous capture/error, recreate the
            # duplication to release it. ReleaseFrame crashes on this system
            # (see _recreate_duplication docstring), so we destroy the entire
            # IDXGIOutputDuplication and create a fresh one.
            if self._frame_held:
                if not self._recreate_duplication():
                    return None
                self._frame_held = False
                # Wait briefly for the desktop to accumulate changes before
                # calling AcquireNextFrame. Without this delay, the first
                # AcquireNextFrame after recreation returns AccumulatedFrames=0
                # (empty/black frame) because no desktop updates have occurred.
                time.sleep(RECREATE_SETTLE_TIME_SEC)

            frame_info = DXGI_OUTDUPL_FRAME_INFO()
            resource_ptr = ctypes.c_void_p()

            hr = acquire_frame_fn(
                self._output_dup,
                self._frame_timeout_ms,
                ctypes.byref(frame_info),
                ctypes.byref(resource_ptr),
            )

            if hr == DXGI_ERROR_WAIT_TIMEOUT:
                logger.debug("AcquireNextFrame timed out (%d ms)", self._frame_timeout_ms)
                return None

            if hr == DXGI_ERROR_ACCESS_LOST:
                logger.warning("Desktop Duplication access lost (mode change / fullscreen)")
                # Access lost means the dup is invalid — the frame is gone.
                # Recreate and retry.
                if not self._recreate_duplication():
                    return None
                time.sleep(RECREATE_SETTLE_TIME_SEC)
                continue

            if hr == DXGI_ERROR_INVALID_CALL:
                # Frame still held (shouldn't happen if _frame_held tracking
                # is correct, but handle it defensively). Recreate and retry.
                logger.debug("AcquireNextFrame: INVALID_CALL (frame held), recreating")
                if not self._recreate_duplication():
                    return None
                time.sleep(RECREATE_SETTLE_TIME_SEC)
                continue

            if hr == E_ACCESSDENIED:
                logger.debug("AcquireNextFrame returned ACCESS_DENIED")
                return None

            if hr != S_OK or not resource_ptr.value:
                logger.warning("AcquireNextFrame failed: 0x%08X", hr & 0xFFFFFFFF)
                return None

            # Frame acquired successfully (S_OK). Mark as held — will be
            # released via dup recreation on the next capture() call.
            self._frame_held = True

            # AccumulatedFrames=0: desktop hasn't changed since last acquire.
            # The texture is empty/black — release the IDXGIResource, then
            # recreate the dup (via _frame_held flag on next iteration) and
            # retry after a brief sleep to allow desktop updates to accumulate.
            if frame_info.AccumulatedFrames == 0:
                logger.debug(
                    "AcquireNextFrame returned empty frame (AccumulatedFrames=0), "
                    "retrying %d/%d",
                    attempt + 1, EMPTY_FRAME_MAX_RETRIES,
                )
                _com_release(resource_ptr.value)
                # _frame_held stays True — next iteration will recreate the dup
                continue

            # AccumulatedFrames > 0: real desktop content available.
            # Read pixels, then release the IDXGIResource. The frame remains
            # "held" by the dup until the next capture() call recreates it.
            try:
                return self._read_frame_pixels(resource_ptr.value)
            finally:
                _com_release(resource_ptr.value)

        # All retries exhausted with AccumulatedFrames=0 — desktop is idle
        logger.warning(
            "AcquireNextFrame returned empty frames for %d retries (desktop idle?)",
            EMPTY_FRAME_MAX_RETRIES,
        )
        return None

    def capture_window(self, hwnd: int) -> np.ndarray | None:
        """Capture a desktop frame cropped to the target window's rect (TD-124).

        Wraps ``capture()`` to return only the pixels belonging to the target
        window. Used by ``WindowsScreenshotHandler._capture_dxgi(hwnd)`` so
        DXGI captures the target window instead of the full desktop, allowing
        per-window capture in multi-window / multi-game scenarios.

        The window rect is translated to desktop-relative coordinates using
        ``DXGI_OUTPUT_DESC.DesktopCoordinates`` and then numpy-sliced from the
        full-desktop frame. Window pixels outside the desktop bounds are
        clipped (defensive against windows partially off-screen).

        Args:
            hwnd: Target window handle. If 0 or invalid, returns None.

        Returns:
            BGR numpy array with shape ``(window_height, window_width, 3)``
            cropped to the window rect, or None if:

            * hwnd is 0/invalid
            * GetWindowRect fails
            * window rect is empty or fully outside desktop
            * underlying ``capture()`` returns None
        """
        if not hwnd:
            return None

        # Get target window's screen coordinates via the extracted helper
        # (testable without touching ctypes.byref in tests).
        rect = self._get_window_rect(hwnd)
        if rect is None:
            return None

        win_left, win_top = rect.left, rect.top
        win_right, win_bottom = rect.right, rect.bottom

        if win_right <= win_left or win_bottom <= win_top:
            logger.debug(
                "Empty window rect for hwnd=%s: (%d,%d,%d,%d)",
                hwnd, win_left, win_top, win_right, win_bottom,
            )
            return None

        # Get desktop origin from DXGI_OUTPUT_DESC. If unavailable, assume (0, 0).
        desktop_left, desktop_top = 0, 0
        desktop_right = self._width
        desktop_bottom = self._height
        if self._output_desc:
            drect = self._output_desc.DesktopCoordinates
            desktop_left, desktop_top = drect.left, drect.top
            desktop_right, desktop_bottom = drect.right, drect.bottom

        # Translate window rect to desktop-relative coordinates and clip to
        # desktop bounds (window may extend beyond the monitor — e.g. shadow
        # borders on maximized windows).
        rel_left = max(0, win_left - desktop_left)
        rel_top = max(0, win_top - desktop_top)
        rel_right = min(self._width, win_right - desktop_left)
        rel_bottom = min(self._height, win_bottom - desktop_top)

        if rel_right <= rel_left or rel_bottom <= rel_top:
            logger.debug(
                "Window rect fully outside desktop for hwnd=%s: "
                "win=(%d,%d,%d,%d) desktop=(%d,%d,%d,%d)",
                hwnd, win_left, win_top, win_right, win_bottom,
                desktop_left, desktop_top, desktop_right, desktop_bottom,
            )
            return None

        # Capture full desktop frame, then slice to the window rect.
        frame = self.capture()
        if frame is None:
            return None

        return frame[rel_top:rel_bottom, rel_left:rel_right].copy()

    def _get_window_rect(self, hwnd: int) -> ctypes.wintypes.RECT | None:
        """Fetch the target window's screen coordinates via GetWindowRect.

        Extracted as a helper so tests can patch it without dealing with
        ``ctypes.byref`` plumbing. Returns None when GetWindowRect fails
        (invalid hwnd, window destroyed, etc.).

        Args:
            hwnd: Target window handle.

        Returns:
            Filled ``ctypes.wintypes.RECT`` instance, or None on failure.
        """
        rect = ctypes.wintypes.RECT()
        user32 = ctypes.windll.user32
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            logger.debug("GetWindowRect failed for hwnd=%s", hwnd)
            return None
        return rect

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
            "device_name": self._output_desc.DeviceName.rstrip("\x00"),
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

        # IDXGIOutput::GetDesc is at vtable index 7:
        # IUnknown(0-2) + IDXGIObject(3-6) + IDXGIOutput::GetDesc(7).
        # Previous code used index 4 (IDXGIObject::SetPrivateDataInterface),
        # which writes data instead of reading desc, corrupting COM state.
        # GetDesc returns HRESULT (not void); declaring restype=None masked
        # failures and returned a zeroed desc, producing 0x0 dimensions.
        get_desc_fn = _com_call(7, HRESULT, ctypes.POINTER(DXGI_OUTPUT_DESC))
        desc = DXGI_OUTPUT_DESC()
        try:
            hr = get_desc_fn(self._dxgi_output, ctypes.byref(desc))
            if hr != S_OK:
                logger.warning("IDXGIOutput::GetDesc failed: 0x%08X", hr & 0xFFFFFFFF)
                return None
            return desc
        except Exception as exc:
            logger.warning("IDXGIOutput::GetDesc failed: %s", exc)
            return None

    def _create_staging_texture(self, d3d11) -> None:
        """Create a CPU-readable staging texture for frame data transfer

        Creates a D3D11 Texture2D with Staging usage that allows CPU read access.
        This texture serves as the intermediate buffer between GPU desktop
        duplication output and CPU-accessible memory for numpy conversion.

        Args:
            d3d11: The d3d11 DLL module handle (unused now — CreateTexture2D is
                   a COM vtable method on ID3D11Device, not a DLL export).
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

        # ID3D11Device::CreateTexture2D is at vtable index 5:
        # IUnknown(0-2) + ID3D11Device::CreateBuffer(3) + CreateTexture1D(4) +
        # CreateTexture2D(5).
        # Signature: HRESULT(const D3D11_TEXTURE2D_DESC *pDesc,
        #                    const D3D11_SUBRESOURCE_DATA *pInitialData,
        #                    ID3D11Texture2D **ppTexture2D)
        # Previous code tried to resolve it as a DLL export named
        # "CreateTexture2D", which does not exist in d3d11.dll exports.
        create_texture_fn = _com_call(
            5, HRESULT,
            ctypes.POINTER(D3D11_TEXTURE2D_DESC),
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        )

        self._staging_texture = ctypes.c_void_p()
        hr = create_texture_fn(
            self._d3d11_device,
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

        Takes the GPU texture from AcquireNextFrame, copies it to the CPU-readable
        staging texture via CopyResource, then maps the staging texture and converts
        the raw BGRA pixel data to a BGR numpy array.

        Uses the D3D11 path (QI for ID3D11Texture2D → CopyResource → Map) rather
        than the IDXGISurface path, because QI for IID_IDXGISurface returns
        E_NOINTERFACE on the acquired resource (confirmed by diagnostic).

        Args:
            resource_ptr: Pointer to the IDXGIResource from AcquireNextFrame

        Returns:
            BGR numpy array (height, width, 3), or None on failure
        """
        qi_fn = _com_call(0, HRESULT, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))

        # QI the acquired IDXGIResource for ID3D11Texture2D. The underlying
        # desktop duplication texture is a D3D11 texture; QI for IDXGISurface
        # fails on this system, but QI for ID3D11Texture2D succeeds.
        tex_iid = _fill_guid(_uuid_to_guid(IID_ID3D11Texture2D))
        src_texture = ctypes.c_void_p()
        hr = qi_fn(resource_ptr, ctypes.byref(tex_iid), ctypes.byref(src_texture))

        if hr != S_OK or not src_texture.value:
            logger.warning(
                "Failed to QI acquired resource to ID3D11Texture2D: 0x%08X",
                hr & 0xFFFFFFFF,
            )
            return None

        try:
            # ID3D11DeviceContext::CopyResource is at vtable index 47
            # (verified via windows-rs ID3D11DeviceContext_Impl trait, which is
            # auto-generated from Microsoft's official win32metadata).
            # IUnknown(0-2) + ID3D11DeviceChild(3-6) + 40 ID3D11DeviceContext
            # methods precede CopyResource. Previous code used index 21
            # (DrawInstanced), which crashed with the wrong arg signature.
            # CopyResource returns void; declare restype=None to avoid reading
            # garbage as HRESULT.
            # Both src_texture (QI'd) and self._staging_texture (from
            # CreateTexture2D) are ID3D11Texture2D, which inherits from
            # ID3D11Resource — the interface CopyResource expects.
            copy_resource_fn = _com_call(
                47, None, ctypes.c_void_p, ctypes.c_void_p
            )
            copy_resource_fn(
                self._d3d11_context,
                self._staging_texture,
                src_texture,
            )

            # ID3D11DeviceContext::Map is at vtable index 14
            # (verified via windows-rs ID3D11DeviceContext_Impl trait):
            # IUnknown(0-2) + ID3D11DeviceChild(3-6) + VSSetConstantBuffers(7) +
            # PSSetShaderResources(8) + PSSetShader(9) + PSSetSamplers(10) +
            # VSSetShader(11) + DrawIndexed(12) + Draw(13) + Map(14).
            # Previous code used index 10 (PSSetSamplers) — wrong interface method.
            # Also fix prototype: Map takes 5 args (resource, subresource, mapType,
            # mapFlags, pMappedResource). The previous prototype was missing the
            # MapType arg, causing ctypes to misinterpret argument slots.
            map_fn = _com_call(
                14, HRESULT,
                ctypes.c_void_p,                                    # pResource
                ctypes.c_uint,                                      # Subresource
                ctypes.c_uint,                                      # MapType (D3D11_MAP enum)
                ctypes.c_uint,                                      # MapFlags
                ctypes.POINTER(D3D11_MAPPED_SUBRESOURCE),           # pMappedResource
            )
            mapped_sub = D3D11_MAPPED_SUBRESOURCE()
            hr = map_fn(
                self._d3d11_context,
                self._staging_texture,
                0,
                D3D11_MAP_READ,
                0,
                ctypes.byref(mapped_sub),
            )

            if hr != S_OK:
                logger.warning(
                    "ID3D11DeviceContext::Map(staging) failed: 0x%08X",
                    hr & 0xFFFFFFFF,
                )
                return None

            try:
                row_stride = mapped_sub.RowPitch // 4
                buf = (ctypes.c_ubyte * (mapped_sub.RowPitch * self._height)).from_address(
                    mapped_sub.pData
                )
                img = np.frombuffer(buf, dtype=np.uint8).reshape(
                    (self._height, row_stride, 4)
                )
                img_cropped = img[:, :self._width, :].copy()
                bgr = img_cropped[:, :, :3].copy()
                return bgr
            finally:
                # ID3D11DeviceContext::Unmap is at vtable index 15.
                # D3D11 Unmap takes only 2 args (resource, subresource) — the
                # extra MapFlags arg from D3D10 was removed. Previous code passed
                # 3 args with the wrong vtable index. Returns void → restype=None.
                unmap_fn = _com_call(
                    15, None,
                    ctypes.c_void_p,    # pResource
                    ctypes.c_uint,      # Subresource
                )
                unmap_fn(self._d3d11_context, self._staging_texture, 0)

        finally:
            _com_release(src_texture)

        return None

    def _release_frame_if_acquired(self) -> None:
        """No-op — ReleaseFrame crashes on this system.

        IDXGIOutputDuplication::ReleaseFrame (vtable 9) crashes with
        "access violation reading 0xFFFFFFFFFFFFFFFF" whenever a frame is
        held, regardless of AccumulatedFrames value. This was verified
        empirically (diag_release_v6.py): ReleaseFrame is safe when NO frame
        is held (returns DXGI_ERROR_INVALID_CALL), but crashes 100% of the
        time after a successful AcquireNextFrame.

        Instead of calling ReleaseFrame, we release the held frame by
        destroying the entire IDXGIOutputDuplication interface and creating
        a fresh one via DuplicateOutput. See _recreate_duplication().

        This method is kept as a no-op for backward compatibility with any
        callers that might still reference it.
        """
        return

    def _recreate_duplication(self) -> bool:
        """Release the current IDXGIOutputDuplication and create a new one.

        This is a workaround for a system/driver bug where
        IDXGIOutputDuplication::ReleaseFrame (vtable 9) crashes with
        "access violation reading 0xFFFFFFFFFFFFFFFF" whenever a frame is
        held. Instead of calling ReleaseFrame to release the held frame,
        we release the entire IDXGIOutputDuplication interface
        (IUnknown::Release) and call DuplicateOutput again to create a
        fresh one. The fresh duplication has no held frame.

        Verified empirically (diag_release_v6.py):
        - IUnknown::Release on the old dup works (no crash)
        - DuplicateOutput succeeds and returns a fresh, valid dup
        - The fresh dup passes QI for IID_IDXGIOutputDuplication
        - AcquireNextFrame on the fresh dup returns real content (AF>0)
          if the desktop has changed since DuplicateOutput

        Returns:
            True if recreation succeeded, False if DuplicateOutput failed
            (e.g., DXGI_ERROR_ALREADY_EXIST — another process holds the dup).
        """
        if not self._dxgi_output or not self._d3d11_device:
            logger.error("Cannot recreate duplication: _dxgi_output or _d3d11_device is None")
            return False

        # Release the old IDXGIOutputDuplication (IUnknown::Release).
        # This destroys the held frame implicitly — no ReleaseFrame needed.
        if self._output_dup:
            _com_release(
                self._output_dup.value
                if hasattr(self._output_dup, "value")
                else self._output_dup
            )
            self._output_dup = None

        # Create a fresh IDXGIOutputDuplication via DuplicateOutput (vtable 22).
        # See initialize() for vtable index derivation.
        dup_fn = _com_call(
            22, HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
        )
        self._output_dup = ctypes.c_void_p()
        hr = dup_fn(
            self._dxgi_output,
            self._d3d11_device,
            ctypes.byref(self._output_dup),
        )

        if hr == DXGI_ERROR_ALREADY_EXIST:
            logger.error("DuplicateOutput failed: already in use by another process")
            self._initialized = False
            return False
        if hr != S_OK or not self._output_dup.value:
            logger.error(
                "DuplicateOutput failed during recreate: 0x%08X",
                hr & 0xFFFFFFFF,
            )
            self._initialized = False
            return False

        return True

    def _cleanup_internal(self) -> None:
        """Internal cleanup helper that releases all COM resources in reverse order

        Releases resources in LIFO order: staging texture → output duplication →
        output → output1 → adapter → DXGI device → D3D11 context → D3D11 device
        → CoUninit.
        Each step uses try/except to ensure all resources are attempted even if
        one release fails.
        """
        if self._staging_texture:
            _com_release(self._staging_texture)
            self._staging_texture = None

        if self._output_dup:
            # ReleaseFrame is NOT called — it crashes on this system whenever
            # a frame is held (see _recreate_duplication docstring). Releasing
            # the IDXGIOutputDuplication interface (IUnknown::Release) destroys
            # the held frame implicitly.
            _com_release(self._output_dup)
            self._output_dup = None
        self._frame_held = False

        if self._dxgi_output:
            _com_release(self._dxgi_output)
            self._dxgi_output = None

        if self._dxgi_output1:
            _com_release(self._dxgi_output1)
            self._dxgi_output1 = None

        if self._dxgi_adapter:
            _com_release(self._dxgi_adapter)
            self._dxgi_adapter = None

        if self._dxgi_device:
            _com_release(self._dxgi_device)
            self._dxgi_device = None

        if self._d3d11_context:
            _com_release(self._d3d11_context)
            self._d3d11_context = None

        if self._d3d11_device:
            _com_release(self._d3d11_device)
            self._d3d11_device = None

        with contextlib.suppress(Exception):
            ctypes.windll.combase.CoUninitialize()

        self._output_desc = None
        self._width = 0
        self._height = 0
