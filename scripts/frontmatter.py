"""frontmatter.py — tiny YAML-less front matter parser for GAF scripts.

Shared by sync_docs_index.py, check_lessons_updated.py and promote_lessons.py
so that front matter parsing is not re-implemented in every script.

The parser supports the subset of YAML used by GAF markdown files:

    ---
    key: value
    list_inline: [a, b, c]
    list_multiline:
      - item1
      - item2
    quoted: "value"
    ---

It intentionally does not depend on PyYAML, keeping pre-commit hooks fast.
"""
from __future__ import annotations

import re

# Matches a key:value line where the key is a valid Python identifier.
_KEY_VALUE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")
# Matches a list item line ("  - item").
_LIST_ITEM_RE = re.compile(r"^\s*-\s*(.*)$")


def parse_front_matter(text: str) -> tuple[dict[str, object], str, bool]:
    """Parse a minimal YAML front matter block at the top of ``text``.

    Returns ``(data, body, had_front_matter)``.

    - ``data`` is the parsed front matter mapping.
    - ``body`` is the markdown body after the closing ``---`` line.
    - ``had_front_matter`` is ``True`` when a well-formed block was found.

    Values may be strings, inline lists (``[a, b]``), or multi-line lists
    (indented ``- item`` lines). Unrecognised values are returned as strings.
    """
    if not text.startswith("---"):
        return {}, text, False

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text, False

    end: int | None = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break

    if end is None:
        return {}, text, False

    block_lines = lines[1:end]
    data: dict[str, object] = {}
    i = 0
    while i < len(block_lines):
        line = block_lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        match = _KEY_VALUE_RE.match(line)
        if not match:
            i += 1
            continue

        key, value = match.group(1), match.group(2).strip()

        # Inline list: [a, b, c]
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1]
            data[key] = [
                item.strip().strip("'\"")
                for item in inner.split(",")
                if item.strip()
            ]
            i += 1
            continue

        # Quoted string
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            data[key] = value[1:-1]
            i += 1
            continue

        # Multi-line list: indented - item lines
        if value == "":
            items: list[str] = []
            j = i + 1
            while j < len(block_lines):
                next_line = block_lines[j]
                if not next_line.strip().startswith("-"):
                    break
                item_match = _LIST_ITEM_RE.match(next_line)
                if not item_match:
                    break
                items.append(item_match.group(1).strip().strip("'\""))
                j += 1
            if items:
                data[key] = items
                i = j
                continue
            data[key] = ""
            i += 1
            continue

        # Plain string
        data[key] = value
        i += 1

    body = "\n".join(lines[end + 1 :])
    return data, body, True
