"""
Management command: backfill resource_pack FK for existing Task records.

Scans all resource pack directories (pipelines/*.json and tasks/*.yaml),
reads the task name from each file, and binds matching Task records
to the corresponding ResourcePack.

Usage:
    conda run -n gaf python manage.py backfill_resource_pack
    conda run -n gaf python manage.py backfill_resource_pack --dry-run
"""

import json
import logging
from pathlib import Path

from django.core.management.base import BaseCommand

from resources.models import ResourcePack
from tasks.models import Task

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfill resource_pack FK for existing tasks by matching file names in resource pack directories."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only show what would be bound, without making changes.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        stats = {"matched": 0, "skipped": 0, "errors": 0, "total_tasks": Task.objects.count()}

        for rp in ResourcePack.objects.all():
            pack_dir = Path(rp.directory_path)
            if not pack_dir.is_dir():
                self.stderr.write(f"  [SKIP] Directory not found: {pack_dir}")
                stats["skipped"] += 1
                continue

            # Collect task names from pipelines/ and tasks/ directories
            task_names = self._collect_task_names(pack_dir)

            if not task_names:
                self.stdout.write(f"  [SKIP] {rp.name} v{rp.version}: no pipelines/ or tasks/ found")
                stats["skipped"] += 1
                continue

            # Find matching Task records by name
            matching_tasks = Task.objects.filter(name__in=task_names, resource_pack__isnull=True)
            match_count = matching_tasks.count()

            if match_count == 0:
                self.stdout.write(f"  [OK]   {rp.name} v{rp.version}: {len(task_names)} files, "
                                  f"0 unbound tasks to backfill")
                stats["skipped"] += 1
                continue

            if dry_run:
                self.stdout.write(f"  [DRY]  {rp.name} v{rp.version}: would bind {match_count} tasks")
                for t in matching_tasks.order_by("name"):
                    self.stdout.write(f"         -> Task '{t.name}' (id={t.id})")
                stats["matched"] += match_count
            else:
                updated = matching_tasks.update(resource_pack=rp)
                self.stdout.write(f"  [BIND] {rp.name} v{rp.version}: bound {updated} tasks")
                for t in matching_tasks.order_by("name"):
                    self.stdout.write(f"         -> Task '{t.name}' (id={t.id})")
                stats["matched"] += updated

        self.stdout.write("\n=== Summary ===")
        self.stdout.write(f"  Total tasks in DB:  {stats['total_tasks']}")
        self.stdout.write(f"  Matched (bound/dry): {stats['matched']}")
        self.stdout.write(f"  Skipped:             {stats['skipped']}")
        self.stdout.write(f"  Errors:              {stats['errors']}")

        if dry_run:
            self.stdout.write("\nRun without --dry-run to apply changes.")

    def _collect_task_names(self, pack_dir: Path) -> set:
        """Collect task names from tasks/*.json (preferred) and pipelines/*.json (legacy)."""
        names = set()

        # Prefer tasks/ (current format)
        tasks_dir = pack_dir / "tasks"
        if tasks_dir.is_dir():
            for json_file in sorted(tasks_dir.glob("*.json")):
                try:
                    with open(json_file, encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        name = data.get("name", json_file.stem)
                        names.add(name)
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning("Failed to parse %s: %s", json_file, exc)

        # Fall back to pipelines/ (legacy format)
        pipelines_dir = pack_dir / "pipelines"
        if pipelines_dir.is_dir():
            for json_file in sorted(pipelines_dir.glob("*.json")):
                try:
                    with open(json_file, encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        name = data.get("name", json_file.stem)
                        names.add(name)
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning("Failed to parse %s: %s", json_file, exc)

        return names
