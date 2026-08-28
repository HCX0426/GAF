"""sync_ai_memory.py — GAF .ai-memory knowledge base synchronizer (v8.3.1).

This is the core tool for keeping `GAF/.ai-memory/` in sync with the
source code it documents. It supports three maintainer modes declared
in each file's front matter:

- `auto`: regenerate the file body from `source:` declaration.
- `derived-manual`: print a hint to the AI; do not auto-rewrite.
- `manual`: skip; only humans (or AI with explicit instruction) edit.

The tool exposes several commands used by the v8.3.1 hard-constraint
pipeline:

    python sync_ai_memory.py                     # full sync
    python sync_ai_memory.py --query <keyword>   # fuzzy search
    python sync_ai_memory.py --root <path>       # operate on a
                                                  # different repo
    python sync_ai_memory.py --dry-run           # report only
    python sync_ai_memory.py --index             # print summary
    python sync_ai_memory.py --stats             # per-mode counts

Hook-aware behaviour (v8.4 N105 fix):

    When invoked from a pre-commit hook, the framework sets
    `PRE_COMMIT=1` in the environment. In that context we treat
    `auto` mode files as READ-ONLY — we still scan them, but the
    regeneration step is suppressed to avoid clobbering files
    produced by other sync tools (e.g. `sync_docs_index.py` for
    `docs-index.md`). The hook runner is informed via a clear
    warning so any stale index triggers a developer-visible error
    rather than a silent overwrite.

Front matter format (YAML between two `---` lines, see spec.md §3):

    ---
    maintainer: auto|derived-manual|manual
    source: backend/foo/urls.py
    load_when: [新功能, Bug修复]
    priority: high
    symptom: [popup:agent:duplicate, 中文同义词, 英文同义词]
    solution: 一句话解决思路
    related_files: [path/to/file.py]
    created_by: AI|user
    generated: 2026-06-14
    auto_updated: 2026-06-14
    ---

v8.3.1 cross-language source parsing (M1.B scope; this M0.B
implementation handles Markdown front matter + Python AST placeholders
for forward compatibility).
"""

from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path
_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import _encoding_safe  # noqa: F401  (must be first; reconfigures stdout to UTF-8)

import argparse
import contextlib
import datetime as _dt
import io
import json
import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - exercised by test_no_yaml_dependency
    yaml = None  # type: ignore

# Local synonym dictionary, see symptom_synonyms.py (N89 / O5).
from symptom_synonyms import expand_query, get_all_categories  # noqa: E402

# s38 (TD-365): register this module under the top-level name `sync_ai_memory`
# in every context (script run, `scripts.bootstrap` package import, `bootstrap`
# package import, sys.path-hack test import). `ai_memory_sync.collect` resolves
# `_main` by that name, so no second module object is ever loaded and no
# partial-init cycle can occur.
sys.modules.setdefault("sync_ai_memory", sys.modules[__name__])


REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
AI_MEMORY = REPO_ROOT_DEFAULT / ".ai-memory"
LESSONS_DIR = AI_MEMORY / "lessons"
SYNC_STATE = AI_MEMORY / "sync-state.json"
TOP_LEVEL_FILES = [
    # v9.7 (2026-07-26 TD-341): 4 个用户可读 ref 文件迁出到 docs/reference/, ref/ 仅留 3 个 AI 内部文件
    "ref/session-context.md",
    "ref/spec-index.md",
    "ref/doc-health-report-schema.md",
    # spec-38 Phase 4: 4 个 auto-generated KB 已迁到 meta/auto-kb/
    "meta/auto-kb/api-endpoints.md",
    "meta/auto-kb/agent-protocol.md",
    "meta/auto-kb/pipeline-nodes.md",
    "meta/auto-kb/error-codes.md",
    "meta/ai-operating-handbook.md",
]

VALID_MODES = {"auto", "derived-manual", "manual"}
REQUIRED_FIELDS = {"maintainer", "symptom", "solution", "related_files", "created_by"}

# Front matter regex: --- on its own line opens and closes the block.
# We accept trailing whitespace, but the closing `---` must be at line start.
_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(?P<yaml>.*?)\n---\s*(?:\n|$)",
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Hook-context detection (v8.4 N105 fix)
# ---------------------------------------------------------------------------


def is_hook_context() -> bool:
    """Return True if the script is being executed inside a pre-commit hook.

    The pre-commit framework exports `PRE_COMMIT=1` for every hook
    invocation (see https://pre-commit.com/#pre-commit-environment-variables).
    We treat the presence of that variable as a strong signal that any
    writes performed by this script would race with the user's staged
    changes — and would in fact be silently dropped because the
    framework re-stages the working tree after each hook passes.

    Callers can override detection by setting `GAF_ALLOW_HOOK_WRITES=1`
    in the environment; this is intended for maintenance scripts that
    need to refresh auto-maintained files on demand.
    """
    if os.environ.get("GAF_ALLOW_HOOK_WRITES") == "1":
        return False
    return os.environ.get("PRE_COMMIT", "") == "1"


# ---------------------------------------------------------------------------
# Front matter parsing
# ---------------------------------------------------------------------------


class FrontMatterError(ValueError):
    """Raised when YAML front matter is missing, malformed, or incomplete."""


def parse_front_matter(text: str) -> Tuple[Dict[str, object], str, bool]:
    """Parse YAML front matter from the head of a markdown document.

    Returns (front_matter_dict, body_text, had_front_matter).

    The returned dict preserves whatever fields the file declared;
    no field is required at this layer (validation lives in
    `validate_front_matter()`). Special characters in YAML values
    (colons, hashes, curly braces) are handled natively by PyYAML's
    block-scalar and quoted-string support.

    If `yaml` (PyYAML) is not importable, a `FrontMatterError` is raised
    with a clear remediation hint.
    """
    if yaml is None:
        raise FrontMatterError("PyYAML is not installed. Run: " "conda run -n gaf pip install pyyaml")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text, False
    raw_yaml = match.group("yaml")
    try:
        data = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:  # type: ignore[attr-defined]
        raise FrontMatterError(f"Invalid YAML in front matter: {exc}") from exc
    if not isinstance(data, dict):
        raise FrontMatterError(f"Front matter must be a YAML mapping, got {type(data).__name__}")
    body = text[match.end() :]
    return data, body, True


def validate_front_matter(data: Dict[str, object], *, strict: bool = True) -> List[str]:
    """Validate that a front-matter dict has the required fields.

    Returns a list of human-readable error messages; empty list means OK.
    When `strict=False`, missing fields produce a single warning instead
    of one error per field.
    """
    errors: List[str] = []
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"missing required field: {field!r}")
    maintainer = data.get("maintainer")
    if maintainer is not None and maintainer not in VALID_MODES:
        errors.append(f"invalid maintainer: {maintainer!r} (must be one of {sorted(VALID_MODES)})")
    if not strict and len(errors) == len(REQUIRED_FIELDS):
        # In non-strict mode, treat a fully-missing front matter as one warning.
        return ["front matter missing all required fields"]
    return errors


# ---------------------------------------------------------------------------
# Maintainer-mode dispatch
# ---------------------------------------------------------------------------


def _strip_yaml_block(text: str) -> str:
    """Return the body of the markdown file (front matter removed)."""
    _, body, _ = parse_front_matter(text)
    return body


def _autogenerate_body(data: Dict[str, object]) -> str:
    """Generate a placeholder body for an `auto` mode file.

    Real cross-language source parsing (Python AST, JS regex, Vue
    `<script>` extraction, etc.) is implemented in M1.B. For M0.B
    we emit a deterministic skeleton derived from the file's
    declared `source:` path and `symptom:` field. The skeleton
    carries a `<!-- source: ... -->` hint so M1.B can re-emit
    accurate content without re-reading the file.
    """
    source = str(data.get("source", "<unknown>"))
    symptom = data.get("symptom", [])
    if isinstance(symptom, str):
        symptom = [symptom]
    solution = str(data.get("solution", "")).strip()
    related = data.get("related_files", []) or []
    if isinstance(related, str):
        related = [related]
    today = _dt.date.today().isoformat()
    body = textwrap.dedent(
        f"""\
        # Auto-generated knowledge entry

        <!-- source: {source} -->
        <!-- generated: {today} -->

        ## Symptom

        {", ".join(str(s) for s in symptom) or "(none declared)"}

        ## Solution

        {solution or "(no solution declared)"}

        ## Related files

        {chr(10).join(f"- `{p}`" for p in related) or "- (none declared)"}

        <!-- end of auto-generated section -->
        """
    )
    return body


def _derived_manual_hint(data: Dict[str, object]) -> str:
    """Print a one-line hint for derived-manual files (no rewrite)."""
    title = str(data.get("symptom", "this file"))
    return (
        f"[derived-manual] Skipping auto-rewrite for {title}. "
        f"AI should review the source and append a '## Manual notes' "
        f"section when relevant."
    )


def handle_file(
    path: Path,
    *,
    dry_run: bool = False,
    hook_mode: Optional[bool] = None,
) -> Tuple[str, str]:
    """Process a single .ai-memory file according to its maintainer mode.

    Returns (action, message) where action is one of:
    - "skipped": file untouched (manual or derived-manual)
    - "regenerated": body replaced with auto-generated content
    - "read-only": auto-mode file inspected but NOT written (hook context)
    - "warning": file parsed but had problems

    The `hook_mode` flag, when set, overrides the auto-detection in
    `is_hook_context()`. Pass `True` to force read-only behaviour (e.g.
    from the `gaf-git-status-check` hook), `False` to force write mode,
    or `None` to use the env-based detection.

    Lessons (anything under `lessons/`) are treated as `manual` by
    default — they document specific incidents and should never be
    auto-rewritten, even if their front matter omits the
    `maintainer:` field (which is allowed for lessons, see
    Appendix E §E.4).
    """
    text = path.read_text(encoding="utf-8")
    try:
        data, body, had_fm = parse_front_matter(text)
    except FrontMatterError as exc:
        return "warning", f"{path.name}: {exc}"
    if not had_fm:
        return "warning", f"{path.name}: no front matter"
    errors = validate_front_matter(data, strict=False)
    mode = data.get("maintainer")
    is_lesson = "lessons" in path.parts
    is_summary = "summaries" in path.parts
    if (is_lesson or is_summary) and mode is None:
        return "skipped", f"{path.name}: lesson/summary (implicit manual)"
    if mode == "manual" or ((is_lesson or is_summary) and mode is None):
        return "skipped", f"{path.name}: manual mode"
    if mode == "derived-manual":
        return "skipped", _derived_manual_hint(data)
    if mode == "auto":
        # v8.4 N105 fix: in pre-commit hook context, NEVER rewrite
        # auto-maintained files. The framework re-stages the working
        # tree after each hook, so any write we do here would be
        # silently discarded (and would clobber the 96-line
        # docs-index.md that sync_docs_index.py just emitted).
        effective_hook_mode = hook_mode if hook_mode is not None else is_hook_context()
        if effective_hook_mode and not dry_run:
            return (
                "read-only",
                f"{path.name}: auto-mode in hook context — "
                f"skipped write to avoid clobbering "
                f"(run `python scripts/bootstrap/sync_ai_memory.py` outside "
                f"of a hook to refresh).",
            )
        new_body = _autogenerate_body(data)
        # M1.C: check whether source files are newer than this .ai-memory entry;
        # if so, tag the regenerated body with [CONFLICT] markers
        conflicts = _check_source_conflict(path, data, new_body)
        if conflicts:
            new_body = _mark_conflict(new_body, conflicts)
        if dry_run:
            if conflicts:
                return (
                    "conflict",
                    f"{path.name}: dry-run (auto) — would mark "
                    f"[CONFLICT] for {len(conflicts)} source file(s)",
                )
            return "regenerated", f"{path.name}: dry-run (auto) — would regenerate"
        new_text = _rebuild_text(data, new_body, text)
        path.write_text(new_text, encoding="utf-8")
        if conflicts:
            return (
                "conflict",
                f"{path.name}: auto-regenerated with [CONFLICT] "
                f"({len(conflicts)} source file(s) newer than {path.name})",
            )
        return "regenerated", f"{path.name}: auto-regenerated"
    return "warning", f"{path.name}: unknown maintainer={mode!r} (errors: {errors})"


def _rebuild_text(data: Dict[str, object], body: str, original: str) -> str:
    """Re-emit a markdown file with its front matter and a new body.

    Uses yaml.dump() to preserve the original field order and to
    round-trip unicode / special characters safely.
    """
    if yaml is None:  # pragma: no cover - parse_front_matter enforces
        raise FrontMatterError("PyYAML not installed")
    buf = io.StringIO()
    yaml.safe_dump(
        data,
        buf,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=4096,
    )
    yaml_text = buf.getvalue().rstrip("\n")
    body = body if body.endswith("\n") else body + "\n"
    return f"---\n{yaml_text}\n---\n\n{body}"


# ---------------------------------------------------------------------------
# M1.C: auto mode CONFLICT marking
# ---------------------------------------------------------------------------


# Match `<!-- source: ... -->` HTML comment to extract the source path
_SOURCE_HINT_RE = re.compile(r"<!--\s*source:\s*(\S+)\s*-->")


def _extract_source_hint(body: str) -> Optional[str]:
    """Extract the source path from a `<!-- source: ... -->` comment.

    Returns:
        Source path string (may contain glob wildcards, e.g.
        `agent/src/engine/nodes/*.py`); returns None if not found.
    """
    m = _SOURCE_HINT_RE.search(body)
    return m.group(1) if m else None


def _resolve_source_files(repo_root: Path, source_pattern: str) -> List[Path]:
    """Resolve a source pattern into a concrete list of file paths.

    - If `source_pattern` contains glob characters (`*`, `?`, `[`), expand via glob.
    - Otherwise, treat it as a direct file path.
    - Paths are resolved relative to `repo_root` (the GAF repository root).
    """
    # Path contains glob characters
    if any(c in source_pattern for c in "*?["):
        matches = sorted(repo_root.glob(source_pattern))
    else:
        # Direct file path
        direct = repo_root / source_pattern
        if direct.is_file():
            matches = [direct]
        else:
            matches = []
    return [m for m in matches if m.is_file()]


def _check_source_conflict(
    memory_path: Path, data: Dict[str, object], body: str
) -> List[Path]:
    """Check whether any source file is newer than the .ai-memory entry.

    1. Extract the `<!-- source: ... -->` path from `body`.
    2. Resolve it to concrete files (supports glob patterns).
    3. Compare mtime: source mtime > memory mtime => conflict.
    4. If body has no source hint but front matter has a `source` field, fall back to that.

    Returns:
        List of conflicting source files, sorted by mtime descending (newest first).
    """
    source_pattern = _extract_source_hint(body)
    if not source_pattern:
        # Fallback: use the `source` field from the front matter
        source_pattern = str(data.get("source", "")).strip()
    if not source_pattern:
        return []

    # memory_path is .ai-memory/foo.md; repo_root is the GAF repo root.
    # memory_path may be absolute or relative to repo_root.
    repo_root = REPO_ROOT_DEFAULT
    source_files = _resolve_source_files(repo_root, source_pattern)
    if not source_files:
        return []

    try:
        memory_mtime = memory_path.stat().st_mtime
    except OSError:
        return []

    conflicts: List[Tuple[float, Path]] = []
    for src in source_files:
        try:
            src_mtime = src.stat().st_mtime
        except OSError:
            continue
        if src_mtime > memory_mtime:
            conflicts.append((src_mtime, src))

    # Sort by mtime descending (newest conflict first)
    conflicts.sort(key=lambda x: x[0], reverse=True)
    return [path for _, path in conflicts]


def _mark_conflict(body: str, conflicts: List[Path]) -> str:
    """Insert a [CONFLICT] warning block at the top of `body`.

    The block is placed right after the `<!-- source: ... -->` comment
    so the AI sees the warning immediately when reading the file.
    """
    if not conflicts:
        return body
    # Use paths relative to the GAF repository root
    conflict_lines = []
    for src in conflicts[:5]:  # Show at most 5 entries
        try:
            rel = src.relative_to(REPO_ROOT_DEFAULT)
            conflict_lines.append(f"- `{rel}`")
        except ValueError:
            conflict_lines.append(f"- `{src}`")
    if len(conflicts) > 5:
        conflict_lines.append(f"- ... ({len(conflicts) - 5} more)")

    conflict_block = (
        "\n<!-- [CONFLICT] source file has been modified; "
        "this entry needs review and regeneration -->\n"
        f"<!-- [CONFLICT] {len(conflicts)} source file(s) newer than .ai-memory entry: -->\n"
        + "\n".join(conflict_lines)
        + "\n<!-- [CONFLICT] END -->\n"
    )

    # Insert immediately after the `<!-- source: ... -->` comment
    m = _SOURCE_HINT_RE.search(body)
    if m:
        insert_pos = m.end()
        return body[:insert_pos] + conflict_block + body[insert_pos:]
    # No source hint found => prepend the block to the body
    return conflict_block + body


# ---------------------------------------------------------------------------
# Query / index / stats
# ---------------------------------------------------------------------------


def _iter_markdown_files(root: Path) -> Iterable[Path]:
    """Yield all .md files under root/.ai-memory/ recursively."""
    if not root.exists():
        return
    for path in sorted(root.rglob("*.md")):
        if path.is_file():
            yield path



# C1 治本机制 (2026-07-16): fuzzy 优先 + embedding 补位 (混合检索)
# 触发条件: fuzzy 0 命中 + query 是自然语言 (非 N## / 非英文关键词)
# chromadb 不可用时降级为 warning + 返回空 (不 crash)
import re as _re_c1
import hashlib as _hashlib_c1
import datetime as _dt_c1

PERSIST_DIR_C1 = REPO_ROOT_DEFAULT / ".cache" / "chroma_memory"
COLLECTION_NAME_C1 = "gaf_memory"


def _is_natural_language(query: str) -> bool:
    """Heuristic: return True if query is natural language (not N## / not English keyword).

    Natural language = contains CJK characters OR ≥ 4 words with spaces.
    """
    # N## pattern
    if _re_c1.match(r"^N\d+$", query.strip()):
        return False
    # Contains CJK
    if any("\u4e00" <= ch <= "\u9fff" for ch in query):
        return True
    # ≥ 4 words (English sentence)
    words = query.split()
    if len(words) >= 4:
        return True
    return False


def _load_chroma_collection():
    """Load ChromaDB collection for gaf_memory. Returns collection or None."""
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
    except ImportError:
        return None
    if not PERSIST_DIR_C1.exists():
        return None
    try:
        client = chromadb.PersistentClient(
            path=str(PERSIST_DIR_C1),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        # Reuse FastembedMultilingualEF from backend/gaf_ai/rag.py
        ef = None
        try:
            import sys as _sys
            _backend = str(REPO_ROOT_DEFAULT / "backend")
            if _backend not in _sys.path:
                _sys.path.insert(0, _backend)
            from gaf_ai.rag import FastembedMultilingualEF  # type: ignore
            ef = FastembedMultilingualEF()
        except Exception:
            pass  # chromadb will use default EF (English-only)
        collection = client.get_or_create_collection(
            name=COLLECTION_NAME_C1,
            metadata={"hnsw:space": "cosine"},
            embedding_function=ef,
        )
        return collection
    except Exception:
        return None


def query_semantic(query: str, top_k: int = 5) -> List[Dict[str, object]]:
    """C1 治本机制: semantic search via ChromaDB (fallback when fuzzy returns 0).

    Returns list of matches with: path, score, matched_keywords, symptom, source.
    Returns empty list if chromadb unavailable or collection empty.
    """
    collection = _load_chroma_collection()
    if collection is None:
        print("⚠️  [C1] chromadb 不可用或索引未建, 降级为 fuzzy (跑: python scripts/bootstrap/build_memory_index.py)")
        return []
    try:
        count = collection.count()
        if count == 0:
            print("⚠️  [C1] gaf_memory collection 为空, 跑: python scripts/bootstrap/build_memory_index.py")
            return []
        results = collection.query(query_texts=[query], n_results=top_k)
        matches: List[Dict[str, object]] = []
        if results.get("documents") and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                distance = results["distances"][0][i] if results.get("distances") else 0
                filepath = meta.get("filepath", "")
                path = REPO_ROOT_DEFAULT / filepath if filepath else REPO_ROOT_DEFAULT
                source = meta.get("source", "semantic")
                section = meta.get("section", "")
                matches.append({
                    "path": path,
                    "score": max(0, 1 - distance),  # cosine distance → similarity
                    "matched_keywords": [query[:30]],
                    "symptom": [section or filepath] if section or filepath else [query[:30]],
                    "source": f"semantic-{source}",
                })
        return matches
    except Exception as e:
        print(f"⚠️  [C1] semantic query failed: {e}")
        return []


def print_query_results(query: str, results: List[Dict[str, object]]) -> None:
    """Render query results in a human-readable format."""
    print(f"找到 {len(results)} 条匹配：")
    for m in results:
        rel = m["path"]
        source = m.get("source", "lessons")
        print(f"  - {rel.name}  [{source}]")
        print(f"    symptom: {', '.join(m['symptom'])}")
        print(f"    matched: {', '.join(m['matched_keywords'])}")


# ---------------------------------------------------------------------------
# Sync state
# ---------------------------------------------------------------------------


# v8.4 M1.G: cross-platform file lock for concurrent sync runs.
# Lazy import: `sync_lock` is independent and only needed when we
# actually write state. The bare `import` would couple module load
# order between the two scripts.
def _acquire_state_lock(timeout: float = 5.0):
    """Return a context manager that locks `.ai-memory/.sync.lock`.

    Wraps `sync_lock.acquire_repo_lock` so call-sites stay one-line.
    Falls back to a no-op context manager if `sync_lock` cannot be
    imported (e.g. running this script in isolation for tests).
    """
    try:
        from sync_lock import acquire_repo_lock  # type: ignore
    except ImportError:
        @contextlib.contextmanager
        def _noop():
            yield None
        return _noop()
    return acquire_repo_lock(timeout=timeout)


def update_sync_state(root: Path, summary: Dict[str, int]) -> None:
    """Append a sync-state.json entry recording what just happened.

    This is the "evidence" of the sync run. `bypass_weekly_review.py`
    and other meta tools read this file to compute skip rates, lesson
    counts, and other metrics (see Appendix A §A.5).

    v8.4 M1.G: takes a cross-platform file lock (`.ai-memory/.sync.lock`)
    for the duration of the read-modify-write cycle so two concurrent
    sync runs cannot interleave their `change_history` appends.
    """
    # Lock first — even the existence check + write must be atomic.
    with _acquire_state_lock(timeout=5.0):
        AI_MEMORY.mkdir(parents=True, exist_ok=True)
        # v8.4 N106 fix: use module-level SYNC_STATE constant when root matches
        # the default repo root, to keep the path as a single source of truth
        # matching spec.md §5. For non-default roots (e.g. tests, --root flag),
        # keep the explicit inline path so we never write outside the target dir.
        if root == REPO_ROOT_DEFAULT:
            state_path = SYNC_STATE  # single source of truth (N106)
        else:
            state_path = root / ".ai-memory" / "sync-state.json"  # explicit for non-default roots
        state: Dict[str, object] = {
            "last_run": _dt.datetime.now().isoformat(timespec="seconds"),
            "summary": summary,
            "categories_known": len(get_all_categories()),
        }
        if state_path.exists():
            try:
                existing = json.loads(state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}
            history = existing.get("change_history", [])
            if not isinstance(history, list):
                history = []
            history.append(state)
            state = {
                "last_run": state["last_run"],
                "summary": state["summary"],
                "categories_known": state["categories_known"],
                "change_history": history[-30:],  # keep last 30 entries
            }
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# TD-332/TD-344: mtime-based incremental cache (spec-2026-07-26-governance-batch-perf-cache)
#
# When sync_ai_memory runs in hook context, 60-80% of its 4-8s runtime is
# wasted IO: handle_file() reads every .ai-memory/*.md file and parses its
# YAML front matter, only to discover that most files are `manual`/`derived-manual`
# mode and get skipped. If no .md file has changed since the last successful
# sync, the output is guaranteed identical → we can skip the full scan entirely.
#
# Cache strategy: store {relative_path: st_mtime_ns} manifest in
# `.ai-memory/.sync-cache.json`. On next run, rebuild manifest and compare.
# If equal → cache hit (skip main loop + counter-sync, print "cache hit").
# If any file changed → cache miss (run full sync, refresh cache).
#


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------




def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="GAF .ai-memory knowledge base synchronizer (v8.3.1)",
    )
    parser.add_argument(
        "--no-counters-sync",
        action="store_true",
        help="Skip syncing lessons/README count, yn-matrices auto_updated, project_rules archived count",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT_DEFAULT),
        help="Path to the GAF repo root (default: %(default)s)",
    )
    parser.add_argument(
        "--query",
        metavar="KEYWORD",
        help="Fuzzy-search lessons/ by symptom keyword",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing files",
    )
    parser.add_argument(
        "--index",
        action="store_true",
        help="Print a summary of all .ai-memory/ files",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print per-maintainer-mode counts",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    ai_memory = root / ".ai-memory"
    if not ai_memory.exists():
        print(f"❌ {ai_memory} does not exist; run bootstrap first.", file=sys.stderr)
        return 1

    if args.query:
        # B3 治本机制 (2026-07-16): query 4 sources (lessons + failure-modes + yn-matrices + summaries)
        results = query_all_sources(args.query, ai_memory)
        # C1 治本机制 (2026-07-16): fuzzy 优先 + embedding 补位 (混合检索)
        # 触发条件: fuzzy 0 命中 (过滤后) + query 是自然语言 (非 N## / 非英文关键词)
        # 改进 1 (2026-07-16): natural language queries require ≥ 1 exact token
        # match to suppress spurious CJK substring noise (any 2-char Chinese phrase
        # matches many description tokens). Short keyword / N## queries keep
        # lenient substring matching (any score ≥ 1).
        is_nl = _is_natural_language(args.query)
        if is_nl:
            # 改进 1 (2026-07-16): CJK substring matching is too loose (any 2-char
            # phrase matches many description tokens). Require at least one STRONG
            # match = a token that exactly equals (case-insensitive) a RAW English
            # keyword (≥ 3 chars) from the query. We deliberately exclude single
            # CJK chars from the strong-match set because:
            #   (a) `expand_query` synonym-expands them to dozens of unrelated
            #       lesson phrases ("报" → "n105"/"hook"/"pre-commit"), and
            #   (b) some failure-modes description tokens ARE single CJK chars
            #       ("时"/"前"/...), producing spurious exact matches.
            # Pure-CJK semantic queries therefore fall through to C1 embedding,
            # which is the intended behavior (embedding handles CJK semantics
            # far better than char-level fuzzy matching).
            raw_kws: set[str] = {
                w.lower()
                for w in _re_c1.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", args.query)
            }
            filtered = []
            for r in results:
                mks = {str(k).lower() for k in r.get("matched_keywords", [])}
                if mks & raw_kws:
                    filtered.append(r)
            if len(filtered) < len(results):
                print(
                    f"# fuzzy {len(results)} 命中, 自然语言 query 要求 ≥ 1 精确英文 token 匹配, "
                    f"过滤后 {len(filtered)} 命中"
                )
            results = filtered
        if not results and is_nl:
            print(f"# fuzzy 0 命中 (过滤后), query 是自然语言 → C1 embedding 补位")
            results = query_semantic(args.query, top_k=5)
        if not results:
            print(f"未找到与 {args.query!r} 匹配的 lessons。")
            return 0
        print_query_results(args.query, results)
        return 0

    summary: Dict[str, int] = {"regenerated": 0, "skipped": 0, "warning": 0, "read-only": 0, "conflict": 0}

    # TD-332/TD-344 (spec-2026-07-26-governance-batch-perf-cache): mtime-based
    # incremental cache. If no .ai-memory/*.md file changed since the last
    # successful sync, skip the full scan entirely (handle_file() results
    # and counter-sync outputs would be identical).
    #
    # Conditions for cache check:
    #   - not --dry-run (dry-run must not read/write cache)
    #   - not --no-counters-sync (caller explicitly wants counter-sync to run,
    #     so skip cache short-circuit to preserve counter-sync behavior)
    #   - not --index/--stats (those flags want per-file detail, cache hit
    #     would skip the per-file loop and produce empty output)
    use_cache = (
        not args.dry_run
        and not args.no_counters_sync
        and not args.index
        and not args.stats
    )
    if use_cache and _check_cache_valid(root):
        summary["skipped"] = 1  # placeholder: "cache hit"
        update_sync_state(root, summary)
        print(
            f"✅ sync_ai_memory: cache hit (0 files changed since last sync), "
            f"skipped full scan"
        )
        return 0

    for path in _iter_markdown_files(ai_memory):
        action, message = handle_file(path, dry_run=args.dry_run)
        summary[action] = summary.get(action, 0) + 1
        if args.index or args.stats:
            print(f"  [{action}] {message}")

    if args.stats:
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    if not args.dry_run:
        update_sync_state(root, summary)

    # TD-159/164/171 — auto-sync counters (lessons count, yn-matrices auto_updated, archived count)
    if not args.no_counters_sync:
        counters_changed = []
        if _sync_lessons_readme_count(root, dry_run=args.dry_run):
            counters_changed.append("lessons/README.md:lessons_count")
        if _sync_rules_counters(root, dry_run=args.dry_run):
            counters_changed.append("lessons/README.md: active/retired/next_n_id (TD-392)")
        if _sync_yn_matrices_auto_updated(root, dry_run=args.dry_run):
            counters_changed.append("yn-matrices.md:auto_updated")
        if _sync_archived_count_in_rules(root, dry_run=args.dry_run):
            counters_changed.append("project_rules.md:archived_count")
        if counters_changed and (args.index or args.stats):
            print(f"  [counter-sync] {', '.join(counters_changed)}")

    # v8.4 N105: in hook context, make the read-only state visible so
    # the operator knows the auto-maintained files were intentionally
    # not refreshed (and can re-run the script outside the hook to do
    # so).
    if is_hook_context() and summary.get("read-only", 0) > 0:
        print(
            f"ℹ️  sync_ai_memory: hook context detected — {summary['read-only']} "
            f"auto-maintained file(s) intentionally NOT rewritten. "
            f"Run `python scripts/bootstrap/sync_ai_memory.py` outside the hook to "
            f"refresh them.",
            file=sys.stderr,
        )

    # TD-332/TD-344: refresh cache after a successful full sync so the
    # next run can hit cache. Only write when we actually performed the
    # full scan (not dry-run, not cache-hit short-circuit above).
    if use_cache:
        _write_cache(root, _build_mtime_manifest(root))

    print(
        f"✅ sync_ai_memory: regenerated={summary['regenerated']} "
        f"skipped={summary['skipped']} "
        f"read-only={summary.get('read-only', 0)} "
        f"conflict={summary.get('conflict', 0)} "
        f"warning={summary['warning']}"
    )
    return 0


# ---------------------------------------------------------------------------
# s38 (TD-365): domain module re-exports.
# Both import paths work: package context (scripts/ on sys.path) and the
# sys.path-hack context used by scripts/tests (scripts/bootstrap/ on path).
# ---------------------------------------------------------------------------

try:
    from bootstrap.ai_memory_sync import collect, counters, mtime_cache
except ImportError:  # pragma: no cover - sys.path hack context (scripts/bootstrap/ only)
    from ai_memory_sync import collect, counters, mtime_cache

collect_lessons = collect.collect_lessons
_symptom_tokens = collect._symptom_tokens
query_lessons = collect.query_lessons
_scan_failure_modes_index = collect._scan_failure_modes_index
_scan_yn_matrices = collect._scan_yn_matrices
_scan_summaries = collect._scan_summaries
query_all_sources = collect.query_all_sources
_cache_path = mtime_cache._cache_path
_build_mtime_manifest = mtime_cache._build_mtime_manifest
_load_cache = mtime_cache._load_cache
_write_cache = mtime_cache._write_cache
_check_cache_valid = mtime_cache._check_cache_valid
_sync_lessons_readme_count = counters._sync_lessons_readme_count
_sync_rules_counters = counters._sync_rules_counters
_sync_yn_matrices_auto_updated = counters._sync_yn_matrices_auto_updated
_sync_archived_count_in_rules = counters._sync_archived_count_in_rules


if __name__ == "__main__":
    sys.exit(main())

