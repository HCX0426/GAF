"""Unit tests for the minimal COM delegate vtable builder (_com_delegate.py).

Verifies:
    - WinRT parameterized IID computation (SHA-1 + version/variant fix-ups)
    - COM delegate vtable construction (QueryInterface / AddRef / Release / Invoke)
    - Delegate lifecycle (_refmap, release_delegate, is_delegate_alive)
"""

import ctypes
import uuid as _uuid

import pytest
from platforms.windows import _com_delegate
from platforms.windows._com_delegate import (
    E_FAIL,
    E_NOINTERFACE,
    IID_CLOSED_HANDLER,
    IID_FRAME_ARRIVED_HANDLER,
    PIID_TYPED_EVENT_HANDLER,
    S_OK,
    _refmap,
    compute_parameterized_iid,
    compute_typed_event_handler_iid,
    create_typed_event_handler_delegate,
    is_delegate_alive,
    release_delegate,
)

pytestmark = pytest.mark.unit

# ── IID computation ───────────────────────────────────────────────────────


class TestIIDComputation:
    """WinRT parameterized IID computation (SHA-1 + RFC 4122 v5 fix-ups)."""

    def test_typed_event_handler_piid_is_canonical(self):
        """PIID for TypedEventHandler must match the canonical WinRT value."""
        assert PIID_TYPED_EVENT_HANDLER == "9c92b687-6ac1-11e0-84e1-18a905bcc53f"

    def test_compute_parameterized_iid_returns_lowercase_uuid_string(self):
        """Output must be a 36-char lowercase UUID string with hyphens."""
        iid = compute_parameterized_iid(
            PIID_TYPED_EVENT_HANDLER,
            ("{af86e2e0-b12d-4c6a-9c5a-d7aa65101e90}",),
        )
        assert isinstance(iid, str)
        assert len(iid) == 36
        # 8-4-4-4-12 hex groups separated by hyphens
        parts = iid.split("-")
        assert len(parts) == 5
        assert all(len(p) == n for p, n in zip(parts, (8, 4, 4, 4, 12), strict=False))
        # All lowercase hex
        assert iid == iid.lower()
        _uuid.UUID(iid)  # raises if invalid

    def test_compute_parameterized_iid_is_deterministic(self):
        """Same input must always produce the same IID."""
        iid1 = compute_parameterized_iid(
            PIID_TYPED_EVENT_HANDLER,
            ("{af86e2e0-b12d-4c6a-9c5a-d7aa65101e90}",),
        )
        iid2 = compute_parameterized_iid(
            PIID_TYPED_EVENT_HANDLER,
            ("{af86e2e0-b12d-4c6a-9c5a-d7aa65101e90}",),
        )
        assert iid1 == iid2

    def test_compute_parameterized_iid_differs_for_different_type_sigs(self):
        """Different type signatures must produce different IIDs."""
        iid_a = compute_parameterized_iid(
            PIID_TYPED_EVENT_HANDLER,
            ("{af86e2e0-b12d-4c6a-9c5a-d7aa65101e90}",),
        )
        iid_b = compute_parameterized_iid(
            PIID_TYPED_EVENT_HANDLER,
            ("{24eb6d22-1975-422e-82e7-780dbd8ddf24}",),
        )
        assert iid_a != iid_b

    def test_compute_parameterized_iid_version_byte_is_5(self):
        """Byte 6 high nibble must be 5 (RFC 4122 v5 UUID)."""
        iid = compute_parameterized_iid(
            PIID_TYPED_EVENT_HANDLER,
            ("{af86e2e0-b12d-4c6a-9c5a-d7aa65101e90}",),
        )
        # 13th hex char (index 12 in the formatted string) encodes version.
        assert iid[14] == "5"

    def test_compute_parameterized_iid_variant_byte_is_8_or_9_or_a_or_b(self):
        """Byte 8 high bits must be 10 (variant 1) — hex char 16 ∈ {8,9,a,b}."""
        iid = compute_parameterized_iid(
            PIID_TYPED_EVENT_HANDLER,
            ("{af86e2e0-b12d-4c6a-9c5a-d7aa65101e90}",),
        )
        assert iid[19] in ("8", "9", "a", "b")

    def test_compute_typed_event_handler_iid_wrapper(self):
        """compute_typed_event_handler_iid must produce the same result as the direct call."""
        sender_sig = "{af86e2e0-b12d-4c6a-9c5a-d7aa65101e90}"
        result_sig = "{24eb6d22-1975-422e-82e7-780dbd8ddf24}"
        wrapped = compute_typed_event_handler_iid(sender_sig, result_sig)
        direct = compute_parameterized_iid(
            PIID_TYPED_EVENT_HANDLER, (sender_sig, result_sig),
        )
        assert wrapped == direct

    def test_iid_frame_arrived_handler_is_valid_uuid(self):
        """IID_FRAME_ARRIVED_HANDLER must be a valid UUID string."""
        _uuid.UUID(IID_FRAME_ARRIVED_HANDLER)

    def test_iid_closed_handler_is_valid_uuid(self):
        """IID_CLOSED_HANDLER must be a valid UUID string."""
        _uuid.UUID(IID_CLOSED_HANDLER)

    def test_frame_arrived_and_closed_iids_differ(self):
        """FrameArrived and Closed handler IIDs must differ (different sender types)."""
        assert IID_FRAME_ARRIVED_HANDLER != IID_CLOSED_HANDLER


# ── Delegate vtable construction & lifecycle ──────────────────────────────


class TestDelegateLifecycle:
    """COM delegate construction, _refmap tracking, release."""

    def setup_method(self):
        """Snapshot _refmap so each test starts clean."""
        self._saved_refmap = dict(_refmap)
        _refmap.clear()

    def teardown_method(self):
        """Restore _refmap so tests don't leak delegates."""
        _refmap.clear()
        _refmap.update(self._saved_refmap)

    def test_create_delegate_returns_nonzero_int(self):
        """create_typed_event_handler_delegate must return a non-zero pointer int."""
        ptr = create_typed_event_handler_delegate(
            IID_FRAME_ARRIVED_HANDLER, lambda: None,
        )
        assert isinstance(ptr, int)
        assert ptr != 0

    def test_create_delegate_registers_in_refmap(self):
        """After creation, the delegate must be in _refmap and alive."""
        ptr = create_typed_event_handler_delegate(
            IID_FRAME_ARRIVED_HANDLER, lambda: None,
        )
        assert ptr in _refmap
        assert is_delegate_alive(ptr)

    def test_create_delegate_keeps_callback_alive(self):
        """The _refmap entry must hold a reference to the callback closure."""
        sentinel = []
        cb = lambda: sentinel.append(1)  # noqa: E731
        ptr = create_typed_event_handler_delegate(IID_FRAME_ARRIVED_HANDLER, cb)
        keepref = _refmap[ptr][0]
        # keepref is a tuple (objptr, obj, vtbl, invoke_cb, callback)
        assert cb in keepref or any(c is cb for c in keepref)

    def test_release_delegate_removes_from_refmap(self):
        """release_delegate must remove the delegate from _refmap."""
        ptr = create_typed_event_handler_delegate(
            IID_FRAME_ARRIVED_HANDLER, lambda: None,
        )
        assert is_delegate_alive(ptr)
        release_delegate(ptr)
        assert not is_delegate_alive(ptr)
        assert ptr not in _refmap

    def test_release_delegate_is_noop_for_unknown_ptr(self):
        """release_delegate must not raise for a ptr not in _refmap."""
        # Should not raise.
        release_delegate(0)
        release_delegate(0xDEADBEEF)

    def test_is_delegate_alive_returns_false_for_unknown(self):
        """is_delegate_alive must return False for unknown / null pointers."""
        assert is_delegate_alive(0) is False
        assert is_delegate_alive(0xDEADBEEF) is False
        assert is_delegate_alive(None) is False


# ── COM vtable call behavior ──────────────────────────────────────────────


class TestDelegateVtableCalls:
    """Calling the delegate's COM vtable slots (QI / AddRef / Release / Invoke)."""

    setup_method = TestDelegateLifecycle.setup_method
    teardown_method = TestDelegateLifecycle.teardown_method

    def _get_vtbl(self, ptr):
        """Return the _DelegateVtbl pointed to by the delegate COM object."""
        # _Delegate is { c_void_p vtbl; } — vtbl[0] is the pointer to _DelegateVtbl.
        obj_ptr = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))
        vtbl_ptr = obj_ptr[0]
        vtbl = ctypes.cast(vtbl_ptr, ctypes.POINTER(_com_delegate._DelegateVtbl)).contents
        return vtbl

    def test_invoke_calls_callback(self):
        """Calling the Invoke slot must call the Python callback."""
        called = []
        ptr = create_typed_event_handler_delegate(
            IID_FRAME_ARRIVED_HANDLER, lambda: called.append(1),
        )
        vtbl = self._get_vtbl(ptr)
        # Invoke signature: HRESULT Invoke(this, sender, result)
        invoke_fn = _com_delegate.TYPED_EVENT_HANDLER_INVOKE_PROTO(vtbl.Invoke)
        hr = invoke_fn(ptr, 0, 0)
        assert hr == S_OK
        assert called == [1]

    def test_invoke_returns_e_fail_on_exception(self):
        """If the callback raises, Invoke must return E_FAIL (no exception escapes)."""
        def boom():
            raise ValueError("kaboom")

        ptr = create_typed_event_handler_delegate(IID_FRAME_ARRIVED_HANDLER, boom)
        vtbl = self._get_vtbl(ptr)
        invoke_fn = _com_delegate.TYPED_EVENT_HANDLER_INVOKE_PROTO(vtbl.Invoke)
        hr = invoke_fn(ptr, 0, 0)
        # HRESULT is c_long (signed); compare as unsigned 32-bit.
        assert (hr & 0xFFFFFFFF) == E_FAIL

    def test_query_interface_returns_iunknown(self):
        """QI for IUnknown must return S_OK and set the out pointer to the delegate."""
        ptr = create_typed_event_handler_delegate(
            IID_FRAME_ARRIVED_HANDLER, lambda: None,
        )
        vtbl = self._get_vtbl(ptr)
        # QI signature: HRESULT QI(this, REFIID, void**)
        qi_fn = _com_delegate._typeof_QueryInterface(vtbl.QueryInterface)
        out = ctypes.c_void_p(0)
        iid_unknown = _com_delegate.IID_IUNKNOWN_BYTES
        refiid = ctypes.create_string_buffer(iid_unknown)
        hr = qi_fn(ptr, refiid, ctypes.byref(out))
        assert hr == S_OK
        assert out.value == ptr  # QI for IUnknown returns self

    def test_query_interface_returns_iagile_object(self):
        """QI for IAgileObject must return S_OK (delegate is free-threaded)."""
        ptr = create_typed_event_handler_delegate(
            IID_FRAME_ARRIVED_HANDLER, lambda: None,
        )
        vtbl = self._get_vtbl(ptr)
        qi_fn = _com_delegate._typeof_QueryInterface(vtbl.QueryInterface)
        out = ctypes.c_void_p(0)
        iid_agile = _com_delegate.IID_IAGILE_OBJECT_BYTES
        refiid = ctypes.create_string_buffer(iid_agile)
        hr = qi_fn(ptr, refiid, ctypes.byref(out))
        assert hr == S_OK
        assert out.value == ptr

    def test_query_interface_returns_delegate_iid(self):
        """QI for the delegate's own concrete IID must return S_OK."""
        ptr = create_typed_event_handler_delegate(
            IID_FRAME_ARRIVED_HANDLER, lambda: None,
        )
        vtbl = self._get_vtbl(ptr)
        qi_fn = _com_delegate._typeof_QueryInterface(vtbl.QueryInterface)
        out = ctypes.c_void_p(0)
        iid_delegate = _uuid.UUID(IID_FRAME_ARRIVED_HANDLER).bytes_le
        refiid = ctypes.create_string_buffer(iid_delegate)
        hr = qi_fn(ptr, refiid, ctypes.byref(out))
        assert hr == S_OK
        assert out.value == ptr

    def test_query_interface_returns_e_nointerface_for_unknown_iid(self):
        """QI for an unrelated IID must return E_NOINTERFACE and null out pointer."""
        ptr = create_typed_event_handler_delegate(
            IID_FRAME_ARRIVED_HANDLER, lambda: None,
        )
        vtbl = self._get_vtbl(ptr)
        qi_fn = _com_delegate._typeof_QueryInterface(vtbl.QueryInterface)
        out = ctypes.c_void_p(0)
        # Use an arbitrary UUID that is not IUnknown / IAgileObject / delegate IID.
        bogus_iid = _uuid.UUID("{11111111-2222-3333-4444-555555555555}").bytes_le
        refiid = ctypes.create_string_buffer(bogus_iid)
        hr = qi_fn(ptr, refiid, ctypes.byref(out))
        # HRESULT is c_long (signed); compare as unsigned 32-bit.
        assert (hr & 0xFFFFFFFF) == E_NOINTERFACE
        assert out.value in (None, 0)

    def test_addref_increments_refcount(self):
        """AddRef must return the incremented refcount."""
        ptr = create_typed_event_handler_delegate(
            IID_FRAME_ARRIVED_HANDLER, lambda: None,
        )
        vtbl = self._get_vtbl(ptr)
        addref_fn = _com_delegate._typeof_AddRef(vtbl.AddRef)
        rc1 = addref_fn(ptr)
        rc2 = addref_fn(ptr)
        assert rc1 == 2  # starts at 1, AddRef -> 2
        assert rc2 == 3

    def test_release_decrements_refcount(self):
        """Release must return the decremented refcount (without dropping to 0)."""
        ptr = create_typed_event_handler_delegate(
            IID_FRAME_ARRIVED_HANDLER, lambda: None,
        )
        vtbl = self._get_vtbl(ptr)
        # First AddRef to bump refcount to 2 so Release doesn't free it.
        addref_fn = _com_delegate._typeof_AddRef(vtbl.AddRef)
        addref_fn(ptr)
        release_fn = _com_delegate._typeof_Release(vtbl.Release)
        rc = release_fn(ptr)
        assert rc == 1  # back to initial refcount
        # Delegate must still be alive (refcount > 0).
        assert is_delegate_alive(ptr)

    def test_release_to_zero_removes_from_refmap(self):
        """Release that drops refcount to 0 must remove the delegate from _refmap."""
        ptr = create_typed_event_handler_delegate(
            IID_FRAME_ARRIVED_HANDLER, lambda: None,
        )
        vtbl = self._get_vtbl(ptr)
        release_fn = _com_delegate._typeof_Release(vtbl.Release)
        rc = release_fn(ptr)
        assert rc == 0
        assert not is_delegate_alive(ptr)
