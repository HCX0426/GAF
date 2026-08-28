"""P1-2 NemuIpc error code mapping unit tests.

Tests platforms.windows.nemu_ipc_errors:
- NEMU_IPC_ERROR_CODES dict covers documented Windows RPC_S_* codes
- format_nemu_error(): success / known / unknown / with-context / no-context
- is_recoverable_error(): 0, recoverable codes, non-recoverable codes
- is_emulator_booting(): 1745 only
- get_error_recovery_hint(): known / unknown
"""
import pytest
from platforms.windows.nemu_ipc_errors import (
    NEMU_IPC_ERROR_CODES,
    format_nemu_error,
    get_error_recovery_hint,
    is_emulator_booting,
    is_recoverable_error,
)

pytestmark = pytest.mark.e2e


class TestErrorCodesDict:
    """NEMU_IPC_ERROR_CODES dict coverage."""

    def test_dict_is_non_empty(self):
        assert len(NEMU_IPC_ERROR_CODES) >= 9

    def test_dict_contains_primary_codes(self):
        # Primary codes called out in P1-2 spec.
        for code in (1722, 1726, 1745, 1783):
            assert code in NEMU_IPC_ERROR_CODES
            assert isinstance(NEMU_IPC_ERROR_CODES[code], str)
            assert NEMU_IPC_ERROR_CODES[code]  # non-empty

    def test_dict_contains_secondary_codes(self):
        # Secondary codes from the Windows RPC_S_* family.
        for code in (1702, 1703, 1717, 1721, 1750):
            assert code in NEMU_IPC_ERROR_CODES

    def test_dict_values_are_strings(self):
        for v in NEMU_IPC_ERROR_CODES.values():
            assert isinstance(v, str)


class TestFormatNemuError:
    """format_nemu_error() formatting."""

    def test_success_code_returns_success(self):
        assert format_nemu_error(0) == "success"

    def test_success_with_context_still_success(self):
        # Context is suppressed on success for cleaner logs.
        assert format_nemu_error(0, context="nemu_connect") == "success"

    def test_known_code_without_context(self):
        msg = format_nemu_error(1722)
        assert "1722" in msg
        assert "RPC server unavailable" in msg

    def test_known_code_with_context(self):
        msg = format_nemu_error(1783, context="nemu_capture_display")
        assert "nemu_capture_display" in msg
        assert "1783" in msg
        assert "invalid binding" in msg.lower()

    def test_unknown_code_without_context(self):
        msg = format_nemu_error(99999)
        assert "99999" in msg
        assert "unknown" in msg.lower()

    def test_unknown_code_with_context(self):
        msg = format_nemu_error(42, context="nemu_connect")
        assert "nemu_connect" in msg
        assert "42" in msg

    def test_negative_code_treated_as_unknown(self):
        # Sentinel codes returned by make_ping_fn on timeout/exception.
        msg = format_nemu_error(-1)
        assert "-1" in msg

    @pytest.mark.parametrize("code", [1722, 1726, 1745, 1783, 1702, 1703, 1717, 1721, 1750])
    def test_all_known_codes_format_with_code(self, code):
        msg = format_nemu_error(code)
        assert f"code={code}" in msg


class TestIsRecoverableError:
    """is_recoverable_error() classification."""

    def test_zero_is_not_recoverable(self):
        assert is_recoverable_error(0) is False

    @pytest.mark.parametrize("code", [1722, 1726, 1745, 1783, 1717, 1721])
    def test_recoverable_codes(self, code):
        assert is_recoverable_error(code) is True

    @pytest.mark.parametrize("code", [1702, 1703, 1750])
    def test_non_recoverable_known_codes(self, code):
        # These indicate permanent misconfiguration, not transient failure.
        assert is_recoverable_error(code) is False

    def test_unknown_code_not_recoverable(self):
        assert is_recoverable_error(99999) is False

    def test_negative_sentinel_not_recoverable(self):
        # -1 (timeout) / -2 (exception) from keepalive pings — these are
        # sentinel values, not real RPC error codes; recovery logic should
        # not treat them as disconnect triggers.
        assert is_recoverable_error(-1) is False
        assert is_recoverable_error(-2) is False


class TestIsEmulatorBooting:
    """is_emulator_booting() classification."""

    def test_1745_indicates_booting(self):
        assert is_emulator_booting(1745) is True

    @pytest.mark.parametrize("code", [0, 1722, 1726, 1783, 1702, 1717, 99999])
    def test_other_codes_not_booting(self, code):
        assert is_emulator_booting(code) is False


class TestGetErrorRecoveryHint:
    """get_error_recovery_hint() user-facing hints."""

    @pytest.mark.parametrize("code", [1722, 1726, 1745, 1783, 1717, 1721])
    def test_known_codes_return_hint(self, code):
        hint = get_error_recovery_hint(code)
        assert hint is not None
        assert isinstance(hint, str)
        assert len(hint) > 10  # meaningful message, not a single word

    def test_unknown_code_returns_none(self):
        assert get_error_recovery_hint(99999) is None

    def test_zero_returns_none(self):
        assert get_error_recovery_hint(0) is None

    def test_hint_for_1722_mentions_emulator_running(self):
        hint = get_error_recovery_hint(1722)
        assert "running" in hint.lower() or "nemu_folder" in hint.lower()

    def test_hint_for_1745_mentions_booting(self):
        hint = get_error_recovery_hint(1745)
        assert "boot" in hint.lower()
