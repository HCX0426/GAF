"""Cleanup command for TD-004 (Option A).

Removes the obsolete `MEDIA_ROOT/resource_packs/` directory tree. After this
command runs, template images and resource pack files live only under the
project `resources/` directory (single source of truth).

This command is safe to run multiple times: it only deletes the
`resource_packs` subdirectory inside `MEDIA_ROOT`. It refuses to run if the
target path does not look like a MEDIA_ROOT/resource_packs directory, as an
extra safety guard.
"""

import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Delete obsolete MEDIA_ROOT/resource_packs/ copies (TD-004 Option A)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip the confirmation prompt.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        yes = options["yes"]

        media_root = Path(settings.MEDIA_ROOT).resolve()
        target = media_root / "resource_packs"

        if not target.exists():
            self.stdout.write(self.style.NOTICE(f"Directory does not exist: {target}"))
            return

        # Safety guard: the target must be inside MEDIA_ROOT and named resource_packs.
        try:
            target.relative_to(media_root)
        except ValueError as exc:
            self.stderr.write(self.style.ERROR(f"Refusing to delete path outside MEDIA_ROOT: {target}"))
            raise SystemExit(1) from exc

        if target.name != "resource_packs":
            self.stderr.write(self.style.ERROR(f"Refusing to delete unexpected directory: {target}"))
            raise SystemExit(1)

        file_count = sum(1 for _ in target.rglob("*") if _.is_file())
        dir_count = sum(1 for _ in target.rglob("*") if _.is_dir())

        self.stdout.write(f"Target directory: {target}")
        self.stdout.write(f"Contains approximately {file_count} files and {dir_count} subdirectories.")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run: no files were deleted."))
            return

        if not yes:
            confirm = input("Delete this directory and all its contents? [y/N]: ")
            if confirm.lower() not in ("y", "yes"):
                self.stdout.write(self.style.NOTICE("Cleanup aborted."))
                return

        shutil.rmtree(str(target), ignore_errors=True)
        self.stdout.write(self.style.SUCCESS(f"Deleted obsolete directory: {target}"))
