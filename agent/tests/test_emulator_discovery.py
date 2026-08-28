"""Tests for emulator discovery: MuiCache, UserAssist, vbox-conf methods (N126-F4)"""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from devices.emulator_discovery import (
    EMULATOR_CONFIGS,
    MUICACHE_EMULATOR_EXES,
    USERASSIST_GUIDS,
    VBOX_CONF_SEARCH_PATHS,
    VBOX_PATH_TYPE_MAP,
    EmulatorDiscovery,
    _rot13,
)

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# _rot13 helper tests
# ---------------------------------------------------------------------------


class TestRot13:
    """Verify ROT13 transformation used to decode UserAssist value names"""

    def test_uppercase_letters(self):
        assert _rot13("ABC") == "NOP"
        assert _rot13("NOP") == "ABC"

    def test_lowercase_letters(self):
        assert _rot13("abc") == "nop"
        assert _rot13("nop") == "abc"

    def test_non_alpha_unchanged(self):
        """Non-alphabetic characters (digits, separators, dots) are unchanged"""
        text = "C:\\Path123\\To\\file.exe"
        result = _rot13(text)
        # Drive letter and path letters ARE transformed (alphabetic)
        # but digits, colons, backslashes, dots, hyphens must be unchanged
        assert ":" in result
        assert "\\" in result
        assert "." in result
        assert "123" in result  # digits unchanged
        # Verify by checking only non-alpha chars are preserved
        for orig_ch, new_ch in zip(text, result, strict=False):
            if not orig_ch.isalpha():
                assert orig_ch == new_ch

    def test_round_trip(self):
        original = "C:\\Program Files\\Netease\\MuMu Player 12\\MuMuPlayer.exe"
        encoded = _rot13(original)
        decoded = _rot13(encoded)
        assert decoded == original

    def test_empty_string(self):
        assert _rot13("") == ""


def _rot13_apply_twice(text):
    """Apply ROT13 twice to verify it returns to original"""
    return _rot13(_rot13(text))


# ---------------------------------------------------------------------------
# MuiCache discovery tests
# ---------------------------------------------------------------------------


class TestMuiCacheDiscovery:
    """Verify MuiCache registry-based emulator discovery"""

    def test_returns_empty_when_winreg_unavailable(self):
        """When winreg module is not available, returns empty dict"""
        discovery = EmulatorDiscovery()
        discovery._winreg = None
        result = discovery._discover_by_muicache()
        assert result == {}

    def test_finds_emulator_from_muicache_entries(self):
        """MuiCache entries with emulator .exe names are detected"""
        discovery = EmulatorDiscovery()
        mock_winreg = MagicMock()
        discovery._winreg = mock_winreg

        # Simulate registry enumeration returning 3 values, 2 of which are emulators
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.HKEY_CURRENT_USER = 0x80000001

        entries = [
            ("C:\\Program Files\\Netease\\MuMu Player 12\\MuMuPlayer.exe", "MuMu", None),
            ("C:\\Windows\\System32\\notepad.exe", "Notepad", None),
            ("D:\\leidian\\LDPlayer9\\dnplayer.exe", "LDPlayer", None),
        ]
        call_count = [0]

        def mock_enum_value(key, index):
            if index < len(entries):
                call_count[0] += 1
                return entries[index]
            raise OSError("No more values")

        mock_winreg.EnumValue.side_effect = mock_enum_value

        result = discovery._discover_by_muicache()
        assert "mumu" in result
        assert "ldplayer" in result
        assert "MuMu Player 12" in result["mumu"]
        assert "leidian" in result["ldplayer"]

    def test_skips_non_emulator_executables(self):
        """Non-emulator executables in MuiCache are ignored"""
        discovery = EmulatorDiscovery()
        mock_winreg = MagicMock()
        discovery._winreg = mock_winreg

        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.HKEY_CURRENT_USER = 0x80000001

        entries = [
            ("C:\\Windows\\System32\\cmd.exe", "Command Prompt", None),
            ("C:\\Windows\\explorer.exe", "Explorer", None),
        ]

        def mock_enum_value(key, index):
            if index < len(entries):
                return entries[index]
            raise OSError("No more values")

        mock_winreg.EnumValue.side_effect = mock_enum_value

        result = discovery._discover_by_muicache()
        assert result == {}

    def test_handles_registry_open_error(self):
        """If MuiCache key cannot be opened, returns empty dict"""
        discovery = EmulatorDiscovery()
        mock_winreg = MagicMock()
        discovery._winreg = mock_winreg
        mock_winreg.OpenKey.side_effect = OSError("Key not found")

        result = discovery._discover_by_muicache()
        assert result == {}

    def test_first_match_wins_for_duplicate_types(self):
        """When multiple .exe of same emulator type exist, first one wins"""
        discovery = EmulatorDiscovery()
        mock_winreg = MagicMock()
        discovery._winreg = mock_winreg

        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.HKEY_CURRENT_USER = 0x80000001

        entries = [
            ("C:\\Path1\\MuMuPlayer.exe", "MuMu", None),
            ("D:\\Path2\\MuMuPlayer.exe", "MuMu", None),
        ]

        def mock_enum_value(key, index):
            if index < len(entries):
                return entries[index]
            raise OSError("No more values")

        mock_winreg.EnumValue.side_effect = mock_enum_value

        result = discovery._discover_by_muicache()
        assert len(result) == 1
        assert "Path1" in result["mumu"]


# ---------------------------------------------------------------------------
# UserAssist discovery tests
# ---------------------------------------------------------------------------


class TestUserAssistDiscovery:
    """Verify UserAssist registry-based emulator discovery"""

    def test_returns_empty_when_winreg_unavailable(self):
        discovery = EmulatorDiscovery()
        discovery._winreg = None
        result = discovery._discover_by_userassist()
        assert result == {}

    def test_decodes_rot13_and_finds_emulator(self):
        """UserAssist entries are ROT13-encoded; decoded paths are checked"""
        discovery = EmulatorDiscovery()
        mock_winreg = MagicMock()
        discovery._winreg = mock_winreg

        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.HKEY_CURRENT_USER = 0x80000001

        # ROT13-encode an emulator path
        original_path = "C:\\Program Files\\Netease\\MuMu Player 12\\MuMuPlayer.exe"
        encoded_path = _rot13(original_path)

        entries = [
            (encoded_path, b"\x00" * 8, None),
            (_rot13("C:\\Windows\\System32\\notepad.exe"), b"\x00" * 8, None),
        ]

        def mock_enum_value(key, index):
            if index < len(entries):
                return entries[index]
            raise OSError("No more values")

        mock_winreg.EnumValue.side_effect = mock_enum_value

        result = discovery._discover_by_userassist()
        assert "mumu" in result
        assert "MuMu Player 12" in result["mumu"]

    def test_skips_entries_without_drive_letter(self):
        """Entries without ':' (e.g. UNC paths) are skipped"""
        discovery = EmulatorDiscovery()
        mock_winreg = MagicMock()
        discovery._winreg = mock_winreg

        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.HKEY_CURRENT_USER = 0x80000001

        # ROT13 of a path without drive letter
        entries = [
            (_rot13("\\Device\\HarddiskVolume1\\MuMuPlayer.exe"), b"\x00", None),
        ]

        def mock_enum_value(key, index):
            if index < len(entries):
                return entries[index]
            raise OSError("No more values")

        mock_winreg.EnumValue.side_effect = mock_enum_value

        result = discovery._discover_by_userassist()
        assert result == {}

    def test_handles_missing_guid_key(self):
        """If a UserAssist GUID key is missing, continues to next GUID"""
        discovery = EmulatorDiscovery()
        mock_winreg = MagicMock()
        discovery._winreg = mock_winreg
        mock_winreg.OpenKey.side_effect = OSError("Key not found")

        result = discovery._discover_by_userassist()
        assert result == {}

    def test_multiple_guids_checked(self):
        """Both Windows 7+ and Windows 10+ GUIDs are checked"""
        assert len(USERASSIST_GUIDS) >= 2
        assert "{CEBFF5CD-ACE2-4F4F-9178-9926F41749EA}" in USERASSIST_GUIDS


# ---------------------------------------------------------------------------
# vbox-conf discovery tests
# ---------------------------------------------------------------------------


class TestVboxConfDiscovery:
    """Verify .vbox config file-based emulator instance discovery"""

    def test_returns_empty_when_no_vbox_files(self):
        """When glob finds no .vbox files, returns empty list"""
        discovery = EmulatorDiscovery()
        with patch("devices.emulator_discovery.glob.glob", return_value=[]):
            result = discovery._discover_by_vbox_conf()
        assert result == []

    def test_finds_vbox_file_and_extracts_type(self):
        """A .vbox file in LDPlayer path is detected as ldplayer type"""
        discovery = EmulatorDiscovery()
        vbox_path = r"D:\leidian\LDPlayer9\vms\ld1.vbox"

        with (
            patch("devices.emulator_discovery.glob.glob", return_value=[vbox_path]),
            patch("devices.emulator_discovery.ET.parse") as mock_parse,
        ):
            # Simulate parse failure so we fall back to filename
            mock_parse.side_effect = Exception("parse error")
            result = discovery._discover_by_vbox_conf()

        assert len(result) == 1
        assert result[0]["type"] == "ldplayer"
        assert result[0]["vbox_path"] == vbox_path
        assert result[0]["vm_name"] == "ld1"

    def test_parses_vm_name_from_xml(self):
        """VM name is extracted from Machine element in .vbox XML"""
        discovery = EmulatorDiscovery()

        # Build a minimal .vbox XML
        xml_content = """<?xml version="1.0"?>
<VirtualBox>
  <Machine name="MuMu-Instance-1" ostype="Android" uuid="abc-123"/>
</VirtualBox>
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".vbox", delete=False, encoding="utf-8"
        ) as f:
            f.write(xml_content)
            temp_path = f.name

        try:
            with patch("devices.emulator_discovery.glob.glob", return_value=[temp_path]):
                result = discovery._discover_by_vbox_conf()
            assert len(result) == 1
            # Type derived from temp_path (no emulator marker) — should be "unknown"
            assert result[0]["vm_name"] == "MuMu-Instance-1"
        finally:
            os.unlink(temp_path)

    def test_deduplicates_duplicate_paths(self):
        """Same .vbox path matched by multiple glob patterns is deduplicated"""
        discovery = EmulatorDiscovery()
        vbox_path = r"D:\leidian\LDPlayer9\vms\ld1.vbox"

        # glob returns the same path multiple times (from different patterns)
        with (
            patch(
                "devices.emulator_discovery.glob.glob",
                return_value=[vbox_path, vbox_path, vbox_path],
            ),
            patch("devices.emulator_discovery.ET.parse") as mock_parse,
        ):
            mock_parse.side_effect = Exception("parse error")
            result = discovery._discover_by_vbox_conf()

        assert len(result) == 1

    def test_emulator_type_inferred_from_path(self):
        """Emulator type is correctly inferred from .vbox file path"""
        test_cases = [
            (r"D:\leidian\LDPlayer9\vms\ld1.vbox", "ldplayer"),
            (r"D:\Program Files\Netease\MuMu Player 12\vms\mumu1.vbox", "mumu"),
            (r"D:\Program Files\Nox\bin\BignoxVMS\nox1.vbox", "nox"),
            (r"D:\Program Files\Microvirt\MEmu\MemuHyperv VMs\memu1.vbox", "memu"),
        ]
        discovery = EmulatorDiscovery()

        for path, expected_type in test_cases:
            with (
                patch("devices.emulator_discovery.glob.glob", return_value=[path]),
                patch("devices.emulator_discovery.ET.parse") as mock_parse,
            ):
                mock_parse.side_effect = Exception("parse error")
                result = discovery._discover_by_vbox_conf()
            assert len(result) == 1, f"Failed for path: {path}"
            assert result[0]["type"] == expected_type, f"Failed for path: {path}"


# ---------------------------------------------------------------------------
# discover_all integration tests
# ---------------------------------------------------------------------------


class TestDiscoverAllIntegration:
    """Verify discover_all integrates all discovery methods"""

    def test_includes_discovery_source_field(self):
        """Each result entry includes a discovery_source field"""
        discovery = EmulatorDiscovery()
        # Mock all discovery methods to return empty
        with (
            patch.object(discovery, "_discover_by_process", return_value={}),
            patch.object(discovery, "discover_ldplayer", return_value=None),
            patch.object(discovery, "discover_mumu", return_value=None),
            patch.object(discovery, "discover_bluestacks", return_value=None),
            patch.object(discovery, "discover_nox", return_value=None),
            patch.object(discovery, "discover_xiaoyao", return_value=None),
            patch.object(discovery, "_discover_by_muicache", return_value={}),
            patch.object(discovery, "_discover_by_userassist", return_value={}),
            patch.object(discovery, "_discover_by_vbox_conf", return_value=[]),
            patch.object(discovery, "scan_adb_ports", return_value=["127.0.0.1:5555"]),
        ):
            results = discovery.discover_all()
        assert len(results) >= 1
        assert all("discovery_source" in r for r in results)
        assert results[0]["discovery_source"] == "adb-scan"

    def test_muicache_results_added_when_registry_fails(self):
        """When registry discovery fails, MuiCache results are included"""
        discovery = EmulatorDiscovery()

        muicache_result = {"mumu": "C:\\Path\\To\\MuMu"}
        with (
            patch.object(discovery, "_discover_by_process", return_value={}),
            patch.object(discovery, "discover_ldplayer", return_value=None),
            patch.object(discovery, "discover_mumu", return_value=None),
            patch.object(discovery, "discover_bluestacks", return_value=None),
            patch.object(discovery, "discover_nox", return_value=None),
            patch.object(discovery, "discover_xiaoyao", return_value=None),
            patch.object(discovery, "_discover_by_muicache", return_value=muicache_result),
            patch.object(discovery, "_discover_by_userassist", return_value={}),
            patch.object(discovery, "_discover_by_vbox_conf", return_value=[]),
        ):
            results = discovery.discover_all()
        muicache_entries = [r for r in results if r.get("discovery_source") == "muicache"]
        assert len(muicache_entries) == 1
        assert muicache_entries[0]["type"] == "mumu"
        assert muicache_entries[0]["install_path"] == "C:\\Path\\To\\MuMu"

    def test_vbox_instances_always_included(self):
        """vbox-conf instances are included even if base emulator already found"""
        discovery = EmulatorDiscovery()

        # Registry finds mumu at port 7555
        mumu_info = {
            "name": "MuMu Emulator",
            "type": "mumu",
            "adb_port": 7555,
            "adb_serial": "127.0.0.1:7555",
            "install_path": "C:\\MuMu",
        }
        vbox_instances = [
            {
                "name": "mumu - Instance1",
                "type": "mumu",
                "vbox_path": "D:\\MuMu\\vms\\inst1.vbox",
                "vm_name": "Instance1",
                "install_path": "D:\\MuMu",
            }
        ]

        with (
            patch.object(discovery, "_discover_by_process", return_value={"mumu": True}),
            patch.object(discovery, "discover_ldplayer", return_value=None),
            patch.object(discovery, "discover_mumu", return_value=mumu_info),
            patch.object(discovery, "discover_bluestacks", return_value=None),
            patch.object(discovery, "discover_nox", return_value=None),
            patch.object(discovery, "discover_xiaoyao", return_value=None),
            patch.object(discovery, "_discover_by_muicache", return_value={}),
            patch.object(discovery, "_discover_by_userassist", return_value={}),
            patch.object(discovery, "_discover_by_vbox_conf", return_value=vbox_instances),
        ):
            results = discovery.discover_all()
        # Both registry and vbox-conf results present
        sources = [r.get("discovery_source") for r in results]
        assert "registry+adb" in sources
        assert "vbox-conf" in sources


# ---------------------------------------------------------------------------
# Constants sanity tests
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify discovery constants are properly configured"""

    def test_muicache_emulator_exes_non_empty(self):
        assert len(MUICACHE_EMULATOR_EXES) >= 5
        assert "MuMuPlayer.exe" in MUICACHE_EMULATOR_EXES

    def test_vbox_search_paths_non_empty(self):
        assert len(VBOX_CONF_SEARCH_PATHS) >= 6

    def test_vbox_path_type_map_covers_all_emulators(self):
        types = {t for _, t in VBOX_PATH_TYPE_MAP}
        assert "ldplayer" in types
        assert "mumu" in types
        assert "nox" in types

    def test_emulator_configs_have_required_fields(self):
        for emu_type, config in EMULATOR_CONFIGS.items():
            assert "name" in config, f"Missing name for {emu_type}"
            assert "reg_paths" in config, f"Missing reg_paths for {emu_type}"
            assert "default_adb_port" in config, f"Missing port for {emu_type}"
            assert "process_names" in config, f"Missing process_names for {emu_type}"
