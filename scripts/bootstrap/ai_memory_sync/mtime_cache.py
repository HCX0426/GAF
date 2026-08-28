"""mtime cache domain (s38 split from sync_ai_memory.py, TD-365).

Manifest-based cache for the .ai-memory sync loop; skips the main loop and
counter-sync when all relevant mtimes are unchanged since the last run.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Dict, Optional

# Cache validity must include counter-sync dependency files (lessons/README.md,
# yn-matrices.md, archived-lessons.md, project_rules.md) — if any of these
# change, counter-sync helpers may need to update their target fields.
# ---------------------------------------------------------------------------

CACHE_FILE_NAME = ".sync-cache.json"

# Files outside .ai-memory/**/*.md that counter-sync helpers depend on.
# Changes to these files invalidate the cache (because counter-sync output
# may differ even if .ai-memory/*.md are unchanged).
CACHE_EXTERNAL_DEPS = [
    ".skills/rules/project_rules.md",
]


def _cache_path(root: Path) -> Path:
    """Return path to .ai-memory/.sync-cache.json."""
    return root / ".ai-memory" / CACHE_FILE_NAME


def _build_mtime_manifest(root: Path) -> Dict[str, int]:
    """Build {relative_path: st_mtime_ns} for all .md files relevant to sync.

    Scans:
    - .ai-memory/**/*.md (main scan target of _iter_markdown_files)
    - .skills/rules/project_rules.md (counter-sync dep _sync_archived_count_in_rules)

    If this manifest is unchanged since the last successful sync, the
    handle_file() results and counter-sync outputs are guaranteed identical.
    """
    manifest: Dict[str, int] = {}
    ai_memory = root / ".ai-memory"
    if ai_memory.exists():
        for path in ai_memory.rglob("*.md"):
            if path.is_file():
                try:
                    rel = str(path.relative_to(root)).replace("\\", "/")
                    manifest[rel] = path.stat().st_mtime_ns
                except OSError:
                    continue
    for dep_rel in CACHE_EXTERNAL_DEPS:
        dep_path = root / dep_rel
        if dep_path.is_file():
            try:
                manifest[dep_rel] = dep_path.stat().st_mtime_ns
            except OSError:
                pass
    return manifest


def _load_cache(root: Path) -> Optional[Dict[str, object]]:
    """Load cache JSON. Returns None if missing or corrupt."""
    path = _cache_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(root: Path, manifest: Dict[str, int]) -> None:
    """Write cache JSON. Called after a successful full sync."""
    path = _cache_path(root)
    cache = {
        "manifest": manifest,
        "last_run": _dt.datetime.now().isoformat(timespec="seconds"),
        "version": 1,
    }
    try:
        path.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        # Non-fatal: cache write failure should not break sync.
        # Next run will simply be a cache miss.
        pass


def _check_cache_valid(root: Path) -> bool:
    """Check if cache is valid (all mtimes match last successful sync).

    Returns True if cache hit (safe to skip main loop + counter-sync).
    Returns False if cache miss (must run full sync).
    """
    cache = _load_cache(root)
    if cache is None:
        return False
    cached_manifest = cache.get("manifest")
    if not isinstance(cached_manifest, dict):
        return False
    current_manifest = _build_mtime_manifest(root)
    return cached_manifest == current_manifest
