"""Django management command: run_startup_checks (spec §5.2).

调用 gaf_core.startup_checks.run_startup_checks, 启动时跑一次.

Usage:
    python manage.py run_startup_checks               # 实际执行
    python manage.py run_startup_checks --dry-run      # 预览不修改
    python manage.py run_startup_checks --all          # 跑所有检查 (默认行为)
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from gaf_core.startup_checks import run_startup_checks


class Command(BaseCommand):
    help = "GAF 启动时跑一次的检查任务 (spec §5): cleanup + forgetting"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只打印不实际修改",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            default=True,
            help="跑所有检查 (默认行为, 保留为兼容)",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        self.stdout.write(
            self.style.SUCCESS(
                f"启动检查 (dry_run={dry_run})..."
            )
        )
        results = run_startup_checks(dry_run=dry_run)
        self.stdout.write(json.dumps(results, indent=2, ensure_ascii=False, default=str))
        self.stdout.write(self.style.SUCCESS("启动检查完成."))
