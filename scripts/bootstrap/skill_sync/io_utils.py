"""skill_sync.io_utils — file/text helpers for sync_skills (s39 split, TD-365 6/9)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .constants import (
    _FRONTMATTER_RE,
    _FRONTMATTER_UPDATED_RE,
    DECISION_TREE_END,
    DECISION_TREE_START,
)


def _read_text(path: Path) -> str:
    """Read a UTF-8 file. Returns "" on error."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _file_hash(path: Path) -> str:
    """SHA-256 of file content (16-char prefix)."""
    return hashlib.sha256(_read_text(path).encode("utf-8")).hexdigest()[:16]


def _extract_decision_tree_block(content: str) -> str:
    """Extract the decision tree block (decision tree copies only)."""
    start = content.find(DECISION_TREE_START)
    if start < 0:
        return ""
    end = content.find(DECISION_TREE_END, start)
    if end < 0:
        return content[start:]
    return content[start : end + len(DECISION_TREE_END)]


def _block_hash(block: str) -> str:
    return hashlib.sha256(block.encode("utf-8")).hexdigest()[:16]


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _skill_minimal_scaffold(name: str) -> str:
    """Generate a minimal SKILL.md scaffold for a missing skill."""
    return (
        "---\n"
        f"name: {name}\n"
        "---\n\n"
        f"# {name}\n\n"
        "<!-- M0.L: 此 skill 由 sync_skills.py 同步生成 -->\n"
    )


def _rule_minimal_scaffold(filename: str) -> str:
    return f"# GAF Project Rules\n\n<!-- M0.L: scaffold for {filename} -->\n"

def parse_frontmatter_updated(text: str) -> str:
    """Parse the ``updated:`` field from SKILL.md frontmatter.

    Returns the date string (e.g. ``"2026-07-17"``) or ``""`` if frontmatter
    is missing or the field is absent.
    """
    fm_match = _FRONTMATTER_RE.match(text)
    if not fm_match:
        return ""
    fm_text = fm_match.group(1)
    m = _FRONTMATTER_UPDATED_RE.search(fm_text)
    return m.group(1) if m else ""


def update_frontmatter_updated(text: str, new_date: str) -> str:
    """Replace or insert the ``updated:`` field in SKILL.md frontmatter.

    - If frontmatter has ``updated:`` line → replace its value with ``new_date``.
    - If frontmatter exists but no ``updated:`` → insert before closing ``---``.
    - If no frontmatter → return text unchanged (caller should handle).

    Returns the modified text (or original text if no frontmatter).
    """
    fm_match = _FRONTMATTER_RE.match(text)
    if not fm_match:
        return text
    fm_text = fm_match.group(1)
    fm_start, fm_end = fm_match.span(1)
    if _FRONTMATTER_UPDATED_RE.search(fm_text):
        new_fm = _FRONTMATTER_UPDATED_RE.sub(f"updated: {new_date}", fm_text, count=1)
    else:
        # Insert `updated: <date>` before end of frontmatter.
        separator = "\n" if fm_text and not fm_text.endswith("\n") else ""
        new_fm = fm_text + separator + f"updated: {new_date}"
    return text[:fm_start] + new_fm + text[fm_end:]

