"""Windows input_variants compatibility and enum tests.

After TD-090 cleanup, this module only tests:
- Win32InputMethod enum completeness (9 variants)
- Introspection helpers: list_available_variants / list_all_variants /
  get_variant_description / get_variant_info
- INPUT_COMPATIBILITY_TABLE correctness
- Query functions: recommend_input_method / recommend_legacy_input_method /
  get_blocked_input_methods / get_compatibility_reason /
  is_input_method_compatible / get_compatibility_info

The 9 InputVariant subclasses and create_input_variant factory were removed
because they were dead code (only exercised by tests, never used in production).
"""

import sys
from pathlib import Path

# Ensure src on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from platforms.windows.input_variants import (
    INPUT_COMPATIBILITY_TABLE,
    Win32InputMethod,
    get_blocked_input_methods,
    get_compatibility_info,
    get_compatibility_reason,
    get_variant_description,
    get_variant_info,
    is_input_method_compatible,
    list_all_variants,
    list_available_variants,
    recommend_input_method,
    recommend_legacy_input_method,
)

pytestmark = pytest.mark.unit

# ============================================================
# Enum completeness
# ============================================================

class TestWin32InputMethodEnum:
    """Win32InputMethod enum must define exactly 9 variants."""

    def test_enum_has_9_variants(self):
        assert len(list(Win32InputMethod)) == 9

    def test_enum_values_unique(self):
        values = [m.value for m in Win32InputMethod]
        assert len(values) == len(set(values))

    def test_enum_contains_all_expected_methods(self):
        expected = {
            "seize", "send_message", "post_message", "legacy_event",
            "send_message_cursor_pos", "post_message_cursor_pos",
            "send_message_window_pos", "post_message_window_pos",
            "post_thread_message",
        }
        actual = {m.value for m in Win32InputMethod}
        assert actual == expected

    def test_post_thread_message_is_deprecated(self):
        assert Win32InputMethod.POST_THREAD_MESSAGE.is_deprecated is True

    def test_only_post_thread_message_is_deprecated(self):
        deprecated = [m for m in Win32InputMethod if m.is_deprecated]
        assert deprecated == [Win32InputMethod.POST_THREAD_MESSAGE]

    def test_foreground_methods(self):
        """SEIZE and LEGACY_EVENT require foreground; others are background-safe."""
        assert Win32InputMethod.SEIZE.is_foreground is True
        assert Win32InputMethod.LEGACY_EVENT.is_foreground is True
        assert Win32InputMethod.POST_MESSAGE.is_foreground is False
        assert Win32InputMethod.SEND_MESSAGE.is_foreground is False

    def test_background_methods(self):
        """Background methods = not foreground."""
        assert Win32InputMethod.POST_MESSAGE.is_background is True
        assert Win32InputMethod.SEIZE.is_background is False


# ============================================================
# Introspection helpers
# ============================================================

class TestIntrospectionHelpers:
    """list_available_variants / list_all_variants / get_variant_description / get_variant_info."""

    def test_list_available_variants_excludes_deprecated(self):
        available = list_available_variants()
        assert Win32InputMethod.POST_THREAD_MESSAGE not in available
        assert len(available) == 8  # 9 total - 1 deprecated

    def test_list_all_variants_includes_deprecated(self):
        all_variants = list_all_variants()
        assert Win32InputMethod.POST_THREAD_MESSAGE in all_variants
        assert len(all_variants) == 9

    def test_get_variant_description_returns_string(self):
        for method in Win32InputMethod:
            desc = get_variant_description(method)
            assert isinstance(desc, str)
            assert len(desc) > 0

    def test_get_variant_description_deprecated_marker(self):
        desc = get_variant_description(Win32InputMethod.POST_THREAD_MESSAGE)
        assert "DEPRECATED" in desc

    def test_get_variant_info_structure(self):
        info = get_variant_info()
        assert len(info) == 9
        for entry in info:
            assert "method" in entry
            assert "value" in entry
            assert "description" in entry
            assert "is_deprecated" in entry
            assert "is_foreground" in entry
            assert "is_background" in entry

    def test_get_variant_info_deprecated_flag(self):
        info = get_variant_info()
        deprecated_entries = [e for e in info if e["is_deprecated"]]
        assert len(deprecated_entries) == 1
        assert deprecated_entries[0]["method"] == "POST_THREAD_MESSAGE"


# ============================================================
# Compatibility table
# ============================================================

class TestCompatibilityTable:
    """INPUT_COMPATIBILITY_TABLE correctness for known window classes."""

    def test_table_covers_known_game_classes(self):
        """Table must cover Unity, Unreal, Godot, GLFW, and default."""
        expected_classes = {
            "UnityWndClass", "UnrealWindow", "LaunchUnrealUWindowsClient",
            "Godot_Engine_Wnd", "GLFW30", "",  # "" = default
        }
        assert expected_classes.issubset(INPUT_COMPATIBILITY_TABLE.keys())

    def test_unity_blocks_postmessage(self):
        """Unity (BD2) uses RawInput and blocks PostMessage/SendMessage."""
        blocked = get_blocked_input_methods("UnityWndClass")
        assert Win32InputMethod.POST_MESSAGE in blocked
        assert Win32InputMethod.SEND_MESSAGE in blocked

    def test_unity_recommends_seize(self):
        """Unity recommends SEIZE (SendInput) as first choice."""
        recommended = recommend_input_method("UnityWndClass")
        assert recommended == Win32InputMethod.SEIZE

    def test_default_class_recommends_postmessage(self):
        """Standard Win32 windows default to PostMessage for background safety."""
        recommended = recommend_input_method("")
        assert recommended == Win32InputMethod.POST_MESSAGE

    def test_unknown_class_falls_back_to_postmessage(self):
        """Unknown window class falls back to PostMessage."""
        recommended = recommend_input_method("SomeUnknownClass123")
        assert recommended == Win32InputMethod.POST_MESSAGE

    def test_each_entry_has_required_fields(self):
        """Each compatibility entry must have recommended, blocked, reason."""
        for window_class, info in INPUT_COMPATIBILITY_TABLE.items():
            assert "recommended" in info, f"Missing 'recommended' for {window_class!r}"
            assert "blocked" in info, f"Missing 'blocked' for {window_class!r}"
            assert "reason" in info, f"Missing 'reason' for {window_class!r}"
            assert isinstance(info["recommended"], list)
            assert isinstance(info["blocked"], list)
            assert isinstance(info["reason"], str)
            assert len(info["reason"]) > 0

    def test_recommended_not_in_blocked(self):
        """No method should be both recommended and blocked for the same class."""
        for window_class, info in INPUT_COMPATIBILITY_TABLE.items():
            recommended_set = set(info["recommended"])
            blocked_set = set(info["blocked"])
            overlap = recommended_set & blocked_set
            assert not overlap, (
                f"{window_class!r}: methods {overlap} are both recommended and blocked"
            )


# ============================================================
# Query functions
# ============================================================

class TestQueryFunctions:
    """recommend_input_method / recommend_legacy_input_method / etc."""

    def test_recommend_legacy_for_unity(self):
        """Unity → SendInput (legacy string)."""
        assert recommend_legacy_input_method("UnityWndClass") == "SendInput"

    def test_recommend_legacy_for_default(self):
        """Standard Win32 → PostMessage (legacy string)."""
        assert recommend_legacy_input_method("") == "PostMessage"

    def test_recommend_legacy_returns_valid_string(self):
        """recommend_legacy_input_method must return one of the 3 legacy strings."""
        valid = {"SendInput", "PostMessage", "PseudoBackground"}
        for window_class in INPUT_COMPATIBILITY_TABLE:
            result = recommend_legacy_input_method(window_class)
            assert result in valid, f"{window_class!r}: got {result!r}"

    def test_get_compatibility_reason_returns_string(self):
        reason = get_compatibility_reason("UnityWndClass")
        assert isinstance(reason, str)
        assert "RawInput" in reason or "Unity" in reason

    def test_get_compatibility_reason_unknown_class(self):
        reason = get_compatibility_reason("NonExistentClass")
        assert "Unknown" in reason

    def test_get_blocked_input_methods_returns_list(self):
        blocked = get_blocked_input_methods("UnityWndClass")
        assert isinstance(blocked, list)
        assert len(blocked) > 0

    def test_get_blocked_input_methods_empty_for_default(self):
        """Default class has no blocked methods."""
        blocked = get_blocked_input_methods("")
        assert blocked == []

    def test_is_input_method_compatible_blocked(self):
        """PostMessage is not compatible with Unity."""
        assert is_input_method_compatible(
            Win32InputMethod.POST_MESSAGE, "UnityWndClass"
        ) is False

    def test_is_input_method_compatible_recommended(self):
        """SEIZE is compatible with Unity."""
        assert is_input_method_compatible(
            Win32InputMethod.SEIZE, "UnityWndClass"
        ) is True

    def test_is_input_method_compatible_unknown_class(self):
        """Unknown class → assume compatible."""
        assert is_input_method_compatible(
            Win32InputMethod.POST_MESSAGE, "UnknownClass"
        ) is True

    def test_get_compatibility_info_structure(self):
        info = get_compatibility_info("UnityWndClass")
        assert "recommended" in info
        assert "blocked" in info
        assert "reason" in info
        assert "recommended_legacy" in info
        assert info["recommended_legacy"] == "SendInput"

    def test_get_compatibility_info_unknown_class_uses_default(self):
        """Unknown class returns default compatibility info."""
        info = get_compatibility_info("NonExistentClass")
        # Should fall back to default (standard Win32)
        assert Win32InputMethod.POST_MESSAGE in info["recommended"]
