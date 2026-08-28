"""check_doc_code_sync.py - TD-325 (spec-87) 代码-文档因果绑定 pre-commit hook.

在 ``git commit`` 时检测代码变更是否需要同步更新文档, 分级阻断:
- 硬阻断 (R1/R2/R4): urls.py / models.py 字段 / 模块重命名删除
  → exit 1 (除非 commit message 含 [skip-doc-sync])
- 警告 (R3/R5/R7): 新增 app / 前端 api 客户端 / settings
  → exit 0 (N167 反思阶段强制确认)
- 信息 (R6): 新增 spec 文件 → sync_spec_index 自动同步
  → exit 0

工作流
-------
1. ``git diff --name-status --cached`` 拿 staged 文件 + status letter
2. 对每个文件按 ``doc_sync_rules.RULES`` 匹配规则
3. 路径+内容规则 (R1/R2/R5/R7): ``git diff --cached -U0 <file>`` 扫描关键字
4. 命中关键字 → 双重验证 ``required_docs`` 同步状态:
   - 条件 1: 文档在本次 staged 列表中
   - 条件 2: 文档最近 commit 在 1 小时内
   任一满足即 PASS
5. 状态信号规则 (R3/R4/R6): 不扫内容, 直接按 severity 输出

性能预算
--------
- 普通 commit (0 规则命中): ~15ms
- 命中 1 条规则: ~35ms (路径命中 → 内容快扫 → 双重验证)
- 最坏 (7 规则全命中): ~100ms
- 对 governance batch 总耗时增量 < 5%

跳过机制
--------
- commit message 含 ``[skip-doc-sync]`` → 跳过所有硬阻断 (仍打印 WARN)
- 跳过记录写入 ``.cache/doc_sync_skips.json``, N167 反思阶段强制确认

Usage
-----
    # 注册在 gaf_governance_batch.py CHECKS 第 12 项:
    ("hooks.check_doc_code_sync", "main", [], "doc-code sync")

    # 手动运行:
    python scripts/hooks/check_doc_code_sync.py
    python scripts/hooks/check_doc_code_sync.py --no-fail   # warn only
    python scripts/hooks/check_doc_code_sync.py --root <p>  # 不同 repo

Exit codes
----------
    0 - 通过 (无硬阻断, 或所有硬阻断被 [skip-doc-sync] 跳过)
    1 - 至少 1 条硬阻断规则触发
    2 - 配置错误 (非 git repo 等)
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
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

from hooks.doc_sync_rules import RULES, DocSyncRule, match_rules  # noqa: E402

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
SKIP_RECORD_FILE = REPO_ROOT_DEFAULT / ".cache" / "doc_sync_skips.json"
SKIP_TOKEN = "[skip-doc-sync]"
DOC_SYNC_WINDOW_SECONDS = 3600  # 1 小时


# ---------- git helpers ----------


def _run_git(args: list[str], repo_root: Path) -> tuple[int, str]:
    """Run a git command, return (returncode, stdout text)."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, result.stdout


def _get_staged_files(repo_root: Path) -> list[tuple[str, str]]:
    """Return [(status_letter, filepath), ...] for staged files.

    Uses ``git diff --name-status --cached`` which yields lines like:
        M\tpath/to/file.py
        A\tpath/to/new.py
        R100\told.py\tnew.py
        D\tpath/to/deleted.py

    For rename (R), we return the new path (column 3) with status 'R'.
    """
    code, out = _run_git(["diff", "--name-status", "--cached"], repo_root)
    if code != 0:
        return []
    files: list[tuple[str, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        # Line format: "STATUS\tpath" or "R100\toldpath\tnewpath"
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        status_letter = status[0].upper()
        if status_letter == "R" and len(parts) >= 3:
            # rename: report new path
            files.append((status_letter, parts[2]))
        else:
            files.append((status_letter, parts[1]))
    return files


def _scan_diff_content(filepath: str, keywords: tuple[str, ...], repo_root: Path) -> bool:
    """Return True if staged diff of ``filepath`` contains any keyword.

    Uses ``git diff --cached -U0 <file>`` (no context lines) to minimize output.
    Only scans added lines (starting with ``+`` but not ``+++``).
    Comment-only changes (lines starting with ``+#``) are skipped to avoid
    false positives on trivial docstring/comment edits.
    """
    if not keywords:
        return True  # 状态信号规则不扫内容
    code, out = _run_git(["diff", "--cached", "-U0", "--", filepath], repo_root)
    if code != 0:
        return False
    for line in out.splitlines():
        # Only added lines (skip +++ header)
        if not line.startswith("+") or line.startswith("+++"):
            continue
        # Skip pure comment additions (Python #, JS/TS //, /* */)
        stripped = line[1:].lstrip()
        if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
            continue
        for kw in keywords:
            if kw in line:
                return True
    return False


def _get_doc_last_commit_timestamp(doc_path: str, repo_root: Path) -> float | None:
    """Return Unix timestamp of last commit touching ``doc_path``, or None."""
    code, out = _run_git(["log", "-1", "--format=%ct", "--", doc_path], repo_root)
    if code != 0 or not out.strip():
        return None
    try:
        return float(out.strip())
    except ValueError:
        return None


def _verify_doc_synced(
    doc_path: str,
    staged_filepaths: list[str],
    repo_root: Path,
) -> bool:
    """双重验证文档是否已同步更新.

    条件 1 (staged 检查): doc_path 在本次 commit 的 staged 文件列表中
    条件 2 (最近 commit): doc_path 最近一次 commit在 1 小时内
    任一条件满足即 PASS.
    """
    # 条件 1: staged 检查
    if doc_path in staged_filepaths:
        return True
    # 条件 2: 最近 commit 时间检查 (1 小时窗口)
    last_ts = _get_doc_last_commit_timestamp(doc_path, repo_root)
    if last_ts is None:
        return False
    now_ts = time.time()
    return (now_ts - last_ts) < DOC_SYNC_WINDOW_SECONDS


# ---------- skip token ----------


def _read_commit_message(repo_root: Path) -> str:
    """Read the in-progress commit message.

    pre-commit framework (pre-commit stage) does NOT receive the commit
    message file as an argument. We read ``.git/COMMIT_EDITMSG`` which
    git populates before opening the editor. If that fails, fall back to
    the last commit message (helps when running manually post-commit).

    Also supports ``GAF_SKIP_DOC_SYNC=1`` environment variable as an
    alternative to ``[skip-doc-sync]`` token, for cases where git commit
    -m/-F does not populate COMMIT_EDITMSG before the hook runs (e.g.
    PowerShell on Windows).
    """
    # Environment variable override (P2 归档 commit 场景)
    import os
    if os.environ.get("GAF_SKIP_DOC_SYNC") == "1":
        return SKIP_TOKEN  # 模拟 commit message 含 [skip-doc-sync]

    editmsg = repo_root / ".git" / "COMMIT_EDITMSG"
    if editmsg.is_file():
        try:
            return editmsg.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    # Fallback: last commit message
    code, out = _run_git(["log", "-1", "--pretty=%B"], repo_root)
    if code == 0:
        return out
    return ""


def _check_skip_token(repo_root: Path) -> bool:
    """True if commit message contains [skip-doc-sync]."""
    msg = _read_commit_message(repo_root)
    return SKIP_TOKEN in msg


def _write_skip_record(
    triggered_rules: list[DocSyncRule],
    repo_root: Path,
) -> None:
    """Append a skip record to ``.cache/doc_sync_skips.json``.

    Record format:
        {
          "timestamp": "2026-07-22T12:34:56Z",
          "commit": "<short hash or empty>",
          "rules": ["R1", "R4"],
          "files": ["backend/accounts/urls.py", ...]
        }
    """
    SKIP_RECORD_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Best-effort: get current commit hash (may be empty pre-commit)
    code, hash_out = _run_git(["rev-parse", "HEAD"], repo_root)
    commit_hash = hash_out.strip()[:12] if code == 0 else ""
    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "commit": commit_hash,
        "rules": [r.id for r in triggered_rules],
    }
    # Append to existing records (keep last 50)
    records: list[dict] = []
    if SKIP_RECORD_FILE.is_file():
        try:
            records = json.loads(SKIP_RECORD_FILE.read_text(encoding="utf-8"))
            if not isinstance(records, list):
                records = []
        except (json.JSONDecodeError, OSError):
            records = []
    records.append(record)
    records = records[-50:]
    try:
        SKIP_RECORD_FILE.write_text(
            json.dumps(records, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass  # best-effort, do not block commit


# ---------- main logic ----------


def _format_hard_fail(rule: DocSyncRule, filepath: str) -> list[str]:
    """Format HARD FAIL output lines for a rule violation."""
    lines = [
        f"[check_doc_code_sync] ⛔ HARD FAIL ({rule.id}): {filepath} 变更",
        f"  规则: {rule.description}",
    ]
    if rule.required_docs:
        for doc in rule.required_docs:
            lines.append(f"  → 请同步更新 {doc}")
    else:
        lines.append("  → 请确认全仓库引用已同步")
    lines.extend([
        f"  → 或在 commit message 加 {SKIP_TOKEN} 跳过",
        f"  → 跳过将记录到 .cache/doc_sync_skips.json, N167 反思阶段强制确认",
    ])
    return lines


def _format_warn(rule: DocSyncRule, filepath: str) -> list[str]:
    """Format WARN output lines."""
    lines = [
        f"[check_doc_code_sync] ⚠️ WARN ({rule.id}): {filepath} 变更",
        f"  规则: {rule.description}",
    ]
    if rule.required_docs:
        for doc in rule.required_docs:
            lines.append(f"  → 请在 N167 反思阶段确认 {doc} 是否需更新")
    else:
        lines.append("  → 请在 N167 反思阶段确认是否需补文档")
    return lines


def _format_info(rule: DocSyncRule, filepath: str) -> list[str]:
    """Format INFO output lines."""
    return [
        f"[check_doc_code_sync] ℹ️ INFO ({rule.id}): {filepath}",
        f"  规则: {rule.description}",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="GAF 代码-文档因果绑定 pre-commit hook (TD-325 / spec-87)",
    )
    parser.add_argument("--root", default=str(REPO_ROOT_DEFAULT), help="repo root (default: %(default)s)")
    parser.add_argument("--no-fail", action="store_true", help="warn only, always exit 0")
    parser.add_argument("--check", action="store_true", help="check mode (alias, same as default)")
    args = parser.parse_args(argv)

    repo_root = Path(args.root).resolve()
    if not (repo_root / ".git").exists():
        print(f"[check_doc_code_sync] ERROR: {repo_root} is not a git repo", file=sys.stderr)
        return 2

    staged = _get_staged_files(repo_root)
    if not staged:
        print("[check_doc_code_sync] no staged files, skip")
        return 0

    staged_filepaths = [fp for _, fp in staged]
    skip_active = _check_skip_token(repo_root)

    if skip_active:
        print(f"[check_doc_code_sync] {SKIP_TOKEN} detected in commit message — 硬阻断降级为 WARN")

    hard_fails: list[tuple[DocSyncRule, str]] = []
    warns: list[tuple[DocSyncRule, str]] = []
    infos: list[tuple[DocSyncRule, str]] = []
    skipped_hard: list[tuple[DocSyncRule, str]] = []

    for status, filepath in staged:
        rules = match_rules(filepath, status)
        for rule in rules:
            # R8 特殊处理: docs/**/*.md modified → 验证 doc_last_updated 字段同步更新 (spec §9.3 扩展点 3)
            if rule.id == "R8":
                # status_filter="M" 已由 match_rules 过滤, 这里只处理 modified
                # 扫描 staged diff 是否包含 +doc_last_updated: 行
                doc_last_updated_synced = _scan_diff_content(
                    filepath, ("doc_last_updated:",), repo_root
                )
                if doc_last_updated_synced:
                    # 用户更新了 doc_last_updated 字段, PASS
                    continue
                # 未更新 → 触发 hard fail (或降级 warn)
                if skip_active:
                    skipped_hard.append((rule, filepath))
                else:
                    hard_fails.append((rule, filepath))
                continue

            # 状态信号规则 (content_keywords 为空): 直接按 severity 输出
            if not rule.content_keywords:
                # R4 归档白名单: docs/specs/archived/ + docs/plans/archived/ + .ai-memory/evidence/archived/ 下的文件
                # 归档操作 (git mv 到 archived/) 是合理的生命周期管理, 不属于"模块重命名/删除"语义
                if rule.id == "R4" and any(
                    frag in filepath for frag in (
                        "docs/specs/archived/",
                        "docs/plans/archived/",
                        ".ai-memory/evidence/archived/",
                        "docs/archive/spec-context/",  # 承载体归档
                        ".ai-memory/meta/yn-matrices/archived-yn-matrices/",  # Y/N 矩阵归档 (spec-2026-07-26-ai-governance-execution-rate-fix Wave 2)
                        ".ai-memory/_archive/",  # lessons 退役归档 (TD-374)
                        ".skills/_archive/",  # skill 移出归档 (TD-375)
                        "scripts/_archive/",  # hook/脚本归档 (TD-379)
                    )
                ):
                    continue  # 归档路径跳过 R4
                if rule.severity == "hard":
                    if skip_active:
                        skipped_hard.append((rule, filepath))
                    else:
                        hard_fails.append((rule, filepath))
                elif rule.severity == "warn":
                    warns.append((rule, filepath))
                else:
                    infos.append((rule, filepath))
                continue

            # 路径+内容规则: 扫描 diff 内容
            content_hit = _scan_diff_content(filepath, rule.content_keywords, repo_root)
            if not content_hit:
                continue  # 路径命中但内容无关键字 (例如只改注释) → 跳过

            # 内容命中 → 双重验证 required_docs
            if not rule.required_docs:
                # 无 required_docs (理论上不会到这里, 但防御性处理)
                if rule.severity == "hard":
                    if skip_active:
                        skipped_hard.append((rule, filepath))
                    else:
                        hard_fails.append((rule, filepath))
                elif rule.severity == "warn":
                    warns.append((rule, filepath))
                else:
                    infos.append((rule, filepath))
                continue

            # 双重验证: 任一文档已同步即 PASS
            doc_synced = any(
                _verify_doc_synced(doc, staged_filepaths, repo_root)
                for doc in rule.required_docs
            )
            if doc_synced:
                continue  # 文档已同步, PASS

            # 文档未同步 → 触发
            if rule.severity == "hard":
                if skip_active:
                    skipped_hard.append((rule, filepath))
                else:
                    hard_fails.append((rule, filepath))
            elif rule.severity == "warn":
                warns.append((rule, filepath))
            else:
                infos.append((rule, filepath))

    # 输出
    for rule, filepath in infos:
        for line in _format_info(rule, filepath):
            print(line)

    for rule, filepath in warns:
        for line in _format_warn(rule, filepath):
            print(line)

    for rule, filepath in skipped_hard:
        print(f"[check_doc_code_sync] ⚠️ HARD→WARN ({rule.id}): {filepath} (skipped via {SKIP_TOKEN})")
        for line in _format_warn(rule, filepath)[2:]:
            print(line)

    for rule, filepath in hard_fails:
        for line in _format_hard_fail(rule, filepath):
            print(line)

    # 写 skip record (如果有跳过的硬阻断)
    if skipped_hard:
        _write_skip_record([r for r, _ in skipped_hard], repo_root)

    # 总结
    total_fail = len(hard_fails)
    total_warn = len(warns) + len(skipped_hard)
    total_info = len(infos)
    print(
        f"[check_doc_code_sync] summary: {total_fail} hard fail, "
        f"{total_warn} warn, {total_info} info"
    )

    if total_fail > 0 and not args.no_fail:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
