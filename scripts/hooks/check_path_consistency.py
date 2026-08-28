"""check_path_consistency.py - N107 路径一致性检查器 (v8.4 M1.A 后续 [B] 类)

Scans the GAF repository for code that uses inline path construction
(``Path(\"foo\") / \"bar.json\"``) instead of the module-level constants
that act as a single source of truth (N106 fix / SYNC_STATE pattern).

This is the enforcement companion to the N106 lesson (sync_ai_memory.py
path drift) and project_rules.md §5.2.1 (SYNC_STATE constant usage).

Severity levels
---------------
* **error** - The path appears in ``.gitignore`` AND is referenced
  multiple times. Drift in such a path is invisible to ``git status``
  and high-risk. The hook will exit 1 and block the commit.
* **warning** - The path is constructed inline (single reference)
  but the literal string matches a known canonical name (e.g.
  ``sync-state.json``). The hook will emit a non-fatal warning.

The known-path catalogue mirrors ``project_rules.md §5.2.1`` plus
the spec.md §5 file tree. Adding a new canonical file requires
updating KNOWN_CANONICAL_PATHS below.

Usage
-----
    python scripts/hooks/check_path_consistency.py                # scan default repo
    python scripts/hooks/check_path_consistency.py --root <repo>  # explicit root
    python scripts/hooks/check_path_consistency.py --no-fail      # warn-only mode
    python scripts/hooks/check_path_consistency.py --fix         # auto-fix (Phase 2)

Exit codes
----------
    0 - no error-level violations (warnings may be present)
    1 - error-level violations found
    2 - configuration / argument error
"""
# ruff: noqa: I001  # _encoding_safe must stay first; do not reorder imports
from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path
_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import _encoding_safe  # noqa: E402,F401  (must be first; reconfigures stdout to UTF-8)

import argparse  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
from collections import defaultdict  # noqa: E402
from pathlib import Path  # noqa: E402

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT_DEFAULT / "scripts"
GITIGNORE_PATH = REPO_ROOT_DEFAULT / ".gitignore"


# ---------------------------------------------------------------------------
# TD-348: mtime-based manifest cache (复用 sync_ai_memory.py / check_doc_path_drift.py 模式)
# ---------------------------------------------------------------------------

CACHE_FILE_NAME = ".path-consistency-cache.json"


def _cache_path(root: Path) -> Path:
    """Return path to .ai-memory/.path-consistency-cache.json."""
    return root / ".ai-memory" / CACHE_FILE_NAME


def _build_mtime_manifest(repo_root: Path) -> dict[str, int]:
    """Build {relative_path: st_mtime_ns} for all scanned files.

    Walks the repo with the same SKIP_DIRS / SCAN_EXTENSIONS filter as the
    main scan, plus .gitignore (severity depends on gitignore patterns).
    If this manifest is unchanged since the last successful scan, the
    error_count / warning_count result is guaranteed identical.

    TD-348 fix: use ``repo_root/.gitignore`` (not module-level GITIGNORE_PATH)
    so cache invalidation actually fires when the target repo's .gitignore
    changes. The module-level constant was a pre-existing bug that made the
    cache silently miss invalidation on non-default repos.
    """
    import os

    manifest: dict[str, int] = {}
    # Include .gitignore in manifest (severity depends on patterns).
    # TD-348: use repo_root/.gitignore, not module-level GITIGNORE_PATH.
    gitignore = repo_root / ".gitignore"
    if gitignore.is_file():
        try:
            manifest[".gitignore"] = gitignore.stat().st_mtime_ns
        except OSError:
            pass
    # Include this checker script itself: logical changes (SKIP_DIRS,
    # regexes, exemption rules) must invalidate the cache, otherwise a
    # stale cached count persists after the rule set shrinks — e.g. a
    # cache built at 186 warnings kept reporting 186 after the warnings
    # were eliminated, because none of the scanned files had changed.
    self_path = Path(__file__).resolve()
    try:
        self_rel = str(self_path.relative_to(repo_root)).replace("\\", "/")
        manifest[self_rel] = self_path.stat().st_mtime_ns
    except (OSError, ValueError):
        pass
    # Files auto-written by governance-batch itself (not user edits).
    # Excluding prevents N+1 cache miss: batch end → auto-write → next batch cache miss.
    # performance-baseline.md is a timestamp log; its content doesn't affect hook results.
    AUTO_WRITTEN_PATHS = frozenset({
        "docs/reference/performance-baseline.md",  # _append_performance_baseline in gaf_governance_batch.py
    })
    for dirpath, dirs, files in os.walk(repo_root):
        # Prune SKIP_DIRS in-place (same as walk_repo)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if not fname.endswith(SCAN_EXTENSIONS):
                continue
            full = Path(dirpath) / fname
            try:
                rel = str(full.relative_to(repo_root)).replace("\\", "/")
                if rel in AUTO_WRITTEN_PATHS:
                    continue
                manifest[rel] = full.stat().st_mtime_ns
            except OSError:
                continue
    return manifest


def _load_cache(repo_root: Path) -> dict | None:
    """Load cache JSON. Returns None if missing or corrupt."""
    path = _cache_path(repo_root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(
    repo_root: Path,
    manifest: dict[str, int],
    last_exit_code: int,
    last_error_count: int,
    last_warning_count: int,
    per_file_hits: dict[str, list[tuple[int, str, str]]] | None = None,
) -> None:
    """Write cache JSON with per-file hits (TD-390 incremental).

    ``per_file_hits`` maps rel_path → its list of (line, literal, category).
    On a later cache miss caused by a small change, the caller can re-scan
    only the changed files and reuse these results for everything else,
    instead of re-scanning the whole repo.
    """
    path = _cache_path(repo_root)
    cache = {
        "manifest": manifest,
        "last_exit_code": last_exit_code,
        "last_error_count": last_error_count,
        "last_warning_count": last_warning_count,
        "per_file_hits": dict(per_file_hits) if per_file_hits is not None else {},
        "version": 2,
    }
    try:
        path.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        # Non-fatal: cache write failure should not break the hook.
        pass


def _check_cache_valid(repo_root: Path) -> tuple[bool, int, int, int]:
    """Check if cache is valid (all mtimes match last successful scan).

    Returns (cache_hit, cached_exit_code, cached_error_count,
    cached_warning_count). Cache hit means safe to skip full scan.
    """
    cache = _load_cache(repo_root)
    if cache is None:
        return False, 0, 0, 0
    cached_manifest = cache.get("manifest")
    if not isinstance(cached_manifest, dict):
        return False, 0, 0, 0
    cached_exit_code = cache.get("last_exit_code", 0)
    cached_error_count = cache.get("last_error_count", 0)
    cached_warning_count = cache.get("last_warning_count", 0)
    if not isinstance(cached_exit_code, int):
        return False, 0, 0, 0
    if not isinstance(cached_error_count, int):
        return False, 0, 0, 0
    if not isinstance(cached_warning_count, int):
        return False, 0, 0, 0
    current_manifest = _build_mtime_manifest(repo_root)
    if cached_manifest != current_manifest:
        return False, 0, 0, 0
    return True, cached_exit_code, cached_error_count, cached_warning_count

# File extensions we scan for inline path literals
# spec-13 Phase 3 [A]-R4-4: include `.md` to catch script path drift in docs.
SCAN_EXTENSIONS = (".py", ".ts", ".tsx", ".js", ".jsx", ".md")

# Directories we never scan (3rd-party, build artefacts, generated docs)
SKIP_DIRS = frozenset(
    {
        "node_modules",
        "dist",
        "build",
        ".git",
        "__pycache__",
        "venv",
        ".venv",
        "migrations",
        "evidence",  # evidence files are docs, not code paths
        "_templates",
        "archive",  # archived one-off helpers are not subject to active checks
        ".trash",  # spec-13 Phase 4: temp scripts, not subject to active checks
        ".ai-memory",  # AI memory store (lessons/specs/meta) is prose, not project code; absolute paths there are legitimate examples, not constant-able literals
    }
)

# Canonical filenames that should be referenced via module-level
# constants. The full path "GAF/.ai-memory/<name>" matches spec.md §5.
# Each entry carries a severity hint: "error" if it appears in
# .gitignore (drift invisible), "warning" otherwise.
KNOWN_CANONICAL_PATHS: dict[str, str] = {
    "sync-state.json": "error",  # .gitignore line 133
    "sync-state.yaml": "warning",
    "lessons.json": "warning",
    "docs-index.md": "warning",
}

# spec-13 Phase 3 [A]-R4-4: Known script canonical paths.
# Maps script basename → required subdirectory under `scripts/`.
# Used by the new SCRIPT_REF_RE check to detect drift like
# `python scripts/sync_ai_memory.py` (should be `scripts/bootstrap/sync_ai_memory.py`).  # path-check-ignore
KNOWN_SCRIPTS: dict[str, str] = {
    # scripts/bootstrap/
    "sync_ai_memory.py": "scripts/bootstrap/",
    "sync_docs_index.py": "scripts/bootstrap/",
    "sync_skills.py": "scripts/bootstrap/",
    "sync_session_context.py": "scripts/bootstrap/",
    "check_session_active.py": "scripts/bootstrap/",
    "check_env.py": "scripts/bootstrap/",
    # scripts/lessons/
    "promote_lessons.py": "scripts/lessons/",
    "extract_lessons.py": "scripts/lessons/",
    "append_lesson_block.py": "scripts/lessons/",
    "weekly_summary.py": "scripts/lessons/",
    "bypass_weekly_review.py": "scripts/lessons/",
    "generate_architecture_mistakes_summary.py": "scripts/lessons/",
    # scripts/hooks/
    "check_3step_evidence.py": "scripts/hooks/",
    "check_spec_consistency.py": "scripts/hooks/",
    "check_lessons_updated.py": "scripts/hooks/",
    "check_git_status_after_hook.py": "scripts/hooks/",
    "check_yn_matrices_index.py": "scripts/hooks/",
    "check_path_consistency.py": "scripts/hooks/",
    "check_skip_rate.py": "scripts/hooks/",
    # scripts/ (root)
    "select_reflection_checks.py": "scripts/",
    "check_big_change.py": "scripts/",
    "gaf_init.sh": "scripts/",
    "gaf-commit.sh": "scripts/",
}

# Regex to match inline path construction patterns.
# Examples that match:
#   Path("foo") / "bar.json"
#   pathlib.Path(root) / "sync-state.json"
#   Path(__file__).parent / "x.json"
# The pattern captures the trailing string literal after the last `/`.
INLINE_PATH_RE = re.compile(
    r"""(?:Path|pathlib\.Path)\s*\([^)]*\)\s*/\s*['"]([^'"]+)['"]"""
)

# A looser pattern for plain string concatenation that is not Path-anchored.
#   "foo" / "bar.json"
# We intentionally keep this conservative (only catches the "literal / literal"
# shape) to avoid false positives on dict keys.
STRING_SLASH_RE = re.compile(r"""['\"]([a-zA-Z0-9_\-./]+\.(?:json|ya?ml|md))['\"]\s*/\s*['\"]""")

# Absolute Windows path literals inside string quotes.
# Catches both raw strings (r"C:\...") and escaped strings ("C:\\...").
# Examples: Path(r"d:\foo\bar.md") or r"C:/Users/x.json"
ABS_PATH_RE = re.compile(r"""(?i)(?:r|R)?['\"]([a-zA-Z]:\\+[^'\"\n]+)['\"]""")

# Absolute paths that point at external tools / OS install locations
# (Android emulators, ADB, Program Files / System32, user game dirs) are
# legitimate discovery targets and MUST stay absolute. Exempting them from
# the "prefer repo-relative constant" rule avoids N106 false positives on
# emulator/ADB discovery code (e.g. emulator_discovery.py enumerating
# LDPlayer/MuMu/BlueStacks/Nox/Memu install paths).
KNOWN_EXTERNAL_PATH_RE = re.compile(
    r"(?i)"
    r"ldplayer|bluestacks|nox|memu|mumu"
    r"|adb\.exe|hd-adb\.exe"
    r"|\.vbox"
    r"|program files|system32|leidian"
    r"|\\\\game\\\\"
)

# spec-13 Phase 3 [A]-R4-4: Script reference patterns in docs/code.
# Catches `python scripts/X.py`, `python GAF/scripts/X.py`, `bash scripts/X.sh`,
# and bare `scripts/X.py` forms inside backticks or quotes.
# Captures the full path (e.g. "scripts/bootstrap/sync_ai_memory.py") so we can verify
# the subdirectory matches KNOWN_SCRIPTS.
SCRIPT_REF_RE = re.compile(
    r"""(?x)
    (?:`|'|"|)
    (?:python\s+|bash\s+|conda\s+run\s+-n\s+\w+\s+python\s+)?  # optional launcher
    (?:GAF/)?                                                    # optional repo prefix
    (scripts/[^\s`'"]+\.py|scripts/[^\s`'"]+\.sh)               # capture script path
    (?:`|'|"|)
    """
)


def load_gitignore(repo_root: Path) -> list[str]:
    """Return the list of patterns declared in .gitignore (best-effort).

    TD-348 fix: use ``repo_root/.gitignore`` (not module-level GITIGNORE_PATH)
    so the patterns actually reflect the target repo. The module-level
    constant was a pre-existing bug that always loaded D:\\code\\GAF\\.gitignore
    regardless of --root.
    """
    gitignore = repo_root / ".gitignore"
    if not gitignore.exists():
        return []
    patterns: list[str] = []
    for raw in gitignore.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Strip trailing slash for filename matching
        patterns.append(line.rstrip("/"))
    return patterns


def is_gitignored(basename: str, patterns: list[str]) -> bool:
    """Return True if the basename matches any gitignore pattern."""
    for pat in patterns:
        if pat == basename:
            return True
        # Wildcard patterns: *.json, sync-state.*, etc.
        if "*" in pat:
            # Convert shell-style wildcard to a simple regex
            regex = "^" + re.escape(pat).replace(r"\*", ".*") + "$"
            if re.match(regex, basename):
                return True
    return False


def is_canonical_basename(basename: str) -> bool:
    """True if basename (e.g. sync-state.json) is a known canonical path."""
    return basename in KNOWN_CANONICAL_PATHS


def _line_has_triple_quote(line: str, quote: str) -> bool:
    """Return True if the line contains an odd number of `quote` triples."""
    return line.count(quote) % 2 == 1


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Return [(line_no, literal_string, category), ...] for path hits.

    Categories:
        - "inline": Path(...) / "literal" or "literal" / "literal"
        - "abs":    absolute path literal such as r"C:\\foo\\bar.md"
        - "script_ref": scripts/X.py reference (spec-13 Phase 3 — verify subdir)

    N171 performance optimization (2026-07-18):
    Pre-filters file content with cheap ``str.find()`` checks before
    running any regex. Most files (docs, configs) contain none of the
    trigger tokens, so we skip all 4 regex.finditer calls per line.
    Measured: 1.28s → ~0.3s on 1263-file repo (4x speedup).
    """
    hits: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return hits

    # N171 optimization: pre-filter with cheap substring checks.
    # If none of the trigger tokens appear in the file, skip all regex.
    # This avoids 1.1M+ finditer calls on files that have no path literals.
    # Use lowercase for case-insensitive prefix matching where safe.
    text_lower = text.lower()
    has_path_construct = "path(" in text_lower or "pathlib" in text_lower
    has_slash_literal = "/" in text and ('.json' in text_lower or '.yaml' in text_lower or '.yml' in text_lower or '.md' in text_lower)
    has_abs_path = ":\\" in text or ":/" in text
    has_script_ref = "scripts/" in text_lower and (".py" in text or ".sh" in text)
    if not (has_path_construct or has_slash_literal or has_abs_path or has_script_ref):
        return hits

    # Build per-file regex tuple based on pre-filter (avoid running 4 regex
    # when only 1 category is relevant).
    active_regexes: list[tuple[re.Pattern, str]] = []
    if has_path_construct or has_slash_literal:
        active_regexes.append((INLINE_PATH_RE, "inline"))
        if has_slash_literal:
            active_regexes.append((STRING_SLASH_RE, "inline"))
    if has_abs_path:
        active_regexes.append((ABS_PATH_RE, "abs"))
    if has_script_ref:
        active_regexes.append((SCRIPT_REF_RE, "script_ref"))

    in_docstring: str | None = None  # None, '"""', or "'''"
    for idx, line in enumerate(text.splitlines(), start=1):
        # Skip pure comments and lines explicitly marked as intentional.
        stripped = line.lstrip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue
        if "# path-check-ignore" in line or "# noqa: path-check" in line:
            continue

        # Skip triple-quoted docstrings; literal examples inside them are
        # documentation, not executable code.
        if in_docstring is not None:
            if in_docstring in line:
                in_docstring = None
            continue
        for quote in ('"""', "'''"):
            if quote in line:
                # Single-line docstring: skip entire line.
                # Multi-line: enter skip mode.
                if _line_has_triple_quote(line, quote):
                    in_docstring = quote
                break
        if in_docstring is not None:
            continue

        for regex, category in active_regexes:
            for match in regex.finditer(line):
                hits.append((idx, match.group(1), category))
    return hits


def walk_repo(repo_root: Path) -> list[Path]:
    """Yield candidate files under repo_root matching SCAN_EXTENSIONS.

    Uses os.walk with directory pruning (dirs[:] modification) to skip
    SKIP_DIRS entries during traversal, avoiding expensive rglob descent
    into node_modules and other large 3rd-party directories.
    """
    import os

    candidates: list[Path] = []
    for dirpath, dirs, files in os.walk(repo_root):
        # Prune SKIP_DIRS in-place so os.walk does not descend into them.
        # This is dramatically faster than rglob("*") + post-filter on
        # large repos with node_modules (50k+ files).
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if not fname.endswith(SCAN_EXTENSIONS):
                continue
            candidates.append(Path(dirpath) / fname)
    return candidates


def evaluate(
    hits_by_file: dict[Path, list[tuple[int, str, str]]],
    patterns: list[str],
    repo_root: Path | None = None,
) -> tuple[int, int, list[str]]:
    """Aggregate hits and return (error_count, warning_count, messages).

    TD-348 fix: ``repo_root`` parameter replaces hardcoded ``REPO_ROOT_DEFAULT``
    in ``path.relative_to(...)``. Without this, the hook crashes on any
    non-default repo (e.g. temp dirs in tests, or alternate checkouts).
    Defaults to ``REPO_ROOT_DEFAULT`` for backwards compatibility.
    """
    error_count = 0
    warning_count = 0
    messages: list[str] = []

    # Group by basename to detect "referenced multiple times" (error severity)
    basename_files: dict[str, list[Path]] = defaultdict(list)
    for path, hits in hits_by_file.items():
        for _line_no, literal, category in hits:
            if category != "inline":
                continue
            basename = Path(literal).name
            if is_canonical_basename(basename) and path not in basename_files[basename]:
                basename_files[basename].append(path)

    # TD-348: use caller-supplied repo_root for relative path computation.
    root_for_rel = repo_root if repo_root is not None else REPO_ROOT_DEFAULT
    for path in sorted(hits_by_file.keys()):
        rel = path.relative_to(root_for_rel)
        under_scripts = "scripts" in rel.parts
        for line_no, literal, category in hits_by_file[path]:
            if category == "abs":
                # N106 false-positive guard: absolute paths inside test
                # fixtures or pointing at external tools / OS install
                # locations (emulator/ADB discovery) are legitimate and
                # exempt from the "prefer repo-relative constant" warning.
                if (
                    "tests" in rel.parts
                    or rel.suffix == ".md"
                    or KNOWN_EXTERNAL_PATH_RE.search(literal)
                ):
                    continue
                snippet = literal if len(literal) <= 60 else literal[:57] + "..."
                if under_scripts:
                    error_count += 1
                    messages.append(
                        f"ERROR {rel}:{line_no} absolute path literal "
                        f"'{snippet}' (use repo-relative module constant)"
                    )
                else:
                    warning_count += 1
                    messages.append(
                        f"warn  {rel}:{line_no} absolute path literal "
                        f"'{snippet}' (prefer repo-relative constant)"
                    )
                continue

            if category == "script_ref":
                # spec-13 Phase 3 [A]-R4-4: verify script reference subdir.
                # `literal` is like "scripts/bootstrap/sync_ai_memory.py". Extract
                # basename and check KNOWN_SCRIPTS for the canonical prefix.
                # Skip self-references (this checker itself) to avoid noise.
                basename = Path(literal).name
                if basename == "check_path_consistency.py":
                    continue
                expected_prefix = KNOWN_SCRIPTS.get(basename)
                if expected_prefix is None:
                    # Unknown script — not necessarily wrong, skip silently.
                    continue
                # `literal` already starts with "scripts/". Verify the
                # substring right after "scripts/" matches expected_prefix
                # minus the trailing "scripts/" prefix.
                expected_subdir = expected_prefix  # e.g. "scripts/bootstrap/"
                # Normalize: strip leading "scripts/" from expected_prefix
                expected_after_scripts = expected_subdir[len("scripts/"):]
                actual_after_scripts = literal[len("scripts/"):]
                # If actual path starts with the expected subdir, it's correct.
                # Otherwise, drift detected.
                if not actual_after_scripts.startswith(expected_after_scripts):
                    error_count += 1
                    messages.append(
                        f"ERROR {rel}:{line_no} script path drift: "
                        f"'{literal}' should be '{expected_prefix}{basename}'"
                    )
                continue

            basename = Path(literal).name
            severity = KNOWN_CANONICAL_PATHS.get(basename)
            if severity is None:
                continue
            if severity == "error" and is_gitignored(basename, patterns):
                # Promote to error if referenced from 2+ files
                if len(basename_files[basename]) >= 2:
                    error_count += 1
                    messages.append(
                        f"ERROR {rel}:{line_no} inline path '{literal}' "
                        f"(basename gitignored + {len(basename_files[basename])} files)"
                    )
                else:
                    warning_count += 1
                    messages.append(
                        f"warn  {rel}:{line_no} inline path '{literal}' "
                        f"(basename gitignored, single reference)"
                    )
            else:
                warning_count += 1
                messages.append(
                    f"warn  {rel}:{line_no} inline path '{literal}' "
                    f"(known canonical, prefer module constant)"
                )
    return error_count, warning_count, messages


def main() -> int:
    parser = argparse.ArgumentParser(description="GAF path consistency checker (N107)")
    parser.add_argument("--root", default=str(REPO_ROOT_DEFAULT), help="Repository root to scan")
    parser.add_argument("--no-fail", action="store_true", help="Warn-only mode (do not exit 1 on errors)")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="No-op: the checker only surfaces (a) intentionally-exempt absolute paths "
        "and (b) structural path-drift that must be reviewed and fixed by hand, so there "
        "is nothing safe to auto-rewrite. Kept as an explicit flag for clarity.",
    )
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    # Check for a stable GAF marker file. gaf_init.sh stays at scripts/ top level
    # (not moved during the scripts/ reorg) and is the canonical entry point.
    if not (repo_root / "scripts" / "gaf_init.sh").exists():
        print(f"ERROR: {repo_root} does not look like a GAF checkout", file=sys.stderr)
        return 2

    if args.fix:
        # Intentionally a no-op: see --fix help. All ``abs`` warnings are
        # deliberately exempted legitimate paths (emulator/ADB/OS installs,
        # doc examples, tests, .ai-memory); the ``error`` class is structural
        # path-drift that must be reviewed manually, not blindly rewritten.
        print(
            "--fix is a no-op: this checker surfaces only exempt/structural path issues "
            "with nothing safe to auto-rewrite. Fix the printed messages by hand.",
            file=sys.stderr,
        )
        return 0

    # TD-348: mtime cache hit → skip full scan, return last result
    cache_hit, cached_exit_code, cached_error_count, cached_warning_count = _check_cache_valid(repo_root)
    if cache_hit:
        print(
            f"cache hit: {cached_error_count} error(s), {cached_warning_count} warning(s) [from last scan]"
        )
        return cached_exit_code

    patterns = load_gitignore(repo_root)
    current_manifest = _build_mtime_manifest(repo_root)
    prior_cache = _load_cache(repo_root)
    prior_manifest = prior_cache.get("manifest") if prior_cache else None
    prior_pv = prior_cache.get("per_file_hits") if prior_cache else None
    # TD-390 incremental: on a miss (e.g. one file changed), re-scan ONLY the
    # files whose mtime changed (or were added/removed), reusing the cached
    # per-file hits for everything else. Full-repo correctness is preserved
    # because untouched files keep their cached result; only the changed set
    # is re-read, cutting scan I/O from all files to just those.
    if isinstance(prior_pv, dict) and prior_manifest != current_manifest:
        changed = [
            rel for rel in current_manifest
            if prior_manifest.get(rel) != current_manifest[rel]
        ]
        changed += [rel for rel in prior_manifest if rel not in current_manifest]
        changed = sorted(set(changed))
        candidates = [(repo_root / rel, rel) for rel in changed]
        seen_cache = True
    else:
        candidates = [(p, str(p.relative_to(repo_root)).replace("\\", "/")) for p in walk_repo(repo_root)]
        seen_cache = False

    print(f"{'incremental' if seen_cache else 'full'} scanning "
          f"{'changed' if seen_cache else len(candidates)} files under {repo_root}")

    # Rebuild hits_by_file: start from cached non-empty hits of unchanged
    # files, then overwrite entries for changed files (dropping any that now
    # have no hits), and drop entries for deleted files.
    hits_by_file: dict[Path, list[tuple[int, str, str]]] = {}
    if prior_pv is not None:
        changed_rel = {rel for _, rel in candidates}
        for rel, hits in prior_pv.items():
            if (repo_root / rel).is_file() and rel not in changed_rel:
                hits_by_file[repo_root / rel] = [tuple(h) for h in hits]

    for full, rel in candidates:
        if not full.is_file():
            continue
        hits = scan_file(full)
        if hits:
            hits_by_file[full] = hits
        else:
            hits_by_file.pop(full, None)

    error_count, warning_count, messages = evaluate(hits_by_file, patterns, repo_root)

    for line in messages:
        print(line)

    print(f"---\nsummary: {error_count} error(s), {warning_count} warning(s)")
    if error_count and not args.no_fail:
        exit_code = 1
    else:
        exit_code = 0

    # TD-348/TD-390: refresh cache after a scan so the next run can reuse it.
    per_file_hits = {str(p.relative_to(repo_root)).replace("\\", "/"): hits
                     for p, hits in hits_by_file.items()}
    _write_cache(
        repo_root,
        current_manifest,
        exit_code,
        error_count,
        warning_count,
        per_file_hits,
    )

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
