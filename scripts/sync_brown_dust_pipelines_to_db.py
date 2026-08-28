"""Sync all resources/<game>/tasks/*.json files to DB tasks.

N191 schema-unification fix (2026-07-28, BD2 get_email 测试发现):
数据库 task_definition 与 resources/<game>/tasks/*.json 不同步 —
DB 中 task id=3 之前是旧 steps 格式, 与已转换为新 schema 的 pipeline 文件不一致.
此脚本:
1. 扫描 resources/<game>/tasks/*.json 所有 pipeline 文件 (tasks/ 是唯一数据源,
   旧 pipelines/ 目录已废弃).
2. 根据 task.name 或 task.description 匹配 DB task (按 pipeline 文件 name 字段).
3. 将最新 pipeline 内容同步到 task.task_definition + execution_mode='pipeline'.
4. 报告同步结果 (新增/更新/跳过).

用法:
    conda run -n gaf python scripts/sync_brown_dust_pipelines_to_db.py
    conda run -n gaf python scripts/sync_brown_dust_pipelines_to_db.py --game BrownDust-II
    conda run -n gaf python scripts/sync_brown_dust_pipelines_to_db.py --dry-run

注意:
- 默认 --game BrownDust-II, 可通过 --game 指定其他游戏.
- --dry-run 仅打印将要同步的内容, 不写 DB.
- 匹配规则: pipeline 文件 name 字段 == task.name (大小写不敏感, 去除前后空格).
  若无匹配 task, 跳过并打印警告 (不自动创建 task, 避免误创建).
- task_definition 结构: {version, description, metadata, entry_node, nodes, edges}.
- 同步后 task.execution_mode 强制设为 'pipeline'.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Make backend importable
sys.path.insert(0, str(Path("backend").resolve()))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from tasks.models import Task  # noqa: E402


def build_task_definition(pipeline_data: dict) -> dict:
    """Build task_definition dict from pipeline file content (new schema)."""
    return {
        "version": pipeline_data.get("version", "1.0.0"),
        "description": pipeline_data.get("description", ""),
        "metadata": pipeline_data.get("metadata", {}),
        "entry_node": pipeline_data.get("entry_node"),
        "nodes": pipeline_data.get("nodes", []),
        "edges": pipeline_data.get("edges", []),
    }


def find_task_for_pipeline(pipeline_data: dict, pipeline_filename: str) -> Task | None:
    """Find DB task matching this pipeline file.

    Match priority:
    1. task.name exact match with pipeline.name (case-insensitive)
    2. task.name starts with pipeline.name (e.g. "BD2 - login" matches "login")
    3. task.description contains pipeline.name
    4. task.name contains pipeline filename stem (e.g. "get_email")
    """
    pipeline_name = pipeline_data.get("name", "").strip().lower()
    pipeline_stem = Path(pipeline_filename).stem.lower()

    # Priority 1: exact match
    for task in Task.objects.all():
        task_name = (task.name or "").strip().lower()
        if task_name == pipeline_name:
            return task

    # Priority 2: task.name starts with pipeline.name
    for task in Task.objects.all():
        task_name = (task.name or "").strip().lower()
        if task_name.startswith(pipeline_name) and pipeline_name:
            return task

    # Priority 3: task.description contains pipeline.name
    for task in Task.objects.all():
        task_desc = (task.description or "").lower()
        if pipeline_name and pipeline_name in task_desc:
            return task

    # Priority 4: task.name contains pipeline filename stem
    for task in Task.objects.all():
        task_name = (task.name or "").lower()
        if pipeline_stem in task_name:
            return task

    return None


def sync_pipeline_to_task(
    pipeline_path: Path,
    task: Task,
    dry_run: bool = False,
) -> dict:
    """Sync one pipeline file to one DB task. Returns sync report dict."""
    with pipeline_path.open(encoding="utf-8") as f:
        pipeline_data = json.load(f)

    new_task_def = build_task_definition(pipeline_data)
    old_task_def = task.task_definition if isinstance(task.task_definition, dict) else {}
    old_mode = task.execution_mode
    old_nodes_count = len(old_task_def.get("nodes", []))
    old_has_steps = "steps" in old_task_def
    new_nodes_count = len(new_task_def["nodes"])
    new_edges_count = len(new_task_def["edges"])

    report = {
        "task_id": task.id,
        "task_name_old": task.name,
        "task_name_new": f"BD2 - {pipeline_data['name']}",
        "pipeline_file": pipeline_path.name,
        "execution_mode_old": old_mode,
        "execution_mode_new": "pipeline",
        "nodes_old": old_nodes_count,
        "nodes_new": new_nodes_count,
        "edges_new": new_edges_count,
        "had_legacy_steps": old_has_steps,
        "needs_sync": (
            old_mode != "pipeline"
            or old_has_steps
            or old_nodes_count != new_nodes_count
            or old_task_def.get("entry_node") != new_task_def.get("entry_node")
        ),
        "dry_run": dry_run,
    }

    if dry_run:
        return report

    # Apply sync
    task.task_definition = new_task_def
    task.execution_mode = "pipeline"
    task.name = f"BD2 - {pipeline_data['name']}"
    task.description = pipeline_data.get("description", "")[:200]
    task.save(update_fields=["task_definition", "execution_mode", "name", "description", "updated_at"])
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync resources/<game>/tasks/*.json to DB tasks.")
    parser.add_argument("--game", default="BrownDust-II", help="Game directory name under resources/")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be synced without writing DB.")
    args = parser.parse_args()

    # N205 (2026-08-21): tasks/ 是唯一数据源, pipelines/ 目录已废弃 (N191 归一化).
    game_dir = Path("resources") / args.game
    tasks_dir = game_dir / "tasks"

    if not tasks_dir.is_dir():
        print(f"[ERROR] No tasks/ directory found under: {game_dir} (pipelines/ 已废弃)")
        return 1

    pipeline_files = sorted(tasks_dir.glob("*.json"))
    if not pipeline_files:
        print(f"[ERROR] no pipeline files in {tasks_dir}")
        return 1

    print(f"{'[DRY-RUN] ' if args.dry_run else ''}Syncing {len(pipeline_files)} pipelines from {tasks_dir}")
    print("=" * 80)

    synced = 0
    skipped = 0
    errors = 0

    for pipeline_path in pipeline_files:
        try:
            with pipeline_path.open(encoding="utf-8") as f:
                pipeline_data = json.load(f)
            pipeline_name = pipeline_data.get("name", pipeline_path.stem)

            task = find_task_for_pipeline(pipeline_data, pipeline_path.name)
            if task is None:
                print(f"[SKIP] {pipeline_path.name}: no matching DB task for '{pipeline_name}'")
                skipped += 1
                continue

            report = sync_pipeline_to_task(pipeline_path, task, dry_run=args.dry_run)

            if not report["needs_sync"]:
                print(f"[OK]    {pipeline_path.name}: task id={report['task_id']} already up-to-date "
                      f"(nodes={report['nodes_new']}, mode={report['execution_mode_old']})")
                skipped += 1
            else:
                action = "would sync" if args.dry_run else "synced"
                print(f"[SYNC]  {pipeline_path.name}: {action} task id={report['task_id']}")
                print(f"        name:    '{report['task_name_old']}' -> '{report['task_name_new']}'")
                print(f"        mode:    {report['execution_mode_old']} -> {report['execution_mode_new']}")
                print(f"        nodes:   {report['nodes_old']} -> {report['nodes_new']}")
                print(f"        edges:   {report['edges_new']}")
                print(f"        legacy-steps: {report['had_legacy_steps']}")
                synced += 1
        except Exception as exc:
            print(f"[ERROR] {pipeline_path.name}: {exc}")
            errors += 1

    print("=" * 80)
    print(f"Total: {len(pipeline_files)} pipelines, {synced} {'would-sync' if args.dry_run else 'synced'}, "
          f"{skipped} skipped, {errors} errors")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
