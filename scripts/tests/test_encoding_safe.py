"""Tests for scripts/_encoding_safe.py (N92 CJK garble fix, v8.4).

Covers the two-line defense aligned with TEST_SFCAPI_LANGUAGE's `-X utf8`
approach (2026-08-15):
  1. force_utf8_mode() — sets PYTHONUTF8=1 + PYTHONIOENCODING=utf-8 so child
     processes inherit global UTF-8 Mode (stdin/stdout/stderr/file IO).
  2. force_utf8_stdout() — reconfigures the current process stdout to UTF-8
     with errors="replace" (idempotent).

All tests are hermetic: they load the module via importlib from the real
scripts/ dir with a controlled env, never mutating the caller's process env.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENCODING_SAFE = REPO_ROOT / "scripts" / "_encoding_safe.py"


def _load_module() -> None:
    """Import scripts/_encoding_safe.py as a standalone module in a clean env.

    The module does NOT call force_utf8_stdout() at import time in a way that
    mutates the test process — it only touches sys.stdout of the subprocess
    it runs in. We still import it in the current process to assert the
    exported helpers exist and behave.
    """
    spec = importlib.util.spec_from_file_location("_encoding_safe_test", ENCODING_SAFE)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_in_subprocess(code: str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    """Run Python snippet in a fresh subprocess with controlled env."""
    env = os.environ.copy()
    # strip any UTF-8 forcing so the test measures the module's own effect
    for key in ("PYTHONUTF8", "PYTHONIOENCODING"):
        env.pop(key, None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )


# Code snippet: import the real _encoding_safe.py and report what it did.
_SNIPPET = textwrap.dedent(
    f"""
    import importlib.util, sys
    from pathlib import Path
    mod_path = Path({str(ENCODING_SAFE)!r})
    spec = importlib.util.spec_from_file_location("_enc", mod_path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    import os
    print("PYTHONUTF8=" + os.environ.get("PYTHONUTF8", "<unset>"))
    print("PYTHONIOENCODING=" + os.environ.get("PYTHONIOENCODING", "<unset>"))
    print("STDOUT_ENC=" + sys.stdout.encoding)
    # force_utf8_stdout is idempotent — calling twice must not raise.
    m.force_utf8_stdout()
    m.force_utf8_stdout()
    print("OK")
    """
)


class TestEncodingSafe(unittest.TestCase):
    """Behavioral tests for _encoding_safe.py two-line defense."""

    # ---- 1. import side effects: env vars for child inheritance ----------

    def test_import_sets_utf8_env_vars(self) -> None:
        """Importing the module sets PYTHONUTF8=1 + PYTHONIOENCODING=utf-8 so
        all child processes inherit global UTF-8 Mode."""
        proc = _run_in_subprocess(_SNIPPET)
        self.assertEqual(
            proc.returncode, 0,
            f"subprocess failed: stderr={proc.stderr!r}",
        )
        self.assertIn("PYTHONUTF8=1", proc.stdout)
        self.assertIn("PYTHONIOENCODING=utf-8", proc.stdout)

    # ---- 2. stdout reconfigure to UTF-8 --------------------------------

    def test_stdout_reconfigured_to_utf8(self) -> None:
        """After import, stdout encoding is UTF-8 (not cp936/cp437)."""
        proc = _run_in_subprocess(_SNIPPET)
        self.assertIn("STDOUT_ENC=utf-8", proc.stdout)

    def test_force_utf8_stdout_idempotent(self) -> None:
        """Calling force_utf8_stdout() twice is safe (no exception)."""
        proc = _run_in_subprocess(_SNIPPET)
        self.assertIn("OK", proc.stdout)

    # ---- 3. direct helper behavior -------------------------------------

    def test_force_utf8_mode_sets_env(self) -> None:
        """Importing the module sets both env vars (module-level side effect),
        and a second call does not clobber a user-set value (idempotent)."""
        import os as _os

        saved = {k: _os.environ.get(k) for k in ("PYTHONUTF8", "PYTHONIOENCODING")}
        try:
            for k in saved:
                _os.environ.pop(k, None)
            mod = _load_module()
            self.assertEqual(_os.environ.get("PYTHONUTF8"), "1")
            self.assertEqual(_os.environ.get("PYTHONIOENCODING"), "utf-8")
            # idempotent: a later force_utf8_mode() call does not clobber a
            # user-set value (module-level already ran; env is untouched).
            _os.environ["PYTHONUTF8"] = "0"
            mod.force_utf8_mode()
            self.assertEqual(_os.environ.get("PYTHONUTF8"), "0")
        finally:
            for k, v in saved.items():
                if v is None:
                    _os.environ.pop(k, None)
                else:
                    _os.environ[k] = v

    def test_force_utf8_stdout_noop_when_already_utf8(self) -> None:
        """force_utf8_stdout() is a safe no-op when stdout is already UTF-8."""
        mod = _load_module()
        stream = mod.force_utf8_stdout()
        self.assertEqual(stream.encoding, "utf-8")


if __name__ == "__main__":
    unittest.main()
