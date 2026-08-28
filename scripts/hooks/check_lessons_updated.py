# ruff: noqa: I001
"""check_lessons_updated.py — v8.3.1 lesson front-matter validator.

Enforces the lesson contract (see spec.md §3.2 + Appendix E §E.4 +
.ai-memory/README.md §1.1 three-mode差异化必填字段, TD-282 2026-07-20):

  Maintainer-mode-aware required fields (TD-282):
    - auto:           maintainer, source, generated, auto_updated (4)
    - derived-manual: maintainer, source, load_when, priority, symptom,
                      solution, related_files, auto_updated,
                      last_manual_edit (9)
    - manual:         maintainer, source, load_when, priority, symptom,
                      solution, related_files, created_by (8)
    - <unspecified>:  legacy 5-field contract (date, symptom, solution,
                      related_files, created_by) — backward compat for
                      lessons/*.md files that have not yet declared
                      `maintainer`. README §0.1 says lessons default to
                      `manual`, but strict 8-field enforcement would
                      block 50+ legacy lesson commits; the migration
                      is deferred (warn-only) until files are touched.

  Also enforces the AI-extension contract (N91 / O2):
    - When `maintainer: derived-manual` and a new N## entry is added
      to `failure-modes.md`, the new section must include `added_by`
      and `added_at` fields, and its title must use the same N##
      number as its top-level heading.

  Other validations:
    - `date` matches the filename prefix when present
    - `related_files` items are paths that exist (warning, not error)
    - symptom is not the empty list

Usage:
    python check_lessons_updated.py
    python check_lessons_updated.py --root <repo>
    python check_lessons_updated.py --no-fail

Exit codes:
    0 — OK
    1 — Missing or invalid front matter
    2 — Configuration error
"""
from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path
_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import _encoding_safe  # noqa: E402,F401  (must be first; reconfigures stdout to UTF-8)

import argparse  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

from frontmatter import parse_front_matter  # noqa: E402

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
LESSONS_DEFAULT = REPO_ROOT_DEFAULT / ".ai-memory" / "lessons"
FAILURE_MODES = REPO_ROOT_DEFAULT / ".ai-memory" / "meta" / "failure-modes.md"

# Legacy 5-field contract (used when `maintainer` is not declared; see
# module docstring for the backward-compat rationale).
LEGACY_REQUIRED_FIELDS = (
    "date",
    "symptom",
    "solution",
    "related_files",
    "created_by",
)

# TD-282 — maintainer-mode-aware required field sets.
# Source of truth: .ai-memory/README.md §1.1 (2026-07-19 spec-39 Phase 7).
MODE_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "auto": (
        "maintainer",
        "source",
        "generated",
        "auto_updated",
    ),
    "derived-manual": (
        "maintainer",
        "source",
        "load_when",
        "priority",
        "symptom",
        "solution",
        "related_files",
        "auto_updated",
        "last_manual_edit",
    ),
    "manual": (
        "maintainer",
        "source",
        "load_when",
        "priority",
        "symptom",
        "solution",
        "related_files",
        "created_by",
    ),
}
VALID_MAINTAINER_MODES = tuple(MODE_REQUIRED_FIELDS.keys())

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
# spec-13 Phase 2 [A]-R2-1: support BOTH heading format (legacy) and table format (v9.0+).
# failure-modes.md uses `| N## | topic | hard constraint | lesson link |` table rows in
# the Active N## index table. The legacy `### N##:` heading regex is kept as a fallback
# for backward compatibility (e.g. archived-lessons.md may still use headings).
N_HEADING_RE = re.compile(r"^###\s+(N\d+):\s*(.+)$", re.MULTILINE)
# Table row pattern: `| N91 | ... | ... | `lessons/xxx.md` |`
# Captures N## id (group 1) and the lesson link path (group 2, may be empty).
N_TABLE_ROW_RE = re.compile(
    r"^\|\s*(N\d{2,4}(?:/\s*N\d{2,4})*)\s*\|\s*[^|]+\|\s*[^|]+\|\s*`?([^|\s`]+\.md)?`?\s*\|",
    re.MULTILINE,
)
# Lesson link path inside the table cell (for file existence check).
# Exclude template placeholders like `<n##>` or `<topic>_<date>-...` (spec-13 Phase 2).
LESSON_LINK_RE = re.compile(r"`lessons/([^`<>]+\.md)`")


def _is_valid_date(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", value))


def _check_one_lesson(path: Path, repo_root: Path) -> list[str]:
    issues: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"❌ {path}: cannot read ({exc})"]
    data, _body, had_fm = parse_front_matter(text)
    if not had_fm:
        return [f"❌ {path}: missing front matter (need --- ... ---)"]

    # TD-282 — pick the required-field set based on `maintainer` mode.
    # Unspecified `maintainer` falls back to the legacy 5-field contract
    # so existing lessons/*.md files (which predate the 3-mode spec) are
    # not suddenly blocked. Files that DO declare `maintainer` are held
    # to the strict README §1.1 contract for their mode.
    maintainer = data.get("maintainer")
    if maintainer is None:
        required_fields = LEGACY_REQUIRED_FIELDS
    elif maintainer in MODE_REQUIRED_FIELDS:
        required_fields = MODE_REQUIRED_FIELDS[maintainer]
    else:
        issues.append(
            f"❌ {path.name}: invalid maintainer {maintainer!r} "
            f"(must be one of {VALID_MAINTAINER_MODES})"
        )
        required_fields = LEGACY_REQUIRED_FIELDS

    for field in required_fields:
        if field not in data or data[field] in ("", []):
            issues.append(f"❌ {path.name}: missing required field: {field!r}")
    if "date" in data and not _is_valid_date(data["date"]):
        issues.append(
            f"❌ {path.name}: invalid date {data['date']!r} (need YYYY-MM-DD)"
        )
    if "date" in data:
        m = DATE_RE.match(path.name)
        if m and m.group(1) != data["date"]:
            issues.append(
                f"❌ {path.name}: filename date {m.group(1)} != front matter date {data['date']}"
            )
    if "symptom" in data:
        symptom = data["symptom"]
        if isinstance(symptom, list) and not symptom:
            issues.append(f"❌ {path.name}: symptom list is empty")
        elif not symptom:
            issues.append(f"❌ {path.name}: symptom is empty")
    if "created_by" in data and data["created_by"] not in ("AI", "user"):
        issues.append(
            f"❌ {path.name}: created_by must be 'AI' or 'user' (got {data['created_by']!r})"
        )
    if "related_files" in data:
        related = data["related_files"]
        if isinstance(related, list):
            search_roots = (repo_root, repo_root.parent)
            for rel in related:
                if not isinstance(rel, str) or not rel:
                    issues.append(
                        f"❌ {path.name}: related_files contains empty / non-string entry"
                    )
                    continue
                # Warn-only: the file might be planned but not yet present.
                # Look in both the GAF repo root and its parent (workspace
                # root), because some specs live in `<workspace>/.skills/`.
                if not any((base / rel).exists() for base in search_roots):
                    issues.append(
                        f"⚠️  {path.name}: related_files entry does not exist "
                        f"(checked {repo_root} and {repo_root.parent}): {rel}"
                    )
    # M3 (2026-08-15): diff_keywords 触发式检索字段.
    # TD-378 (2026-08-20) 强制: 字段必在 frontmatter (可空 list, 但缺失 = ❌ 阻塞),
    # 使 M3 diff→lesson 检索对全部 lesson 生效. 存量 2026-08-20 已批量回填.
    if "diff_keywords" not in data:
        issues.append(
            f"❌ {path.name}: missing required field: 'diff_keywords' (TD-378, "
            f"M3 检索字段 — 可空 list 但字段必在; 参考已有: [\"frontend-sync\", \"cross-layer-sync\"])"
        )
    elif "diff_keywords" in data:
        kws = data["diff_keywords"]
        if not isinstance(kws, list) or not kws:
            issues.append(
                f"⚠️  {path.name}: diff_keywords 必须是非空 list (如 [\"sql-injection\", \"cursor-execute\"])"
            )
        else:
            for kw in kws:
                if not isinstance(kw, str) or not kw.strip():
                    issues.append(
                        f"⚠️  {path.name}: diff_keywords 含空项 (每项必须是非空字符串)"
                    )
                    break
    return issues


def _check_failure_modes(path: Path) -> list[str]:
    r"""Validate failure-modes.md N## index consistency.

    spec-13 Phase 2 [A]-R2-1: support BOTH heading format (legacy) and table
    format (v9.0+). failure-modes.md Active N## index table uses table rows
    like `| N91 | topic | hard constraint | \`lessons/xxx.md\` |`.

    Checks performed:
    1. Extract all N## tokens from BOTH `### N##:` headings AND `| N## |` table rows.
    2. Duplicate N## detection (same N## appears 2+ times).
    3. Lesson link path existence check (for table rows with `lessons/xxx.md`).

    Note: The legacy added_by/added_at contract (N91/O2) is no longer enforced
    because the v9.0 table format does not include these fields. The contract
    is now optional and enforced at lesson file front-matter level instead.
    """
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    issues: list[str] = []

    # Extract N## from legacy headings (### N##:)
    heading_matches = list(N_HEADING_RE.finditer(text))
    # Extract N## from table rows (| N## | ... | ... | ... |)
    table_matches = list(N_TABLE_ROW_RE.finditer(text))

    # Combine all N## tokens (split combined forms like "N124/N125/N126")
    all_n_ids: list[str] = []
    for m in heading_matches:
        all_n_ids.append(m.group(1))
    for m in table_matches:
        # group(1) may contain "N124/N125/N126" — split on /
        raw = m.group(1)
        for piece in re.split(r"[/,]", raw):
            piece = piece.strip()
            if piece:
                all_n_ids.append(piece)

    # Duplicate N## detection
    seen: dict[str, int] = {}
    for n_id in all_n_ids:
        seen[n_id] = seen.get(n_id, 0) + 1
    for n_id, count in seen.items():
        if count > 1:
            issues.append(
                f"❌ {path.name}: duplicate N## {n_id} ({count} times)"
            )

    # Lesson link existence check (table rows only)
    # Extract all `lessons/xxx.md` paths from the entire text and verify
    # the files exist. This catches stale lesson links.
    repo_root = path.parents[2]  # .ai-memory/meta/failure-modes.md -> repo root
    lessons_dir = repo_root / ".ai-memory" / "lessons"
    for m in LESSON_LINK_RE.finditer(text):
        lesson_rel = m.group(1)
        lesson_path = lessons_dir / lesson_rel
        if not lesson_path.exists():
            issues.append(
                f"❌ {path.name}: lesson link points to missing file: "
                f"lessons/{lesson_rel}"
            )

    return issues


def check_repo(
    root: Path, lessons_dir: Path | None = None
) -> tuple[int, list[str]]:
    lessons = lessons_dir or (root / ".ai-memory" / "lessons")
    if not lessons.exists():
        return 2, [f"❌ lessons dir missing: {lessons}"]
    issues: list[str] = []
    info: list[str] = []
    # TD-173 — recursively scan lessons/ + subdirs (e.g. archived-early/).
    # Skip README.md (index file, not a lesson).
    files = sorted(p for p in lessons.rglob("*.md") if p.name != "README.md")
    if not files:
        info.append(f"ℹ️  no lessons found in {lessons}")
    for f in files:
        issues.extend(_check_one_lesson(f, root))
    # Also validate summaries/ (architecture-mistakes / code-rules / library-conflicts)
    summaries = root / ".ai-memory" / "summaries"
    if summaries.exists():
        for f in sorted(summaries.glob("*.md")):
            issues.extend(_check_one_lesson(f, root))
    issues.extend(_check_failure_modes(root / ".ai-memory" / "meta" / "failure-modes.md"))
    if issues:
        return 1, issues + info
    return 0, info or [f"✅ {len(files)} lessons validated"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="GAF lesson front-matter validator (v8.3.1)",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT_DEFAULT),
        help="Path to the GAF repo root (default: %(default)s)",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Print report but never exit non-zero.",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    code, messages = check_repo(root)
    for m in messages:
        print(m)
    if args.no_fail:
        return 0
    return code


if __name__ == "__main__":
    sys.exit(main())
