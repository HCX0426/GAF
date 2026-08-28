"""GAF 启动时跑一次的检查任务 (spec §4/§5).

IDE 开发模式下 GAF 不持续运行, Celery beat 定时任务不会触发.
改为 GAF 启动时 (启动脚本显式调用) 跑一次 cleanup + forgetting.

4 个清理函数 + run_startup_checks 入口:
- cleanup_old_archives_once: 删 30 天前 tar.gz (复用 gaf_core.tasks.cleanup_old_archives)
- cleanup_old_evidence_once: active > 30 天 → 移 archived/YYYY-MM/
- delete_archived_evidence_once: archived > 90 天 → 删除
- forgetting_check_once: 处理两类超时 N## (Active + Dormant)
- run_startup_checks: 启动脚本显式调用, 串行跑 4 个函数

通过 management command 调用:
    python manage.py run_startup_checks [--dry-run] [--all]

注意: 所有函数都是幂等的 (重复跑不会出错), 且支持 dry-run 模式.
"""
from __future__ import annotations

import logging
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

# spec §4.1 retention thresholds
EVIDENCE_ACTIVE_RETENTION_DAYS = 30  # active > 30 天 → 移 archived
EVIDENCE_ARCHIVED_RETENTION_DAYS = 90  # archived > 90 天 → 删除
FORGETTING_THRESHOLD_DAYS = 180  # 6 个月 → 遗忘机制

# evidence 目录路径 (绝对路径, 便于测试)
REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = REPO_ROOT / ".ai-memory" / "evidence"
ACTIVE_DIR = EVIDENCE_DIR / "active"
ARCHIVED_DIR = EVIDENCE_DIR / "archived"

# lessons 目录
LESSONS_DIR = REPO_ROOT / ".ai-memory" / "lessons"
FM_PATH = REPO_ROOT / ".ai-memory" / "meta" / "failure-modes.md"
ARCHIVED_LESSONS_PATH = REPO_ROOT / ".ai-memory" / "meta" / "archived-lessons.md"

# 目录名日期前缀正则 (evidence/YYYY-MM-DD-<slug>/)
DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[-_]")


def cleanup_old_archives_once(dry_run: bool = False) -> dict[str, Any]:
    """删 30 天前 tar.gz (复用 gaf_core.tasks.cleanup_old_archives).

    注意: 这是同步版本 (非 Celery task), 用于启动时调用.
    """
    from gaf_core.tasks import cleanup_old_archives

    logger.info("[startup_checks] cleanup_old_archives_once: dry_run=%s", dry_run)
    if dry_run:
        # dry-run: 只统计不删除
        archive_dir = getattr(settings, "DEBUG_ARCHIVE_DIR", None)
        if not archive_dir:
            return {"deleted_count": 0, "skipped": "DEBUG_ARCHIVE_DIR unset"}
        archive_path = Path(archive_dir)
        if not archive_path.is_dir():
            return {"deleted_count": 0, "skipped": "archive dir missing"}
        retention_days = int(getattr(settings, "DEBUG_ARCHIVE_RETENTION_DAYS", 30))
        cutoff_ts = (datetime.now() - timedelta(days=retention_days)).timestamp()
        would_delete = sum(
            1 for f in archive_path.glob("*.tar.gz")
            if f.stat().st_mtime < cutoff_ts
        )
        return {"would_delete": would_delete, "retention_days": retention_days, "dry_run": True}

    # 实际执行: 调用现有 Celery task 的同步版本
    result = cleanup_old_archives()
    logger.info("[startup_checks] cleanup_old_archives_once: %s", result)
    return result


def cleanup_old_evidence_once(dry_run: bool = False) -> dict[str, Any]:
    """active > 30 天 → 移到 archived/YYYY-MM/ (spec §4.1).

    扫描 evidence/active/ 下所有目录, 按目录名日期前缀判断.
    """
    logger.info("[startup_checks] cleanup_old_evidence_once: dry_run=%s", dry_run)
    today = date.today()
    cutoff = today - timedelta(days=EVIDENCE_ACTIVE_RETENTION_DAYS)

    if not ACTIVE_DIR.is_dir():
        logger.warning(
            "[startup_checks] cleanup_old_evidence_once: active/ 目录不存在: %s", ACTIVE_DIR,
        )
        return {"moved_count": 0, "skipped": "active dir missing"}

    moved_count = 0
    error_count = 0
    for entry in sorted(ACTIVE_DIR.iterdir()):
        if not entry.is_dir():
            continue
        m = DATE_PREFIX_RE.match(entry.name)
        if not m:
            continue
        entry_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        if entry_date >= cutoff:
            continue  # 30 天内, 保留
        # 移到 archived/YYYY-MM/
        month_folder = m.group(1)[:7]
        dst_dir = ARCHIVED_DIR / month_folder
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / entry.name
        if dst.exists():
            logger.warning(
                "[startup_checks] cleanup_old_evidence_once: 目标已存在, 跳过: %s", dst,
            )
            error_count += 1
            continue
        if dry_run:
            logger.info("[startup_checks] [DRY-RUN] would move: %s → %s", entry.name, dst)
            moved_count += 1
            continue
        try:
            shutil.move(str(entry), str(dst))
            moved_count += 1
            logger.info(
                "[startup_checks] cleanup_old_evidence_once: 已移动 %s → %s",
                entry.name, dst.relative_to(ARCHIVED_DIR),
            )
        except OSError as exc:
            error_count += 1
            logger.warning(
                "[startup_checks] cleanup_old_evidence_once: 移动失败 %s: %s", entry.name, exc,
            )

    return {
        "moved_count": moved_count,
        "error_count": error_count,
        "retention_days": EVIDENCE_ACTIVE_RETENTION_DAYS,
        "cutoff": cutoff.isoformat(),
        "dry_run": dry_run,
    }


def delete_archived_evidence_once(dry_run: bool = False) -> dict[str, Any]:
    """archived > 90 天 → 删除 (spec §4.1).

    扫描 evidence/archived/YYYY-MM/ 下所有目录.
    """
    logger.info("[startup_checks] delete_archived_evidence_once: dry_run=%s", dry_run)
    today = date.today()
    cutoff = today - timedelta(days=EVIDENCE_ARCHIVED_RETENTION_DAYS)

    if not ARCHIVED_DIR.is_dir():
        logger.warning(
            "[startup_checks] delete_archived_evidence_once: archived/ 目录不存在: %s", ARCHIVED_DIR,
        )
        return {"deleted_count": 0, "skipped": "archived dir missing"}

    deleted_count = 0
    error_count = 0
    for month_dir in sorted(ARCHIVED_DIR.iterdir()):
        if not month_dir.is_dir():
            continue
        for entry in sorted(month_dir.iterdir()):
            if not entry.is_dir():
                continue
            m = DATE_PREFIX_RE.match(entry.name)
            if not m:
                continue
            entry_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            if entry_date >= cutoff:
                continue  # 90 天内, 保留
            if dry_run:
                logger.info("[startup_checks] [DRY-RUN] would delete: %s", entry)
                deleted_count += 1
                continue
            try:
                shutil.rmtree(entry)
                deleted_count += 1
                logger.info(
                    "[startup_checks] delete_archived_evidence_once: 已删除 %s", entry.name,
                )
            except OSError as exc:
                error_count += 1
                logger.warning(
                    "[startup_checks] delete_archived_evidence_once: 删除失败 %s: %s",
                    entry.name, exc,
                )

    return {
        "deleted_count": deleted_count,
        "error_count": error_count,
        "retention_days": EVIDENCE_ARCHIVED_RETENTION_DAYS,
        "cutoff": cutoff.isoformat(),
        "dry_run": dry_run,
    }


def forgetting_check_once(dry_run: bool = False) -> dict[str, Any]:
    """遗忘机制: 处理两类超时 N## (spec §4.1 步骤 ⑤).

    1. §Active N## last_triggered > 6 月 + 无 Y/N 矩阵引用
       → 移到 archived-lessons.md (deprecated 档)
    2. §Dormant 段家族合并子条目超 6 月 + 无新复发 + 无 Y/N 矩阵引用
       → 移到 archived-lessons.md (deprecated 档)

    注意: §Dormant 段是家族合并子条目专用, 不是 Active 超时归宿
          (Active 超时直接进 archived-lessons.md, 不进 §Dormant).
    N## 四档: Active / Dormant (家族合并子条目) / Archived (deprecated, archived-lessons.md) /
              Retired (M0.M 闭环, §Retired 段, 编号永不复用).
    M0.M 闭环 N## 走 §4.4 升级路径 (→ §Retired 段), 不走遗忘机制.
    详见 failure-modes.md §归档流程.
    """
    logger.info("[startup_checks] forgetting_check_once: dry_run=%s", dry_run)
    today = date.today()
    cutoff = today - timedelta(days=FORGETTING_THRESHOLD_DAYS)

    if not FM_PATH.is_file():
        logger.warning(
            "[startup_checks] forgetting_check_once: failure-modes.md 不存在: %s", FM_PATH,
        )
        return {"archived_count": 0, "skipped": "failure-modes.md missing"}

    text = FM_PATH.read_text(encoding="utf-8")

    # 扫描 §Active 表格, 找 last_triggered < cutoff 的 N##
    # 表格行格式: | N91 | ... | 0 | 2026-07-25 |
    # last_triggered 为 "-" 视为从未触发, 不处理 (新 N## 宽限期)
    candidates: list[tuple[str, str, str]] = []  # (n_id, line, last_triggered)
    in_active = False
    for line in text.split("\n"):
        if line.startswith("| N## |") and "trigger_count" in line:
            in_active = True
            continue
        if in_active and line.startswith("|:---"):
            continue
        if in_active and re.match(r"^\| N\d+", line):
            # 解析: | N91 | ... | 0 | 2026-07-25 |
            parts = [p.strip() for p in line.split("|")]
            # parts: ['', 'N91', '主题', '硬约束', 'lessons/xxx.md', '0', '2026-07-25', '']
            if len(parts) < 7:
                continue
            n_id = parts[1]
            last_triggered = parts[6]
            if last_triggered == "-":
                continue  # 新 N## 宽限期, 不处理
            try:
                trigger_date = datetime.strptime(last_triggered, "%Y-%m-%d").date()
            except ValueError:
                continue
            if trigger_date < cutoff:
                candidates.append((n_id, line, last_triggered))

    # 检查 Y/N 矩阵引用 (yn-matrices/_*.md)
    # 用 word boundary 正则避免 N20 误匹配 N200 / N2001
    yn_matrices_dir = REPO_ROOT / ".ai-memory" / "meta" / "yn-matrices"
    referenced_n_ids = set()
    if yn_matrices_dir.is_dir():
        for ym_file in yn_matrices_dir.glob("_*.md"):
            try:
                ym_text = ym_file.read_text(encoding="utf-8")
                for n_id, _, _ in candidates:
                    # \b 边界确保 N200 不匹配 N2001/N2000
                    if re.search(rf"\b{re.escape(n_id)}\b", ym_text):
                        referenced_n_ids.add(n_id)
            except OSError:
                continue

    # 过滤: 只保留无 Y/N 矩阵引用的
    to_archive = [(n, line, date) for n, line, date in candidates if n not in referenced_n_ids]

    if not to_archive:
        logger.info("[startup_checks] forgetting_check_once: 无超时 N## 需遗忘")
        return {"archived_count": 0, "candidates": len(candidates), "dry_run": dry_run}

    if dry_run:
        for n_id, _, last_triggered in to_archive:
            logger.info(
                "[startup_checks] [DRY-RUN] would archive N## %s (last_triggered=%s)",
                n_id, last_triggered,
            )
        return {
            "archived_count": len(to_archive),
            "candidates": len(candidates),
            "dry_run": True,
        }

    # 实际执行: 从 failure-modes.md §Active 删除行, 追加到 archived-lessons.md
    archived_lines: list[str] = []
    new_lines: list[str] = []
    for line in text.split("\n"):
        archived = False
        for n_id, orig_line, _ in to_archive:
            if line == orig_line:
                archived_lines.append(f"- {n_id} (遗忘机制 {today.isoformat()}, last_triggered 见原表)")
                archived = True
                break
        if not archived:
            new_lines.append(line)

    FM_PATH.write_text("\n".join(new_lines), encoding="utf-8")

    # 追加到 archived-lessons.md
    if ARCHIVED_LESSONS_PATH.is_file():
        archived_text = ARCHIVED_LESSONS_PATH.read_text(encoding="utf-8")
    else:
        archived_text = "# Archived Lessons (deprecated 档)\n\n"
    archived_text += f"\n## 遗忘机制归档 ({today.isoformat()})\n\n"
    archived_text += "\n".join(archived_lines) + "\n"
    ARCHIVED_LESSONS_PATH.write_text(archived_text, encoding="utf-8")

    logger.info(
        "[startup_checks] forgetting_check_once: 已归档 %d 个超时 N##", len(to_archive),
    )
    return {
        "archived_count": len(to_archive),
        "candidates": len(candidates),
        "dry_run": False,
    }


def run_startup_checks(dry_run: bool = False) -> dict[str, Any]:
    """启动检查入口 (spec §5.2).

    串行跑 4 个清理函数, 任一失败不阻塞其他.
    """
    logger.info("[startup_checks] run_startup_checks: dry_run=%s", dry_run)
    results: dict[str, Any] = {"dry_run": dry_run, "checks": {}}

    checks = [
        ("cleanup_old_archives", cleanup_old_archives_once),
        ("cleanup_old_evidence", cleanup_old_evidence_once),
        ("delete_archived_evidence", delete_archived_evidence_once),
        ("forgetting_check", forgetting_check_once),
    ]

    for name, fn in checks:
        try:
            results["checks"][name] = fn(dry_run=dry_run)
        except Exception as exc:
            logger.exception("[startup_checks] %s failed", name)
            results["checks"][name] = {"error": str(exc), "exception_type": type(exc).__name__}

    return results
