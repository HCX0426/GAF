"""TD-004 (Option A): Point ResourcePack.directory_path to resources/.

Previously resource packs were copied into
`MEDIA_ROOT/resource_packs/<name>/<version>/`, creating a second copy that
could drift away from the authoritative `resources/<name>/` directory. This
migration updates existing ResourcePack records so that `directory_path`
points to the canonical location under the project `resources/` directory.

The migration is idempotent: it only updates paths that currently point to
`MEDIA_ROOT/resource_packs/`. If the corresponding `resources/<name>/`
directory does not exist, the record is left unchanged and logged as a
warning so an administrator can resolve the mismatch manually.
"""

import json
import logging
import re
from pathlib import Path

from django.conf import settings
from django.db import migrations

logger = logging.getLogger(__name__)


def _find_canonical_dir(resources_root, pack_name):
    """Find the resources/ subdirectory whose manifest.json name matches pack_name."""
    if not resources_root.is_dir():
        return None
    for subdir in resources_root.iterdir():
        if not subdir.is_dir():
            continue
        manifest_path = subdir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            if manifest.get("name") == pack_name:
                return subdir
        except Exception:
            continue
    return None


def forwards(apps, schema_editor):
    """Update directory_path from MEDIA_ROOT copy to resources/ canonical path."""
    ResourcePack = apps.get_model("resources", "ResourcePack")
    resources_root = Path(settings.BASE_DIR).parent / "resources"

    updated = 0
    skipped = 0
    missing = 0

    for pack in ResourcePack.objects.all():
        if not pack.directory_path:
            skipped += 1
            continue

        current_path = Path(pack.directory_path)

        # Detect any path that points to a MEDIA_ROOT/resource_packs/ copy,
        # even if the absolute prefix differs (e.g. project was moved).
        normalized = current_path.as_posix()
        if "media/resource_packs/" not in normalized and "media\\resource_packs\\" not in str(current_path):
            skipped += 1
            continue

        # Find the canonical resources/<name>/ directory by matching manifest name.
        canonical_path = _find_canonical_dir(resources_root, pack.name)

        if canonical_path is None:
            logger.warning(
                "TD-004 migration: canonical resources directory not found for pack %r (id=%s)",
                pack.name, pack.id,
            )
            missing += 1
            continue

        pack.directory_path = str(canonical_path)
        pack.save(update_fields=["directory_path", "updated_at"])
        updated += 1
        logger.info(
            "TD-004 migration: updated pack %r (id=%s) directory_path to %s",
            pack.name, pack.id, canonical_path,
        )

    logger.info(
        "TD-004 migration complete: updated=%d, skipped=%d, missing=%d",
        updated, skipped, missing,
    )


def backwards(apps, schema_editor):
    """No-op reverse migration.

    Reverting this migration would require recreating the MEDIA_ROOT copies,
    which is intentionally not supported because those copies are the source
    of the drift problem.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("resources", "0005_config_data"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
