"""check_yn_matrices_index.py - Y/N matrix index vs sub-file consistency checker.

Validates that ``.ai-memory/meta/yn-matrices.md`` (the slice index) stays in
sync with the actual ``### N###`` / ``### §X.Y`` headings inside each sub-file
under ``.ai-memory/meta/yn-matrices/``.

Background
----------
R10 of the 2026-07-15 governance audit found 5 drifts where the index table
claimed a sub-file covered fewer N## than it actually did (e.g. index said
``testing`` covers ``N118, N119, N142, N143, N147`` but the sub-file also had
``N156``). Such drift is invisible to ``git status`` and was only caught by
manual audit. This hook blocks future drift at commit time.

What it checks
--------------
For each row in the index table (lines starting with ``| <topic> |``):
  1. Extracts the claimed N## / §X.Y tokens from column 3.
  2. Reads the corresponding ``_<topic>.md`` sub-file.
  3. Extracts actual ``### N###`` and ``### §X.Y`` headings.
  4. Diffs the two sets. Missing entries → exit 1.

Usage
-----
    python scripts/hooks/check_yn_matrices_index.py            # scan default repo
    python scripts/hooks/check_yn_matrices_index.py --root <repo>
    python scripts/hooks/check_yn_matrices_index.py --no-fail  # warn-only

Exit codes
----------
    0 - index and sub-files agree
    1 - drift detected (missing entries in index)
    2 - configuration / argument error
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_DEFAULT = Path(__file__).resolve().parents[2]

INDEX_FILE_REL = ".ai-memory/meta/yn-matrices.md"
SUBDIR_REL = ".ai-memory/meta/yn-matrices"

# Index row pattern: | <topic> | [§N](sub-file.md) | N##, N##, §X.Y | desc |
# Column 3 is the "包含 N##" column.
INDEX_ROW_RE = re.compile(
    r"^\|\s*([^|]+?)\s*\|\s*\[§\d+\]\([^)]+\)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|"
)

# Heading patterns inside sub-files.
# Matches "### ⑨ N109 ..." / "### N91 ..." / "### ㉙ N156 ..." / "### §4.6 ..."
# N## allows 2-4 digits (N91, N109, N151, N160 all exist).
# Circled digits range: ①-⑳ (U+2460-U+2473, 1-20) + ㉑-㉟ (U+3251-U+325F, 21-35) + ㊱-㊿ (U+32B1-U+32BF, 36-50).
# spec-15 fix (2026-07-17): extended from ㉑-㉛ to ㉑-㊿ to cover ㉝/㉞/㉟/㊱ used in _workflow.md.
HEADING_N_RE = re.compile(r"^###\s+(?:[①-⑳㉑-㊿]\s+)?(N\d{2,4}(?:[/,\s]+N\d{2,4})*)", re.MULTILINE)
HEADING_SECTION_RE = re.compile(r"^###\s+(?:[①-⑳㉑-㊿]\s+)?(§\d+(?:\.\d+)*)\b", re.MULTILINE)
# Some sub-files use combined forms like "N124/N125/N126" — split on / and comma.
TOKEN_SPLIT_RE = re.compile(r"[/,]")


def extract_index_claims(index_text: str) -> dict[str, tuple[set[str], set[str]]]:
    """Return {topic: (required_tokens, cross_ref_tokens)} from the index table.

    A token is either ``N##`` or ``§X.Y`` or ``§X.Y-§X.Z`` (range expanded
    to individual sections). Tokens marked ``(cross-ref)`` are separated into
    ``cross_ref_tokens`` and are NOT required to appear as ### headings in the
    sub-file (they are pointers to another topic's sub-file).
    """
    claims: dict[str, tuple[set[str], set[str]]] = {}
    for line in index_text.splitlines():
        match = INDEX_ROW_RE.match(line)
        if not match:
            continue
        topic = match.group(1).strip()
        token_cell = match.group(2).strip()
        required: set[str] = set()
        cross_refs: set[str] = set()
        # Split on commas first (top-level separator), then handle each piece.
        for piece in token_cell.split(","):
            piece = piece.strip()
            if not piece:
                continue
            is_cross_ref = "(cross-ref)" in piece
            # Strip parenthetical annotations.
            clean = piece.split("(")[0].strip()
            if not clean:
                continue
            # Split on "/" for combined forms like "N124/N125/N126".
            for raw in TOKEN_SPLIT_RE.split(clean):
                raw = raw.strip()
                if not raw:
                    continue
                # Handle range like "§4.6-§4.10".
                if raw.startswith("§") and "-" in raw:
                    parts = raw[1:].split("-")
                    if len(parts) == 2 and parts[0].count(".") == 1 and parts[1].count(".") == 1:
                        major = parts[0].split(".")[0]
                        try:
                            start = int(parts[0].split(".")[1])
                            end = int(parts[1].split(".")[1])
                        except ValueError:
                            target = cross_refs if is_cross_ref else required
                            target.add(raw)
                            continue
                        for i in range(start, end + 1):
                            target = cross_refs if is_cross_ref else required
                            target.add(f"§{major}.{i}")
                    else:
                        target = cross_refs if is_cross_ref else required
                        target.add(raw)
                else:
                    target = cross_refs if is_cross_ref else required
                    target.add(raw)
        claims[topic] = (required, cross_refs)
    return claims


def extract_subfile_headings(subfile_text: str) -> set[str]:
    """Return set of N## and §X.Y tokens from ### headings in a sub-file.

    Handles combined heading forms like ``### ⑳ N124/N125/N126 ...`` by
    splitting on ``/`` and ``,``.
    """
    tokens: set[str] = set()
    for match in HEADING_N_RE.finditer(subfile_text):
        raw = match.group(1)
        for piece in TOKEN_SPLIT_RE.split(raw):
            piece = piece.strip()
            if piece:
                tokens.add(piece)
    for match in HEADING_SECTION_RE.finditer(subfile_text):
        tokens.add(match.group(1))
    return tokens


def check_consistency(repo_root: Path) -> list[str]:
    """Return list of violation messages (empty = OK)."""
    index_path = repo_root / INDEX_FILE_REL
    subdir = repo_root / SUBDIR_REL
    if not index_path.is_file():
        return [f"Index file missing: {index_path}"]
    if not subdir.is_dir():
        return [f"Sub-file directory missing: {subdir}"]

    index_text = index_path.read_text(encoding="utf-8", errors="replace")
    claims = extract_index_claims(index_text)
    violations: list[str] = []

    # Wave 2 (2026-07-26, spec-2026-07-26-ai-governance-execution-rate-fix):
    # 6 sub-files moved to archived-yn-matrices/. Index table still references
    # them by topic name (e.g. "workflow-spec"); search active dir first, then
    # archived dir. N## reference relations are preserved (see yn-matrices.md
    # "Wave 2 精简" note).
    archived_subdir = subdir / "archived-yn-matrices"

    for topic, (required_tokens, _cross_ref_tokens) in claims.items():
        subfile_path = subdir / f"_{topic}.md"
        if not subfile_path.is_file():
            # Try archived dir (Wave 2 — 6 sub-files moved to archived-yn-matrices/)
            archived_path = archived_subdir / f"_{topic}.md"
            if archived_path.is_file():
                subfile_path = archived_path
            else:
                violations.append(f"Sub-file missing for topic '{topic}': {subfile_path}")
                continue
        subfile_text = subfile_path.read_text(encoding="utf-8", errors="replace")
        actual_tokens = extract_subfile_headings(subfile_text)

        # Tokens in sub-file but not in index = index drift (missing entries).
        # Skip §X.Y tokens (they may be project_rules section refs, not indexed).
        missing_from_index = {t for t in (actual_tokens - required_tokens) if t.startswith("N")}
        if missing_from_index:
            sorted_missing = sorted(missing_from_index)
            violations.append(
                f"Topic '{topic}': index missing {sorted_missing} "
                f"(present as ### headings in _{topic}.md but not in index table)"
            )

        # Required tokens in index but not in sub-file = stale index entry.
        # Cross-ref tokens are exempt (they point to another topic's sub-file).
        missing_from_subfile = required_tokens - actual_tokens
        stale_n = {t for t in missing_from_subfile if t.startswith("N")}
        if stale_n:
            sorted_stale = sorted(stale_n)
            violations.append(
                f"Topic '{topic}': index claims {sorted_stale} "
                f"but no matching ### heading in _{topic}.md"
            )

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO_DEFAULT), help="Repo root directory")
    parser.add_argument("--no-fail", action="store_true", help="Warn only, do not block commit")
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    if not repo_root.is_dir():
        print(f"[gaf-yn-matrices-index] ERROR: repo root not found: {repo_root}", file=sys.stderr)
        return 2

    violations = check_consistency(repo_root)
    if not violations:
        print("[gaf-yn-matrices-index] OK — index and sub-files agree")
        return 0

    print("[gaf-yn-matrices-index] Drift detected:", file=sys.stderr)
    for v in violations:
        print(f"  - {v}", file=sys.stderr)
    print(
        "\nFix: update .ai-memory/meta/yn-matrices.md index table to match "
        "the ### headings in the corresponding sub-file.",
        file=sys.stderr,
    )
    return 0 if args.no_fail else 1


if __name__ == "__main__":
    sys.exit(main())
