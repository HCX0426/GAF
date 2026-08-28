"""match_lessons_by_diff.py — M3 (2026-08-15) diff→lesson 触发式检索.

测试 SFCAPI 语言借鉴的第三机制: 让教训在"下一次踩坑"时自动出现,
而不是只靠 AI 主动查. 每次 commit 时把 staged diff (路径 + 新增行)
与 lessons front-matter 的 diff_keywords 匹配, 输出相关教训清单.

匹配来源 (按权重):
    diff_keywords 字段直接命中          +3
    related_files 路径子串命中          +2
    diff 新增行 token 命中 topic/主题词  +1 (未启用, 见 FAQ)

Usage:
    python scripts/lessons/match_lessons_by_diff.py               # staged diff vs HEAD
    python scripts/lessons/match_lessons_by_diff.py <path>...     # 指定文件
    python scripts/lessons/match_lessons_by_diff.py --base HEAD~3 # 指定范围
    python scripts/lessons/match_lessons_by_diff.py --json        # JSON 输出
    python scripts/lessons/match_lessons_by_diff.py --top 8       # 显示条数

Exit codes:
    0 — 正常 (无论有无匹配; hook 用途只提示不阻断)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# N105 hook infra fix (2026-08-16): GBK console crashes on emoji/ℹ️ output
# (UnicodeEncodeError in post-commit). Force UTF-8 so the hook is locale-safe.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

REPO_ROOT = Path(__file__).resolve().parents[2]
LESSONS_DIR = REPO_ROOT / ".ai-memory" / "lessons"

MAX_DIFF_BYTES = 200_000  # 防止超大 diff 卡顿


def _parse_front_matter(text: str) -> dict:
    """极简 front-matter 解析 (--- 之间的 YAML 键: 值 / 行内 [a, b] / 缩进 - 列表)."""
    data: dict = {}
    if not text.startswith("---\n"):
        return data
    end = text.find("\n---\n", 4)
    if end == -1:
        return data
    raw = text[4:end]
    current_key: str | None = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        if re.match(r"^[A-Za-z_]+:", line):
            key, _, val = line.partition(":")
            current_key = key.strip()
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                items = [i.strip() for i in val[1:-1].split(",") if i.strip()]
                data[current_key] = items
            else:
                data[current_key] = val
        elif line.startswith("  - ") and current_key:
            item = line.strip()[2:].strip()
            if not isinstance(data.get(current_key), list):
                data[current_key] = []
            data[current_key].append(item)
    return data


def load_lessons(lessons_dir: Path) -> list[dict]:
    """读所有课程 front-matter, 仅保留含 diff_keywords 的."""
    lessons: list[dict] = []
    for p in sorted(lessons_dir.rglob("*.md")):
        if p.name == "README.md":
            continue
        try:
            data = _parse_front_matter(p.read_text(encoding="utf-8"))
        except OSError:
            continue
        kws = data.get("diff_keywords")
        if not kws:
            continue
        if isinstance(kws, str):
            kws = [kws]
        rel = p.relative_to(lessons_dir).as_posix()
        lessons.append(
            {
                "path": rel,
                "diff_keywords": [k.lower() for k in kws if isinstance(k, str) and k.strip()],
                "related_files": [
                    str(f).lower() for f in data.get("related_files", [])
                    if isinstance(f, str) and f.strip()
                ],
            }
        )
    return lessons


def _git(*args: str, cwd: Path) -> str:
    try:
        r = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        return r.stdout if r.returncode == 0 else ""
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return ""


def collect_diff(paths: list[str] | None, base: str, head: str | None) -> tuple[list[str], set[str], list[str]]:
    """收集改动文件路径 + 新增行 token 集 + 新增行原文.

    head 为空时用 `git diff --cached` (staged vs HEAD, pre-commit 场景);
    给了 head 用 `git diff base..head`; 给了文件列表用 status --porcelain 判定.
    """
    changed_paths: list[str] = []
    if paths:
        for p in paths:
            status = _git("status", "--porcelain", "--", p, cwd=REPO_ROOT).strip()
            if status:
                changed_paths.append(p.replace("\\", "/").lower())
    elif head:
        for line in _git("diff", f"{base}..{head}", "--name-only", cwd=REPO_ROOT).splitlines():
            if line.strip():
                changed_paths.append(line.strip().lower())
    else:
        for line in _git("diff", "--cached", "--name-only", cwd=REPO_ROOT).splitlines():
            if line.strip():
                changed_paths.append(line.strip().lower())

    if not changed_paths:
        return changed_paths, set(), []

    # 新增行: 用 -U0 只拿 hunk, 过滤 + 开头的行 (排除 +++ 头)
    if head:
        diff_text = _git(
            "diff", f"{base}..{head}", "-U0", "--", *changed_paths, cwd=REPO_ROOT,
        )[:MAX_DIFF_BYTES]
    else:
        diff_text = _git(
            "diff", "--cached", "-U0", "--", *changed_paths, cwd=REPO_ROOT,
        )[:MAX_DIFF_BYTES]
    added_lines: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++") and line[1:].strip():
            added_lines.append(line[1:])
    tokens: set[str] = set()
    for line in added_lines:
        for tok in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{1,}", line):
            tokens.add(tok.lower())
    return changed_paths, tokens, added_lines


def score_lessons(
    lessons: list[dict], changed_paths: list[str], tokens: set[str], added_lines: list[str]
) -> list[dict]:
    scored: list[dict] = []
    for lesson in lessons:
        kw_hits: list[str] = []
        file_hits: list[str] = []
        score = 0
        for kw in lesson["diff_keywords"]:
            # 关键词命中: 路径子串, 新增行 token, 或新增行原文子串 (支持复合词)
            if (
                any(kw in p for p in changed_paths)
                or kw in tokens
                or any(kw in line for line in added_lines)
            ):
                kw_hits.append(kw)
                score += 3
        for rf in lesson["related_files"]:
            stem = Path(rf).name
            if any(stem in p or rf in p for p in changed_paths):
                file_hits.append(stem)
                score += 2
        if score > 0:
            scored.append(
                {
                    "path": lesson["path"],
                    "score": score,
                    "keywords": kw_hits,
                    "files": file_hits,
                }
            )
    scored.sort(key=lambda x: (-x["score"], x["path"]))
    return scored


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="M3: 按 staged diff 触发式检索相关 lessons (diff_keywords 匹配)",
    )
    parser.add_argument("paths", nargs="*", help="指定文件 (默认: staged 全部改动)")
    parser.add_argument("--base", default="HEAD", help="diff 起点 (默认 HEAD)")
    parser.add_argument("--head", default=None, help="diff 终点 (默认空 = staged vs HEAD)")
    parser.add_argument("--top", type=int, default=5, help="最多显示条数 (默认 5)")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args(argv)

    lessons = load_lessons(LESSONS_DIR)
    changed_paths, tokens, added_lines = collect_diff(args.paths or None, args.base, args.head)

    if not changed_paths:
        print("ℹ️  no changed files (or empty diff) — no lesson matches")
        return 0

    scored = score_lessons(lessons, changed_paths, tokens, added_lines)
    if args.json:
        print(json.dumps(
            {
                "changed_files": len(changed_paths),
                "lessons_with_keywords": len(lessons),
                "matches": scored[: args.top],
            },
            ensure_ascii=False, indent=2,
        ))
        return 0

    if not scored:
        print(f"ℹ️  改动 {len(changed_paths)} 个文件, 无 diff_keywords 命中的 lesson")
        return 0

    print(f"# M3 相关教训 (diff 命中 {len(scored)} 条, 显示前 {min(args.top, len(scored))})")
    for m in scored[: args.top]:
        detail = []
        if m["keywords"]:
            detail.append(f"kw={','.join(m['keywords'])}")
        if m["files"]:
            detail.append(f"files={','.join(m['files'])}")
        print(f"  [{m['score']:>2}] {m['path']} ({'; '.join(detail)})")
    print()
    print("# 按上面 N## 去 .ai-memory/lessons/<path> 读全文再动手")
    return 0


if __name__ == "__main__":
    sys.exit(main())
