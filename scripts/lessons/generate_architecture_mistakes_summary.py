"""Generate a human-readable summary of architecture mistakes.

This script reads the AI-facing detailed lesson file at
`.ai-memory/summaries/architecture-mistakes.md` and writes a curated summary to
`docs/architecture/architecture-mistakes-summary.md`.

The summary preserves the target file's YAML frontmatter and replaces the body
with an auto-generated table of entries.
"""
from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path
_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import importlib.util
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

# Reuse the encoding helper without relying on package layout.
_ENCODING_SAFE = Path(__file__).with_name("_encoding_safe.py")
_spec = importlib.util.spec_from_file_location("_encoding_safe", _ENCODING_SAFE)
if _spec and _spec.loader:
    _enc = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_enc)

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_MEMORY = REPO_ROOT / ".ai-memory"
DOCS = REPO_ROOT / "docs" / "architecture"

SOURCE = AI_MEMORY / "summaries" / "architecture-mistakes.md"
TARGET = DOCS / "architecture-mistakes-summary.md"

SECTION_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
DATE_RE = re.compile(r"\(?\b(\d{4}-\d{2}-\d{2})\b\)?")


def parse_frontmatter(text: str) -> Tuple[str, str]:
    """Split YAML frontmatter from body."""
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            return text[: end + 3], text[end + 3 :].lstrip()
    return "", text


def extract_summary(section_text: str) -> str:
    """Return the first meaningful sentence/line after the section heading."""
    raw_lines = [line.rstrip() for line in section_text.splitlines()]
    lines = [line.strip() for line in raw_lines if line.strip()]
    # Skip heading line if still present.
    if lines and lines[0].startswith("##"):
        lines = lines[1:]

    problem_markers = ("**问题**", "**Problem**", "**Symptom**", "**症状**", "**Rule**", "**规则**", "**??**")

    def _normalize_marker_line(line: str) -> str:
        """Strip leading list markers so `- **Symptom**: ...` matches."""
        return re.sub(r"^[-•*]\s*", "", line.strip())

    def _is_marker(line: str) -> bool:
        normalized = _normalize_marker_line(line)
        return any(normalized.startswith(marker) for marker in problem_markers)

    def _extract_after_marker(line: str) -> str:
        """If the marker and its value share a line, return the value part."""
        normalized = _normalize_marker_line(line)
        for marker in problem_markers:
            if normalized.startswith(marker):
                remainder = normalized[len(marker) :].lstrip(": ").strip()
                cleaned = _clean_line(remainder)
                if cleaned and len(cleaned) > 10:
                    return cleaned
        return ""

    # Prefer the line immediately after a problem/symptom marker.
    for idx, line in enumerate(lines):
        if _is_marker(line):
            inline = _extract_after_marker(line)
            if inline:
                return inline
            for next_line in lines[idx + 1 :]:
                cleaned = _clean_line(next_line)
                if cleaned and len(cleaned) > 10:
                    return cleaned

    # Fallback: pick the first substantive line, skipping structural markers.
    for line in lines:
        if line in ("---", ">") or _is_marker(line):
            continue
        cleaned = _clean_line(line)
        if cleaned and len(cleaned) > 15:
            return cleaned
    return "(no summary)"


def _clean_line(line: str) -> str:
    """Remove markdown formatting and discard table-only/header rows."""
    stripped = line.strip()
    # Drop table separator / header rows.
    if stripped.startswith("|") and stripped.endswith("|"):
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not any(len(c) > 3 and not c.startswith("-") for c in cells):
            return ""
        # Drop table header/separator rows where cells contain no lowercase letters.
        content_cells = [c for c in cells if c and not c.startswith("-")]
        if content_cells and all(len(c) < 40 and not any(ch.islower() for ch in c) for c in content_cells):
            return ""
        stripped = " ".join(c for c in cells if c and not c.startswith("-"))
    # Remove markdown bold/italic/code markers.
    cleaned = re.sub(r"[*_>`]+", "", stripped).strip()
    # Drop leading list markers.
    cleaned = re.sub(r"^[-•*]\s*", "", cleaned).strip()
    return cleaned


def extract_entries(text: str) -> List[Tuple[str, str, str]]:
    """Return list of (heading, summary, date) for each `##` section."""
    matches = list(SECTION_RE.finditer(text))
    entries: List[Tuple[str, str, str]] = []
    for i, match in enumerate(matches):
        heading = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        summary = extract_summary(body)
        date_match = DATE_RE.search(heading)
        if not date_match:
            date_match = DATE_RE.search(body)
        date = date_match.group(1) if date_match else ""
        entries.append((heading, summary, date))
    return entries


def build_target_body(entries: List[Tuple[str, str, str]]) -> str:
    """Build the auto-generated markdown body."""
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: List[str] = [
        "# GAF Architecture Mistakes — Human Summary",
        "",
        "> **Auto-generated** from `.ai-memory/summaries/architecture-mistakes.md`.",
        f"> **Generated at**: {generated_at}.",
        "> Do not edit this file manually; run the generator script instead.",
        "",
        "This document is a high-level index of the architecture and design mistakes",
        "recorded in the AI lesson system. For full details, root-cause analysis, and",
        "prevention rules, read the source file linked above.",
        "",
        "| # | Date | Title | Summary |",
        "|---|------|-------|---------|",
    ]
    for idx, (heading, summary, date) in enumerate(entries, start=1):
        # Escape pipe characters in summary.
        safe_summary = summary.replace("|", "\\|")
        safe_heading = heading.replace("|", "\\|")
        lines.append(f"| {idx} | {date} | {safe_heading} | {safe_summary} |")

    lines.extend(
        [
            "",
            "---",
            "",
            "## Regeneration",
            "",
            "```bash",
            "python scripts/lessons/generate_architecture_mistakes_summary.py",
            "```",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    if not SOURCE.exists():
        print(f"❌ Source not found: {SOURCE}", file=sys.stderr)
        return 1

    source_text = SOURCE.read_text(encoding="utf-8")
    _, source_body = parse_frontmatter(source_text)
    entries = extract_entries(source_body)

    if not entries:
        print("⚠️ No architecture mistake entries found in source.", file=sys.stderr)
        return 1

    target_text = ""
    frontmatter = ""
    if TARGET.exists():
        target_text = TARGET.read_text(encoding="utf-8")
        frontmatter, _ = parse_frontmatter(target_text)

    if not frontmatter:
        frontmatter = "---\nsummary: GAF 架构教训累计记录\napplies_to: ['architecture', 'lessons', 'ai-lessons']\nlast_updated: 2026-06-20\n---\n"

    new_body = build_target_body(entries)
    new_content = frontmatter.rstrip() + "\n\n" + new_body

    DOCS.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(new_content, encoding="utf-8")
    print(f"✅ Wrote {len(entries)} entries to {TARGET.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
