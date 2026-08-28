"""test_session_active.py — Unit tests for check_session_active.py (M2.A-4)

Covers 5 cases (consolidated from Appendix G §G.6):
1. test_file_missing            — session file missing → exit 1
2. test_json_invalid            — corrupted JSON → exit 1
3. test_24h_valid               — fresh session (24h TTL) → exit 0
4. test_24h_expired             — expired session (expires_at in the past) → exit 1
5. test_binding_hash_mismatch   — payload tampered after creation → exit 1 (N58)

The script is hard-coded to a single SESSION_FILE path, so we monkey-patch
the module-level constant to point at a tmp path. This is the same pattern
other GAF tests use (e.g. test_sync_ai_memory, test_extract_lessons).

Run with:
    python -m unittest GAF/scripts/tests/test_session_active.py -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Optional

# Make the parent scripts/ directory importable
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import check_session_active  # noqa: E402
import pytest

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSessionActive(unittest.TestCase):
    """5-test suite for check_session_active (consolidated from G.6)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        # Save the real SESSION_FILE and monkey-patch
        self._real_session_file = check_session_active.SESSION_FILE
        check_session_active.SESSION_FILE = self.tmp_path / ".gaf_session_active"

    def tearDown(self) -> None:
        check_session_active.SESSION_FILE = self._real_session_file
        self.tmp.cleanup()

    # ---- 1. file missing → exit 1 ---------------------------------------

    def test_file_missing(self) -> None:
        """When the session file does not exist, check_session() returns 1."""
        self.assertFalse(
            check_session_active.SESSION_FILE.exists(),
            "precondition: session file should not exist",
        )
        code = check_session_active.check_session()
        self.assertEqual(
            code, 1,
            "expected exit 1 when session file is missing",
        )

    # ---- 2. json invalid → exit 1 ----------------------------------------

    def test_json_invalid(self) -> None:
        """Corrupted JSON in the session file → exit 1."""
        check_session_active.SESSION_FILE.write_text(
            "{this is not valid json,,,", encoding="utf-8",
        )
        code = check_session_active.check_session()
        self.assertEqual(
            code, 1,
            "expected exit 1 when JSON is invalid",
        )

    # ---- 3. 24h valid → exit 0 ------------------------------------------

    def test_24h_valid(self) -> None:
        """A fresh session (created via create_session()) → exit 0."""
        self.assertEqual(
            check_session_active.create_session(), 0,
            "create_session() should succeed",
        )
        # Now check it
        code = check_session_active.check_session()
        self.assertEqual(
            code, 0,
            "fresh session should pass check_session()",
        )

    # ---- 4. 24h expired → exit 1 -----------------------------------------

    def test_24h_expired(self) -> None:
        """A session with expires_at in the past → exit 1."""
        # Build a payload that's clearly expired
        now = int(time.time())
        payload = {
            "created_at": now - 48 * 3600,  # 48h ago
            "expires_at": now - 24 * 3600,  # 24h ago
            "pid": 12345,
            "user": "tester",
            "platform": "Test",
        }
        # First run: no binding_hash → will be created
        check_session_active.SESSION_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        code = check_session_active.check_session()
        self.assertEqual(
            code, 1,
            "expired session should fail check_session()",
        )

    # ---- 5. binding hash mismatch → exit 1 (N58) ------------------------

    def test_binding_hash_mismatch(self) -> None:
        """Tampering with the payload after creation should fail binding check."""
        # Step 1: create a valid session (computes and stores binding_hash)
        check_session_active.create_session()

        # Step 2: tamper with the payload (e.g. change user field)
        payload = json.loads(
            check_session_active.SESSION_FILE.read_text(encoding="utf-8")
        )
        self.assertIn(
            "binding_hash", payload,
            "precondition: created session should have a binding_hash",
        )
        original_binding = payload["binding_hash"]
        payload["user"] = "tampered_user"  # mutate the payload
        # Re-write WITHOUT updating the binding_hash
        check_session_active.SESSION_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8",
        )

        # Step 3: check should now fail (binding mismatch)
        code = check_session_active.check_session()
        self.assertEqual(
            code, 1,
            "tampered session (binding mismatch) should fail check_session()",
        )


if __name__ == "__main__":
    unittest.main()
