"""Minimal COM delegate vtable builder for WinRT event callbacks.

Ports the core pattern from ok-script's rotypes/delegate.py + idldsl.py:
builds a ctypes COM object with a vtable (QueryInterface / AddRef / Release
/ Invoke) that the WinRT runtime can call back into. Also implements the
WinRT parameterized IID computation (SHA-1 over a fixed namespace GUID +
signature string, with version/variant byte fix-ups).

This is a self-contained, minimal implementation — it does NOT depend on
the full ok-script rotypes framework. It provides just enough to register
a TypedEventHandler<TSender, TResult> delegate for WGC's FrameArrived
event.

Reference:
    open-source-ref/ok-script/ok/rotypes/delegate.py   (vtable builder)
    open-source-ref/ok-script/ok/rotypes/idldsl.py     (parameterized IID)
    open-source-ref/ok-script/ok/rotypes/Windows/Foundation/__init__.py
"""

from __future__ import annotations

import ctypes
import hashlib
import logging
import traceback
import uuid as _uuid
from collections.abc import Callable

logger = logging.getLogger(__name__)

# ── COM constants ───────────────────────────────────────────────────────

S_OK = 0
E_NOINTERFACE = 0x80004002
E_FAIL = 0x80004005

HRESULT = ctypes.c_long
ULONG = ctypes.c_ulong

# IID of IUnknown: {00000000-0000-0000-C000-000000000046}
IID_IUNKNOWN_BYTES = _uuid.UUID("{00000000-0000-0000-C000-000000000046}").bytes_le

# IID of IAgileObject: {94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90}
# WinRT queries for this on delegates to determine if they are agile
# (free-threaded). Answering yes lets WinRT call Invoke on any thread.
IID_IAGILE_OBJECT_BYTES = _uuid.UUID("{94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90}").bytes_le

# ── WinRT parameterized IID computation ─────────────────────────────────
#
# WinRT computes concrete IIDs for parameterized interfaces (generics) by
# SHA-1 hashing a signature string prefixed with a fixed 16-byte namespace
# GUID, then fixing the version (byte 6 → 0x50) and variant (byte 8 → 0x80)
# bits to produce a valid RFC 4122 v5 UUID.
#
# Reference: ok-script/rotypes/idldsl.py generate_parameterized_attrs()

# The fixed 16-byte namespace GUID for WinRT parameterized IIDs.
_PIID_NAMESPACE = b"\x11\xF4\x7a\xD5\x7b\x73\x42\xC0\xAB\xAE\x87\x8B\x1E\x16\xAD\xEE"

# PIID (parameterized interface ID) for Windows.Foundation.TypedEventHandler<T, U>.
# This is the canonical WinRT PIID, NOT a concrete IID — the concrete IID is
# computed from it via SHA-1.
PIID_TYPED_EVENT_HANDLER = "9c92b687-6ac1-11e0-84e1-18a905bcc53f"

# Type signature strings for WinRT types used by WGC FrameArrived.
# Reference: ok-script/rotypes/idldsl.py _get_type_signature()
#
# IInspectable: {af86e2e0-b12d-4c6a-9c5a-d7aa65101e90}
_SIG_IINSPECTABLE = "{af86e2e0-b12d-4c6a-9c5a-d7aa65101e90}"

# Direct3D11CaptureFramePool runtime class:
#   rc(Windows.Graphics.Capture.Direct3D11CaptureFramePool;{iid})
_SIG_D3D11_CAPTURE_FRAME_POOL = (
    "rc(Windows.Graphics.Capture.Direct3D11CaptureFramePool;"
    "{24eb6d22-1975-422e-82e7-780dbd8ddf24})"
)

# GraphicsCaptureItem runtime class:
#   rc(Windows.Graphics.Capture.GraphicsCaptureItem;{iid})
_SIG_GRAPHICS_CAPTURE_ITEM = (
    "rc(Windows.Graphics.Capture.GraphicsCaptureItem;"
    "{79c3f95b-31f7-4ec2-a464-632ef5d30760})"
)


def _fix_uuid_version_variant(digest16: bytes) -> str:
    """Fix version/variant bytes in a 16-byte SHA-1 digest and format as UUID.

    Per RFC 4122 §4.3 (v5 UUID):
    - Byte 6: set high nibble to 0101 (version 5)
    - Byte 8: set high bits to 10 (variant 1)
    """
    b = bytearray(digest16)
    b[6] = (b[6] & 0x0F) | 0x50  # version 5
    b[8] = (b[8] & 0x3F) | 0x80  # variant 1
    return "{:02x}{:02x}{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}".format(*tuple(b))


def compute_parameterized_iid(piid: str, type_sigs: tuple[str, ...]) -> str:
    """Compute a concrete WinRT IID from a parameterized interface ID + type signatures.

    Args:
        piid: The parameterized interface ID string (e.g. TypedEventHandler PIID).
        type_sigs: Tuple of WinRT type signature strings for the generic args.

    Returns:
        The computed IID as a lowercase UUID string.
    """
    sig = "pinterface({{{}}};{})".format(piid, ";".join(type_sigs))
    sha1 = hashlib.sha1()
    sha1.update(_PIID_NAMESPACE)
    sha1.update(sig.encode("utf-8"))
    return _fix_uuid_version_variant(sha1.digest()[:16])


def compute_typed_event_handler_iid(sender_sig: str, result_sig: str) -> str:
    """Compute the concrete IID for TypedEventHandler<TSender, TResult>.

    Args:
        sender_sig: WinRT type signature for the sender generic arg.
        result_sig: WinRT type signature for the result generic arg.

    Returns:
        The computed IID as a lowercase UUID string.
    """
    return compute_parameterized_iid(PIID_TYPED_EVENT_HANDLER, (sender_sig, result_sig))


# Pre-computed IIDs for the WGC FrameArrived and Closed event handlers.
# TypedEventHandler<Direct3D11CaptureFramePool, IInspectable>
IID_FRAME_ARRIVED_HANDLER = compute_typed_event_handler_iid(
    _SIG_D3D11_CAPTURE_FRAME_POOL, _SIG_IINSPECTABLE,
)
# TypedEventHandler<GraphicsCaptureItem, IInspectable>
IID_CLOSED_HANDLER = compute_typed_event_handler_iid(
    _SIG_GRAPHICS_CAPTURE_ITEM, _SIG_IINSPECTABLE,
)


# ── COM delegate vtable construction ────────────────────────────────────
#
# A WinRT delegate is a COM object with a 4-slot vtable:
#   0: QueryInterface(IID*, void**)
#   1: AddRef() -> ULONG
#   2: Release() -> ULONG
#   3: Invoke(...) — signature depends on the delegate type
#
# We build this entirely from ctypes Structures so WinRT can call back into
# Python. A module-level _refmap keeps Python references alive for the
# lifetime of the delegate (preventing GC of the closures).

_typeof_QueryInterface = ctypes.WINFUNCTYPE(
    HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
)
_typeof_AddRef = ctypes.WINFUNCTYPE(ULONG, ctypes.c_void_p)
_typeof_Release = ctypes.WINFUNCTYPE(ULONG, ctypes.c_void_p)


class _DelegateVtbl(ctypes.Structure):
    """vtable layout for a WinRT delegate (IUnknown + Invoke)."""
    _fields_ = [
        ("QueryInterface", _typeof_QueryInterface),
        ("AddRef", _typeof_AddRef),
        ("Release", _typeof_Release),
        ("Invoke", ctypes.c_void_p),
    ]


class _Delegate(ctypes.Structure):
    """COM object: a pointer to the vtable."""
    _fields_ = [("vtbl", ctypes.POINTER(_DelegateVtbl))]


# Module-level ref map: raw pointer value (int) -> [keepref_tuple, refcount]
# The keepref tuple holds all ctypes objects + the Python callback so they
# are not garbage-collected while WinRT holds the delegate pointer.
_refmap: dict = {}


# WINFUNCTYPE prototype for TypedEventHandler.Invoke.
# Signature: HRESULT Invoke(this, IInspectable* sender, IInspectable* result)
# All args are opaque pointers (c_void_p) — the callback typically ignores them.
TYPED_EVENT_HANDLER_INVOKE_PROTO = ctypes.WINFUNCTYPE(
    HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
)


def create_typed_event_handler_delegate(
    delegate_iid_str: str,
    callback: Callable[[], None],
) -> int:
    """Build a TypedEventHandler COM delegate that calls callback on Invoke.

    The delegate implements IUnknown (QI/AddRef/Release) + Invoke. WinRT
    calls Invoke(sender, result) on a thread-pool thread when the event
    fires; we dispatch to the Python callback (which receives no args).

    The delegate is "agile" — QueryInterface answers IAgileObject so WinRT
    knows it can call Invoke on any thread.

    Args:
        delegate_iid_str: The concrete delegate IID (from
            compute_typed_event_handler_iid) as a UUID string. Used for QI.
        callback: Zero-arg Python callable invoked on each event.

    Returns:
        Raw pointer value (int) to the delegate COM object. Pass this to
        add_FrameArrived / add_Closed. Keep the return value alive (or
        let the _refmap manage it) — do NOT let it be GC'd while WinRT
        holds the delegate.
    """
    delegate_iid_bytes = _uuid.UUID(delegate_iid_str).bytes_le

    vtbl = _DelegateVtbl()

    def impl_AddRef(this: int) -> int:
        entry = _refmap.get(this)
        if entry is not None:
            entry[1] += 1
            return entry[1]
        return 1

    def impl_QueryInterface(this: int, refiid: int, ppunk) -> int:
        try:
            want = ctypes.string_at(refiid, 16)
            if want in (IID_IUNKNOWN_BYTES, IID_IAGILE_OBJECT_BYTES, delegate_iid_bytes):
                impl_AddRef(this)
                ppunk[0] = this
                return S_OK
            ppunk[0] = None
            return E_NOINTERFACE
        except Exception:
            return E_FAIL

    def impl_Release(this: int) -> int:
        entry = _refmap.get(this)
        if entry is not None:
            entry[1] -= 1
            refcnt = entry[1]
            if refcnt <= 0:
                del _refmap[this]
            return max(refcnt, 0)
        return 0

    def impl_Invoke(this: int, sender: int, result: int) -> int:
        try:
            callback()
            return S_OK
        except Exception:
            logger.error("TypedEventHandler Invoke exception:\n%s", traceback.format_exc())
            return E_FAIL

    invoke_cb = TYPED_EVENT_HANDLER_INVOKE_PROTO(impl_Invoke)

    vtbl.QueryInterface = _typeof_QueryInterface(impl_QueryInterface)
    vtbl.AddRef = _typeof_AddRef(impl_AddRef)
    vtbl.Release = _typeof_Release(impl_Release)
    vtbl.Invoke = ctypes.cast(invoke_cb, ctypes.c_void_p)

    obj = _Delegate()
    obj.vtbl = ctypes.pointer(vtbl)
    objptr = ctypes.pointer(obj)
    objptrval = ctypes.cast(objptr, ctypes.c_void_p).value

    # Keep all ctypes objects + callback alive for the delegate's lifetime.
    keepref = (objptr, obj, vtbl, invoke_cb, callback)
    _refmap[objptrval] = [keepref, 1]
    logger.debug("Created COM delegate ptr=%#x iid=%s", objptrval, delegate_iid_str)
    return objptrval


def release_delegate(ptr: int) -> None:
    """Release a delegate created by create_typed_event_handler_delegate.

    Removes the delegate from _refmap, allowing Python to GC the ctypes
    objects and callback. Call this ONLY after remove_FrameArrived has
    unregistered the delegate from WinRT.
    """
    if ptr and ptr in _refmap:
        del _refmap[ptr]
        logger.debug("Released COM delegate ptr=%#x", ptr)


def is_delegate_alive(ptr: int) -> bool:
    """Check whether a delegate pointer is still in the refmap (alive)."""
    return ptr is not None and ptr in _refmap
