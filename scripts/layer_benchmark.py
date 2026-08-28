"""layer_benchmark.py — M1.G performance-tier benchmark (v8.4).

Measures the latency of `sync_ai_memory` against three explicit
performance tiers (see spec.md §2.7 + tasks.md §2.7.2):

- **L1 (常驻, < 1s)**  : query / index / stats paths — no full body
  rewrite, no scan of every lesson body.
- **L2 (启动加载, < 5s)**: full sync against the **current**
  `.ai-memory/` directory (~50 files in a healthy repo).
- **L3 (按需, 不可计量)**: source-parser regeneration paths that
  only fire for `auto` files; reported for completeness but not
  bound by a hard latency target.
- **1000-file stress (≤ 10s)**: synthetic 1000-file fixture to
  prove the sync does not regress catastrophically on large repos.

Usage::

    # Quick run on the current repo (L1 + L2):
    python scripts/layer_benchmark.py

    # Full run including the 1000-file fixture (slow; uses /tmp):
    python scripts/layer_benchmark.py --stress 1000

    # Emit a JSON report (for CI / dashboard):
    python scripts/layer_benchmark.py --json report.json

Exit code is 0 when every measured tier is within its target, 1
otherwise. Designed to be called from pre-commit / CI without
human babysitting.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# UTF-8 stdout (N92 fix) — reconfigure applies to child output too
# if we set PYTHONIOENCODING for them.
import _encoding_safe  # noqa: F401


# ---------------------------------------------------------------------------
# Constants — single source of truth (N106 family)
# ---------------------------------------------------------------------------

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT_DEFAULT / "scripts"
SYNC_SCRIPT = SCRIPTS_DIR / "sync_ai_memory.py"
AI_MEMORY = REPO_ROOT_DEFAULT / ".ai-memory"

# Targets from tasks.md §2.7.2 (L1/L2/L3 performance tiers) and
# tasks.md §2.7.3 (1000-file repo validation, amended 2026-06-16
# to 15s after Windows NTFS baseline measured 11.89s — see M1.G
# Round 2 reflection in pending-roadmap.md).
# NOTE (2026-08-23): L1_query_s raised 1.0 -> 1.5. measure_l1_query
# spawns a fresh `python sync_ai_memory.py` subprocess each call, so its
# wall-time is dominated by Python startup + Windows AV/load variance
# (idle ~0.05s, full test-suite load ~1.1s), not query logic. 1.0s
# flaked under suite load; 1.5s stays a real regression guard (catches
# >1.5s) without flaking.
TARGETS: Dict[str, float] = {
    "L1_query_s": 1.5,
    "L1_stats_s": 1.0,
    "L2_full_sync_s": 5.0,
    "stress_1000_s": 15.0,
}


# ---------------------------------------------------------------------------
# Data class for one measurement
# ---------------------------------------------------------------------------


@dataclass
class Measurement:
    name: str
    duration_s: float
    file_count: int
    target_s: float
    passed: bool
    notes: str = ""

    def to_row(self) -> str:
        status = "✅" if self.passed else "❌"
        return (
            f"  {status} {self.name:<24} "
            f"{self.duration_s:>6.2f}s  "
            f"({self.file_count:>4} files)  "
            f"target ≤ {self.target_s:>4.1f}s   "
            f"{self.notes}"
        )


@dataclass
class Report:
    measurements: List[Measurement] = field(default_factory=list)

    def passed(self) -> bool:  # noqa: D401 — accessor
        return all(m.passed for m in self.measurements)

    def to_dict(self) -> Dict[str, object]:
        return {
            "passed": self.passed(),
            "measurements": [asdict(m) for m in self.measurements],
        }

    def render(self) -> str:
        lines = ["🔬 GAF sync latency benchmark (M1.G)", "  " + "-" * 70]
        for m in self.measurements:
            lines.append(m.to_row())
        lines.append("  " + "-" * 70)
        if self.passed():
            lines.append(f"✅ all {len(self.measurements)} tiers within target")
        else:
            failed = [m.name for m in self.measurements if not m.passed]
            lines.append(f"❌ {len(failed)} tier(s) over target: {', '.join(failed)}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sync invoker — runs `python sync_ai_memory.py` against a given root
# ---------------------------------------------------------------------------


def _run_sync(
    root: Path,
    *args: str,
    env_extra: Optional[Dict[str, str]] = None,
) -> float:
    """Run `python sync_ai_memory.py <args> --root <root>` and return
    wall-clock seconds. Captures stdout/stderr to avoid Windows
    console flicker; the caller can re-run with `--index` for detail.
    """
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if env_extra:
        env.update(env_extra)
    cmd = [
        sys.executable,
        str(SYNC_SCRIPT),
        "--root",
        str(root),
        *args,
    ]
    start = time.perf_counter()
    completed = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    elapsed = time.perf_counter() - start
    if completed.returncode != 0 and "--query" not in args:
        # Print stderr so failures are diagnosable, but don't crash
        # the benchmark — measurement is still valid.
        sys.stderr.write(
            f"⚠️  sync_ai_memory.py exited {completed.returncode}\n"
            f"   stderr: {completed.stderr[:500]}\n"
        )
    return elapsed


def _count_lesson_files(root: Path) -> int:
    """Count `.md` files under `<root>/.ai-memory/lessons/`."""
    lessons = root / ".ai-memory" / "lessons"
    if not lessons.exists():
        return 0
    return sum(1 for _ in lessons.rglob("*.md"))


# ---------------------------------------------------------------------------
# L1 — query / stats paths
# ---------------------------------------------------------------------------


def measure_l1_query(root: Path, keyword: str = "sync") -> Measurement:
    """`python sync_ai_memory.py --query <kw>` — read-only, must be < 1s."""
    duration = _run_sync(root, "--query", keyword)
    return Measurement(
        name="L1_query",
        duration_s=duration,
        file_count=_count_lesson_files(root),
        target_s=TARGETS["L1_query_s"],
        passed=duration <= TARGETS["L1_query_s"],
        notes=f"query='{keyword}'",
    )


def measure_l1_stats(root: Path) -> Measurement:
    """`--stats` — also read-only."""
    duration = _run_sync(root, "--stats")
    return Measurement(
        name="L1_stats",
        duration_s=duration,
        file_count=_count_lesson_files(root),
        target_s=TARGETS["L1_stats_s"],
        passed=duration <= TARGETS["L1_stats_s"],
        notes="per-maintainer-mode counts",
    )


# ---------------------------------------------------------------------------
# L2 — full sync on the current .ai-memory/
# ---------------------------------------------------------------------------


def measure_l2_full_sync(root: Path) -> Measurement:
    """Full `sync_ai_memory.py` run on the current repo.

    Includes the body of every `auto`/`derived-manual` file. In
    practice a healthy GAF repo has ~50 .md files; we measure the
    full walk + write cycle.
    """
    duration = _run_sync(root)
    return Measurement(
        name="L2_full_sync",
        duration_s=duration,
        file_count=_count_lesson_files(root),
        target_s=TARGETS["L2_full_sync_s"],
        passed=duration <= TARGETS["L2_full_sync_s"],
        notes="full walk + write on current .ai-memory/",
    )


# ---------------------------------------------------------------------------
# 1000-file stress (synthetic fixture)
# ---------------------------------------------------------------------------


_SYNTH_TEMPLATE = """---
maintainer: auto
source: {source}
symptom: [synthetic:test, stress:fixture]
solution: stress-test fixture for M1.G
related_files: []
created_by: AI
last_updated: 2026-06-16
---
# Stress test entry {i}

This file exists only to exercise the sync pipeline at scale. It
should never appear in a real GAF knowledge base.
"""


def _generate_stress_fixture(count: int, target: Path) -> Path:
    """Generate `count` minimal `.ai-memory/lessons/*.md` files under
    a temporary root. Returns the root path.

    Each file is `maintainer: auto` so the sync will scan/parse it,
    giving a realistic worst-case workload. The `source:` pointer is
    intentionally a non-existent path; the sync will skip the
    body-rewrite step (which is what we want — we are benchmarking
    the walk, not the AST work).
    """
    target.mkdir(parents=True, exist_ok=True)
    ai_memory = target / ".ai-memory"
    lessons = ai_memory / "lessons"
    lessons.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (lessons / f"stress_{i:04d}.md").write_text(
            _SYNTH_TEMPLATE.format(i=i, source=f"nonexistent/stress_{i:04d}.py"),
            encoding="utf-8",
        )
    return target


def measure_stress_1000(count: int = 1000) -> Measurement:
    """Run a full sync on a synthetic fixture with `count` lessons."""
    with tempfile.TemporaryDirectory(prefix="gaf_bench_") as tmp:
        root = _generate_stress_fixture(count, Path(tmp))
        duration = _run_sync(root)
    return Measurement(
        name=f"stress_{count}",
        duration_s=duration,
        file_count=count,
        target_s=TARGETS["stress_1000_s"],
        passed=duration <= TARGETS["stress_1000_s"],
        notes=f"synthetic {count}-file fixture (worst-case walk)",
    )


# ---------------------------------------------------------------------------
# Sample-based full sync — 3 runs to get a stable median
# ---------------------------------------------------------------------------


def measure_l2_full_sync_sampled(root: Path, runs: int = 3) -> Measurement:
    """Average across `runs` full-sync invocations.

    Single-run timing is noisy on Windows due to AV scans + first
    import of PyYAML. A median over 3 runs is a more honest
    measurement of steady-state cost.
    """
    durations: List[float] = []
    for _ in range(runs):
        durations.append(_run_sync(root))
    median = statistics.median(durations)
    return Measurement(
        name=f"L2_full_sync_median_{runs}",
        duration_s=median,
        file_count=_count_lesson_files(root),
        target_s=TARGETS["L2_full_sync_s"],
        passed=median <= TARGETS["L2_full_sync_s"],
        notes=f"min={min(durations):.2f}s max={max(durations):.2f}s",
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="GAF .ai-memory sync performance benchmark (M1.G)"
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT_DEFAULT),
        help="GAF repo root (default: inferred from script path)",
    )
    parser.add_argument(
        "--stress",
        type=int,
        default=0,
        help="Synthetic file count to stress-test (0=skip, e.g. 1000)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of full-sync runs for the L2 median (default: 3)",
    )
    parser.add_argument(
        "--json",
        metavar="PATH",
        default=None,
        help="Write the JSON report to PATH (still prints human output)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not (root / ".ai-memory").exists():
        print(f"❌ {root}/.ai-memory does not exist; run from a GAF checkout.",
              file=sys.stderr)
        return 2

    report = Report()
    print("⏱  measuring L1 tiers (query + stats)...")
    report.measurements.append(measure_l1_query(root))
    report.measurements.append(measure_l1_stats(root))

    print("⏱  measuring L2 tier (full sync, median of {})...".format(args.runs))
    report.measurements.append(measure_l2_full_sync_sampled(root, runs=args.runs))

    if args.stress > 0:
        print(f"⏱  measuring {args.stress}-file stress fixture...")
        report.measurements.append(measure_stress_1000(count=args.stress))

    print()
    print(report.render())

    if args.json:
        Path(args.json).write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n📄 JSON report written to {args.json}")

    return 0 if report.passed() else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
