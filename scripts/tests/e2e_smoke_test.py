"""e2e_smoke_test.py — End-to-end smoke test for sync_ai_memory.py CLI.

This script stands up a minimal .ai-memory/ directory, populates one
lesson, and exercises the most important CLI paths:

1. `--query` with a Chinese keyword (hits synonyms)
2. `--query` with an English category path
3. `--query` that returns no matches
4. The default `sync` path on a fresh .ai-memory tree

It's a one-shot smoke test (not part of the 8-case unit suite in
`test_sync_ai_memory.py`); use it to verify cross-platform behaviour
on a fresh checkout.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.e2e
PY = sys.executable


LESSON = """\
---
date: "2026-06-14"
maintainer: auto
symptom: [popup:agent:duplicate, 弹窗, agent 重复]
solution: 文件锁 + SW_HIDE
related_files:
  - agent/src/client/connection.py
created_by: AI
priority: high
---

# Agent popup bug
"""


def run(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PY, str(SCRIPTS_DIR / "sync_ai_memory.py"), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def main() -> int:
    # Force utf-8 stdout so the child Python prints the Chinese banner
    # correctly even on Windows consoles with cp936 default.
    import os

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    tmp = Path(tempfile.mkdtemp(prefix="gaf_e2e_"))
    try:
        ai = tmp / ".ai-memory"
        (ai / "lessons").mkdir(parents=True)
        (ai / "lessons" / "test.md").write_text(LESSON, encoding="utf-8")

        # 1. Chinese keyword — exit 0 and JSON payload includes test.md.
        r = run("--query", "弹窗", "--root", str(tmp), env=env)
        assert r.returncode == 0, f"弹窗 query failed: {r.stdout}\n{r.stderr}"
        assert "test.md" in r.stdout, f"expected test.md in output, got: {r.stdout!r}"
        print("[OK] --query 弹窗")

        # 2. English category path
        r = run("--query", "popup:agent:duplicate", "--root", str(tmp), env=env)
        assert r.returncode == 0, f"category query failed: {r.stdout}\n{r.stderr}"
        assert "test.md" in r.stdout
        print("[OK] --query popup:agent:duplicate")

        # 3. No-match query
        r = run("--query", "no-such-token-xyz", "--root", str(tmp), env=env)
        assert r.returncode == 0
        assert "未找到" in r.stdout or "no matches" in r.stdout
        print("[OK] --query no-such-token-xyz (no match)")

        # 4. Default sync (dry-run)
        r = run("--dry-run", "--root", str(tmp), env=env)
        assert r.returncode == 0
        assert "regenerated=1" in r.stdout
        print("[OK] --dry-run sync")

        # 5. JSON-mode query (--stats) sanity
        r = run("--dry-run", "--stats", "--root", str(tmp), env=env)
        assert r.returncode == 0
        # --stats emits a pretty-printed JSON block; balance braces to
        # extract the JSON object (since extra text follows the block).
        text = r.stdout
        start = text.find("{")
        assert start >= 0, f"no JSON in --stats output: {text!r}"
        depth = 0
        end = start
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        payload = json.loads(text[start:end])
        assert "regenerated" in payload
        print("[OK] --stats json payload")

        print("ALL E2E SMOKE TESTS PASSED")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
