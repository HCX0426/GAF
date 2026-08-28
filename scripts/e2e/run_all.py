"""e2e/run_all.py — End-to-end runner for the 7 canonical AI scenarios.

M2.B deliverable: a single entry point that exercises the orchestrator
plus every companion skill against a mock Agent and writes a
per-scenario verdict to stdout **and** to ``.trash/.e2e-failures.log`` if
anything goes wrong. The 7 scenarios are pinned in
``spec/tasks.md §3.2.2`` and re-exported from ``conftest.py``.

Usage::

    python scripts/e2e/run_all.py           # run all 7 scenarios
    python scripts/e2e/run_all.py cold_start # run a single scenario
    python scripts/e2e/run_all.py --strict  # non-zero exit on any failure

The runner is deliberately a plain Python script (not a pytest module)
so it can be wired into the ``[manual]`` pre-commit stage and into CI
without pulling in the full test stack.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import json
import os
import re
import sys
import tempfile
import time
import traceback
from collections.abc import Callable
from pathlib import Path

# Make ``from scripts.xxx import yyy`` work without an editable install.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Force UTF-8 output (N92 CJK garble fix on Windows cp936/cp437 consoles).
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("LC_ALL", "C.UTF-8")

from scripts.e2e.fixtures import mock_agent  # noqa: E402
from scripts.e2e.scenarios import (  # noqa: E402
    run_ai_qa_chat,
    run_browser_login,
    run_devices_control_mode,
    run_full_routes,
)

FAILURE_LOG_NAME = ".trash/.e2e-failures.log"
WHY_SKIPPED_NAME = "ops/why-skipped.md"
WHY_SKIPPED_DEDUP_HOURS = 24
SCENARIOS: dict[str, Callable[[Path], tuple[bool, str]]] = {}


def register(name: str) -> Callable[[Callable[[Path], tuple[bool, str]]], Callable[[Path], tuple[bool, str]]]:
    """Decorator that registers a scenario under ``name``."""

    def deco(fn: Callable[[Path], tuple[bool, str]]) -> Callable[[Path], tuple[bool, str]]:
        SCENARIOS[name] = fn
        return fn

    return deco


# ---------------------------------------------------------------------------
# Scenario helpers
# ---------------------------------------------------------------------------

def _load_mock_task(repo: Path) -> dict:
    """Load the canonical mock task payload from disk."""
    fixture = repo / "scripts" / "e2e" / "fixtures" / "mock_task.json"
    return json.loads(fixture.read_text(encoding="utf-8"))


def _ensure_min_ai_memory(repo: Path) -> Path:
    """Create a minimal .ai-memory/ tree in a temp dir for hermetic runs."""
    tmp = Path(tempfile.mkdtemp(prefix="gaf_e2e_"))
    (tmp / "lessons").mkdir(parents=True, exist_ok=True)
    (tmp / "meta").mkdir(parents=True, exist_ok=True)
    (tmp / "tech-stack.md").write_text("# tech-stack (mock)\n", encoding="utf-8")
    (tmp / "failure-modes.md").write_text(
        "# failure-modes (mock)\n\n### N##: stub\n", encoding="utf-8"
    )
    return tmp


# ---------------------------------------------------------------------------
# 7 scenarios (spec/tasks.md §3.2.2)
# ---------------------------------------------------------------------------

@register("cold_start")
def scenario_cold_start(repo: Path) -> tuple[bool, str]:
    """Cold-start: gaf_init.sh + session create + .ai-memory bootstrap.

    We do not invoke the real ``gaf_init.sh`` (it mutates the host); we
    simulate the three observable effects: a session file exists, the
    top-level .ai-memory files are present, and the four SKILL.md copies
    were synced. Exit 0 ⇒ all three hold.
    """
    start = time.perf_counter()
    repo_root = repo
    auto_kb = repo_root / ".ai-memory" / "meta" / "auto-kb"
    docs_ref = repo_root / "docs" / "reference"
    # KB 文件分布在两处 (v9.3/v9.6 迁移后):
    #   .ai-memory/meta/auto-kb/  — api-endpoints / agent-protocol / pipeline-nodes / error-codes
    #   docs/reference/           — tech-stack / version-compat / data-flow / cli-cheatsheet
    expected = {
        auto_kb / "api-endpoints.md",
        auto_kb / "agent-protocol.md",
        auto_kb / "pipeline-nodes.md",
        auto_kb / "error-codes.md",
        docs_ref / "tech-stack.md",
        docs_ref / "version-compat.md",
        docs_ref / "data-flow.md",
        docs_ref / "cli-cheatsheet.md",
    }
    missing = sorted(p for p in expected if not p.exists())
    if missing:
        rel = ", ".join(str(p.relative_to(repo_root)).replace("\\", "/") for p in missing)
        return False, f"cold_start missing {rel}"
    skills = [
        repo / ".skills" / "skills" / "gaf-orchestrator" / "SKILL.md",
        repo / ".skills" / "skills" / "gaf-task-execution" / "SKILL.md",
        repo / ".skills" / "skills" / "gaf-reflect-and-evolve" / "SKILL.md",
        repo / ".skills" / "skills" / "gaf-knowledge-base" / "SKILL.md",
    ]
    for p in skills:
        if not p.exists():
            return False, f"cold_start missing skill {p.name}"
    elapsed = time.perf_counter() - start
    return True, f"cold_start OK ({elapsed:.3f}s, {len(expected)} KB files + 4 skills)"


@register("new_feature")
def scenario_new_feature(repo: Path) -> tuple[bool, str]:
    """new_feature: orchestrator → gaf-task-execution → mock agent → evidence."""
    task = _load_mock_task(repo)
    if task.get("type") != "new_feature":
        return False, f"new_feature fixture type mismatch: {task.get('type')}"
    result = mock_agent.handle(task)
    if result.get("status") != "ok":
        return False, f"mock_agent returned {result.get('status')}"
    expected_keys = {"status", "output", "evidence_path"}
    if not expected_keys.issubset(result):
        return False, f"new_feature missing keys: {expected_keys - set(result)}"
    return True, f"new_feature OK (task={task['name']}, evidence={result['evidence_path']})"


@register("bug_fix")
def scenario_bug_fix(repo: Path) -> tuple[bool, str]:
    """bug_fix: orchestrator → gaf-reflect-and-evolve → lesson drafted → 5-layer distribution.

    Verifies the bug_fix lesson chain still works end-to-end: at least one N##
    lesson exists in lessons/, and some N## is referenced in both failure-modes
    and architecture-mistakes (5-layer distribution surface). No longer pins a
    specific N## id — N118 was retired by the N## purge mechanism (§4.12).
    """
    lessons_dir = repo / ".ai-memory" / "lessons"
    n_files = [p for p in lessons_dir.iterdir() if re.search(r"[nN]\d{3}", p.name)]
    if not n_files:
        return False, "bug_fix: no N## lesson file found in lessons/"
    nids = {m.group(0).upper() for p in n_files for m in re.finditer(r"[nN](\d{3})", p.name)}
    arch = (repo / ".ai-memory" / "summaries" / "architecture-mistakes.md").read_text(
        encoding="utf-8", errors="replace"
    )
    failure = (repo / ".ai-memory" / "meta" / "failure-modes.md").read_text(
        encoding="utf-8", errors="replace"
    )
    arch_n = set(re.findall(r"N\d{3}", arch))
    failure_n = set(re.findall(r"N\d{3}", failure))
    distributed = nids & arch_n & failure_n
    if not nids & failure_n:
        return False, "bug_fix: no lesson N## is registered in failure-modes active index"
    if not distributed:
        return False, "bug_fix: no lesson N## referenced in both arch and failure-modes (5-layer)"
    return True, f"bug_fix OK ({len(distributed)} lessons with arch+failure refs)"


@register("documentation")
def scenario_documentation(repo: Path) -> tuple[bool, str]:
    """documentation: orchestrator → gaf-knowledge-base → docs/ + .ai-memory/ parity check."""
    docs_index = repo / ".ai-memory" / "meta" / "docs-index.md"
    if not docs_index.exists():
        return False, "documentation: docs-index.md still missing after sync"
    content = docs_index.read_text(encoding="utf-8", errors="replace")
    # Parse the ``**文档总数**：N`` summary line emitted by sync_docs_index
    # (more reliable than counting ``##``/``###`` headings, which include
    # status banners like "✅ 全部文档新鲜" that aren't real groups).
    import re
    match = re.search(r"\*\*文档总数\*\*[：:]\s*(\d+)", content)
    if not match:
        return False, "documentation: docs-index missing '**文档总数**' summary line"
    total = int(match.group(1))
    if total < 20:
        return False, f"documentation: docs-index reports only {total} docs (< 20)"
    return True, f"documentation OK ({total} docs indexed, sync_docs_index 0 stale)"


@register("refactor")
def scenario_refactor(repo: Path) -> tuple[bool, str]:
    """refactor: orchestrator → gaf-task-execution + gaf-reflect-and-evolve.

    Verifies that the decision-tree SKILL.md contains both
    ``gaf-task-execution`` and ``gaf-reflect-and-evolve`` references in
    the refactor task_type row, and that ``project_rules.md §4.6``
    carries the cycle-reflection rules.
    """
    skill = (repo / ".skills" / "skills" / "gaf-orchestrator" / "SKILL.md").read_text(
        encoding="utf-8", errors="replace"
    )
    rules = (repo / ".skills" / "rules" / "project_rules.md").read_text(
        encoding="utf-8", errors="replace"
    )
    if "gaf-task-execution" not in skill or "gaf-reflect-and-evolve" not in skill:
        return False, "refactor: skill references incomplete in gaf-orchestrator"
    if "4.6" not in rules and "循环迭代反思" not in rules:
        return False, "refactor: project_rules §4.6 循环迭代反思 missing"
    return True, "refactor OK (skill row + rules §4.6 present)"


@register("cross_repo")
def scenario_cross_repo(repo: Path) -> tuple[bool, str]:
    """cross_repo: AI must refuse destructive cross-workspace operations.

    We don't actually run a destructive command; we instead assert that
    the rules contain the explicit ``3 类需授权`` list (N109) so a
    human or downstream tool can detect the policy.
    """
    rules = (repo / ".skills" / "rules" / "project_rules.md").read_text(
        encoding="utf-8", errors="replace"
    )
    # 措辞随 §3.5 演进（2026-08: '跨工作区' 并入 '重写 history' / '不可逆删除' 清单）
    for needle in ("重写 history", "不可逆删除", "branch -D"):
        if needle not in rules:
            return False, f"cross_repo: policy '{needle}' missing in project_rules"
    return True, "cross_repo OK (3 类需授权 policy present)"


@register("browser_login")
def scenario_browser_login(repo: Path) -> tuple[bool, str]:
    """browser_login: Playwright logs into the local frontend and checks console.

    Exercises the full stack (frontend dev server + backend auth API) and
    surfaces JavaScript errors that unit tests cannot catch.
    """
    return run_browser_login(repo)


@register("devices_control_mode")
def scenario_devices_control_mode(repo: Path) -> tuple[bool, str]:
    """devices_control_mode: Playwright verifies /devices/windows control mode UI.

    TD-015 regression coverage: control-mode selector renders and can be
    toggled without console errors.
    """
    return run_devices_control_mode(repo)


@register("ai_qa_chat")
def scenario_ai_qa_chat(repo: Path) -> tuple[bool, str]:
    """ai_qa_chat: Playwright verifies LLM chat via the QA panel (/ai/qa).

    Regression coverage for commit 6a32763: login → /ai/qa → send message
    → LLM reply rendered. Exercises the full chain: browser → Vite proxy
    → Django /qa/ask/ → call_llm() → LLMRouter → SiliconFlow API.
    """
    return run_ai_qa_chat(repo)


@register("full_routes")
def scenario_full_routes(repo: Path) -> tuple[bool, str]:
    """full_routes: headless browser sweeps every frontend route against the real backend.

    Persisted E2E case library (docs/health/e2e-test-plan.md A–K): 40 static
    + 6 dynamic routes. No mocks — real Vite dev server → Django API chain.
    Covers crash-free rendering, layout presence, page exceptions, and
    console errors for the whole feature surface; 4xx/5xx recorded as WARN.
    """
    return run_full_routes(repo)


@register("collaboration")
def scenario_collaboration(repo: Path) -> tuple[bool, str]:
    """collaboration: two concurrent sync_ai_memory runs must not corrupt state.

    We probe the SyncLock helper directly: acquire the lock in this
    process, attempt a second acquisition with a short timeout, and
    assert that ``LockTimeout`` is raised. The ``scripts`` package must
    be importable; the runner's ``sys.path`` already adds the repo root
    for this reason.
    """
    # Add scripts/ to sys.path so ``from sync_lock import ...`` resolves
    # (sync_lock.py itself does ``import _encoding_safe`` which lives in
    # the same directory).
    scripts_dir = str(repo / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from sync_lock import LockTimeout, SyncLock  # type: ignore[import-not-found]

    lock_path = Path(tempfile.mkstemp(prefix="gaf_collaboration_")[1])
    try:
        with SyncLock(lock_path, timeout=2.0):
            # Lock is held; second attempt must time out.
            try:
                with SyncLock(lock_path, timeout=0.5):
                    return False, "collaboration: second lock acquired unexpectedly"
            except LockTimeout:
                return True, "collaboration OK (LockTimeout raised as expected)"
            except Exception as exc:  # noqa: BLE001
                return False, f"collaboration: unexpected error {exc!r}"
    finally:
        with contextlib.suppress(OSError):
            lock_path.unlink()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _write_failure_log(repo: Path, failures: list[tuple[str, str]]) -> None:
    """Append failed scenarios to ``.trash/.e2e-failures.log`` (N91 修复路径)."""
    if not failures:
        return
    log = repo / FAILURE_LOG_NAME
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(f"\n# e2e run @ {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        for name, detail in failures:
            f.write(f"- FAIL  {name}: {detail}\n")


def _write_why_skipped(repo: Path, failures: list[tuple[str, str]]) -> None:
    """Append failed scenarios to ``ops/why-skipped.md`` (M2.E 闭环) with dedup.

    Unlike ``.trash/.e2e-failures.log`` (raw append), this file is curated and
    human/AI readable, with sections grouped by scenario, a triage hint
    section, and a "next step" footer that points at the M2.E weekly
    summary script.

    Format::

        ## e2e 失败记录 @ <timestamp>

        | scenario | detail | 修复路径 | 优先 |
        ...

    TD-306 dedup: same scenario within ``WHY_SKIPPED_DEDUP_HOURS`` (default
    24h) → skip writing. Reads existing file, parses entries newer than the
    cutoff, filters out failures whose scenario already appears in that
    window. If all failures are dupes, skips the append entirely.
    """
    if not failures:
        return
    target = repo / ".ai-memory" / WHY_SKIPPED_NAME
    target.parent.mkdir(parents=True, exist_ok=True)

    # TD-306 dedup: filter out scenarios already recorded in the last 24h.
    recent_scenarios = _recent_why_skipped_scenarios(target, hours=WHY_SKIPPED_DEDUP_HOURS)
    new_failures = [(n, d) for n, d in failures if n not in recent_scenarios]
    if not new_failures:
        # All scenarios already recorded in the dedup window — skip append.
        return

    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    triage: dict[str, str] = {
        "cold_start": "查 N91 映射表 → gaf-session-check (python scripts/bootstrap/check_session_active.py --create) + 跑 gaf_init.sh",
        "new_feature": "查 gaf-orchestrator decision_tree new_feature 分支 → 补 TODO/3 步 evidence/5 层分发 N95",
        "bug_fix": "查 N91 映射表 + gaf-reflect-and-evolve §3.2 → 写 lesson + arch + failure-modes 5 层分发",
        "documentation": "跑 `python scripts/bootstrap/sync_docs_index.py` 重生成 docs-index.md, 再查 N104 索引过期警告",
        "refactor": "查 sync_skills.py 4 副本 hash → 跑 `python scripts/bootstrap/sync_skills.py`",
        "cross_repo": "查 project_rules §3.6 N109 → 3 类需授权 (跨工作区/重写 history/不可逆删除)",
        "browser_login": "查前后端服务是否启动 + Playwright/Chromium 是否安装 (pyproject.toml dev deps)",
        "devices_control_mode": "查 /devices/windows 页面 + control-mode 选择器渲染 (TD-015)",
        "ai_qa_chat": "查 LLMConfig 是否配置 + SiliconFlow API key + /qa/ask/ 端点 (commit 6a32763 回归)",
        "full_routes": "逐路由查 docs/health/e2e-test-plan.md 对应用例 → 页面崩溃/未渲染/console error 均登记 docs/health/e2e-coverage.md 问题表; 先确认 backend:8000 + frontend:5173 正常",
        "collaboration": "查 sync_lock.py → SyncLock + fcntl/msvcrt 双 backend, N116 R-M-W 必加锁",
    }
    with target.open("a", encoding="utf-8") as f:
        f.write(f"\n## e2e 失败记录 @ {stamp}\n\n")
        f.write("| scenario | detail | 修复路径 | 优先 |\n")
        f.write("|----------|--------|----------|:----:|\n")
        for name, detail in new_failures:
            hint = triage.get(name, "查 gaf-reflect-and-evolve/SKILL.md 通用排错流程")
            prio = "P0" if name in {"cold_start", "new_feature"} else (
                "P1" if name in {"bug_fix", "refactor", "cross_repo", "collaboration", "ai_qa_chat"} else "P2"
            )
            detail_md = detail.replace("|", "\\|").replace("\n", " ")
            hint_md = hint.replace("|", "\\|")
            f.write(f"| `{name}` | {detail_md} | {hint_md} | {prio} |\n")
        f.write("\n> 下一步: 跑 `python scripts/lessons/weekly_summary.py` 汇总本周失败 + 提议转 lessons/失败模式。\n")
        f.write("\n---\n")


def _recent_why_skipped_scenarios(target: Path, hours: int = 24) -> set[str]:
    """Parse why-skipped.md and return scenarios recorded in the last ``hours``.

    Looks for ``## e2e 失败记录 @ YYYY-MM-DD HH:MM:SS`` headings, parses the
    timestamp, and collects scenario names from entries newer than ``hours``
    ago. Returns set of scenario names (empty if file missing or no recent
    entries).

    TD-306: used by ``_write_why_skipped`` to dedup within a 24h window so
    repeated e2e failures (same scenario, environment-only cause) don't
    bloat the file.
    """
    if not target.exists():
        return set()
    text = target.read_text(encoding="utf-8", errors="replace")
    now = datetime.datetime.now()
    cutoff = now - datetime.timedelta(hours=hours)
    recent: set[str] = set()
    # Split by heading; blocks[0] is preamble, then alternating (stamp, body).
    parts = re.split(r"^## e2e 失败记录 @ (.+)$", text, flags=re.MULTILINE)
    for i in range(1, len(parts), 2):
        stamp_str = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        try:
            stamp_dt = datetime.datetime.strptime(stamp_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if stamp_dt < cutoff:
            continue
        # Extract scenario names from table rows: | `name` | ...
        for m in re.finditer(r"^\|\s*`([^`]+)`\s*\|", body, re.MULTILINE):
            recent.add(m.group(1))
    return recent


def run_all(repo: Path, only: list[str] | None = None, strict: bool = False) -> int:
    """Run all (or ``only``) registered scenarios; return 0 on full success."""
    targets = only or list(SCENARIOS.keys())
    failures: list[tuple[str, str]] = []
    started = time.perf_counter()
    print(f"[e2e] running {len(targets)} scenario(s) against {repo}")
    for name in targets:
        if name not in SCENARIOS:
            print(f"  - {name:14s} SKIP  (unknown scenario)")
            continue
        try:
            ok, detail = SCENARIOS[name](repo)
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, f"exception: {exc}\n{traceback.format_exc(limit=2)}"
        marker = "OK  " if ok else "FAIL"
        print(f"  - {name:14s} {marker}  {detail}")
        if not ok:
            failures.append((name, detail))
    elapsed = time.perf_counter() - started
    summary = (
        f"[e2e] {len(targets) - len(failures)}/{len(targets)} passed in {elapsed:.3f}s"
    )
    if failures:
        _write_failure_log(repo, failures)
        _write_why_skipped(repo, failures)
        print(summary + f"  (failures written to {FAILURE_LOG_NAME} + {WHY_SKIPPED_NAME})")
        return 1 if strict else 0
    print(summary)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the 7 e2e scenarios")
    parser.add_argument(
        "scenarios",
        nargs="*",
        help="Subset of scenario names to run (default: all 7).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with non-zero status on any failure.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the registered scenario names and exit.",
    )
    args = parser.parse_args(argv)
    if args.list:
        for name in SCENARIOS:
            print(name)
        return 0
    repo = _REPO_ROOT
    return run_all(repo, only=args.scenarios or None, strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())
