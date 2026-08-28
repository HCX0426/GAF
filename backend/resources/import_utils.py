"""Resource pack import utilities.

TD-004 (Option A): `resources/` is the single source of truth for template
images and resource pack files. The database only stores metadata (pack
records, template records with file paths, tags, etc.). No file copies are
made under `MEDIA_ROOT/resource_packs/` anymore.

Previously this module copied every imported pack into
`MEDIA_ROOT/resource_packs/<name>/<version>/`, creating a second copy that
could drift away from the authoritative `resources/` directory. That copy
logic has been removed.
"""

import hashlib
import json
import logging
import re
import shutil
import zipfile
from pathlib import Path

import yaml
from django.conf import settings

from resources.models import ResourcePack, Template
from resources.validators import validate_resource_pack_structure

logger = logging.getLogger(__name__)


def read_manifest(pack_dir):
    """Read manifest.json from a resource pack directory.

    Args:
        pack_dir: Resource pack directory path (path-like, accepts str or Path).

    Returns:
        dict: Parsed manifest dict, or None on failure.
    """
    pack_path = Path(pack_dir)
    manifest_path = pack_path / "manifest.json"
    if not manifest_path.is_file():
        logger.error("manifest.json not found: %s", manifest_path)
        return None

    try:
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        logger.error("manifest.json parse error: %s", exc)
        return None


def get_resources_root():
    """Return the project-level resources/ directory (single source of truth).

    Returns:
        Path: Absolute path to `<project_root>/resources`.
    """
    return Path(settings.BASE_DIR).parent / "resources"


def get_destination_dir(manifest):
    """Return the canonical resource pack directory under resources/.

    The directory is named after the manifest's `name` field, sanitised for
    filesystem safety. This is the single source of truth location; no copy
    to MEDIA_ROOT is performed.

    Args:
        manifest: Parsed manifest dict.

    Returns:
        Path: Canonical pack directory under resources/.
    """
    import re

    pack_name = manifest.get("name", "unknown")
    # Sanitise name for filesystem: allow word chars, dash, dot, space.
    safe_name = re.sub(r"[^\w\-\. ]+", "_", pack_name).strip()
    if not safe_name:
        safe_name = "unknown"
    dest_dir = get_resources_root() / safe_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    return dest_dir


def copy_pack_files(pack_dir, dest_dir):
    """Copy all files from pack_dir into dest_dir.

    .. deprecated::
        TD-004 (Option A): `resources/` is the single source of truth, so
        copying packs into `MEDIA_ROOT/resource_packs/` is no longer needed.
        Kept temporarily for any legacy callers; new code should not use it.

    Args:
        pack_dir: Source resource pack directory (Path object).
        dest_dir: Destination directory (Path object).

    Returns:
        int: Number of files copied.
    """
    logger.warning(
        "copy_pack_files is deprecated (TD-004): resources/ is the single source of truth"
    )
    if dest_dir.exists():
        shutil.rmtree(str(dest_dir), ignore_errors=True)
    dest_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for item in pack_dir.rglob("*"):
        if item.is_file():
            rel_path = item.relative_to(pack_dir)
            target_path = dest_dir / rel_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(item), str(target_path))
            count += 1

    return count


def create_or_update_pack(manifest, directory_path, activate=False):
    """Create or update a ResourcePack database record.

    Args:
        manifest: Parsed manifest dict.
        directory_path: Canonical resource pack directory path (under resources/).
        activate: Whether to activate this pack (deactivates others).

    Returns:
        ResourcePack: Database model instance.
    """
    pack_name = manifest.get("name", "unknown")
    pack_version = manifest.get("version", "0.0.0")

    if activate:
        ResourcePack.objects.filter(is_active=True).update(is_active=False)

    resource_pack, created = ResourcePack.objects.update_or_create(
        name=pack_name,
        version=pack_version,
        defaults={
            "target_app": manifest.get("target_app", ""),
            "author": manifest.get("author", ""),
            "directory_path": str(directory_path),
            "gaf_version_compat": manifest.get("gaf_version", ""),
            "description": manifest.get("description", ""),
            "is_active": activate,
        },
    )

    action = "Created" if created else "Updated"
    logger.info("%s resource pack record: %s v%s (id=%d)", action, pack_name, pack_version, resource_pack.id)
    return resource_pack


def create_pack_zip(pack_dir, manifest):
    """Package a resource pack directory into a .gafpack zip file.

    The zip is written to `MEDIA_ROOT/resource_pack_zips/` for download/export
    purposes only; it is a transient export artifact, not the source of truth.

    Args:
        pack_dir: Canonical resource pack directory (Path object).
        manifest: Parsed manifest dict.

    Returns:
        str: Generated zip file path, or None on failure.
    """
    pack_name = manifest.get("name", "unknown")
    pack_version = manifest.get("version", "0.0.0")
    zip_filename = f"{pack_name}-{pack_version}.gafpack"

    zip_dir = Path(settings.MEDIA_ROOT) / "resource_pack_zips"
    zip_dir.mkdir(parents=True, exist_ok=True)
    zip_path = zip_dir / zip_filename

    try:
        checksums = {}
        with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in pack_dir.rglob("*"):
                if file_path.is_file():
                    rel_path = file_path.relative_to(pack_dir)
                    arc_name = str(rel_path).replace("\\", "/")
                    zf.write(str(file_path), arc_name)
                    with open(str(file_path), "rb") as fh:
                        checksums[arc_name] = hashlib.sha256(fh.read()).hexdigest()

            checksum_data = json.dumps(checksums, indent=2, ensure_ascii=False)
            zf.writestr(".checksums.json", checksum_data)

        logger.info("Resource pack zip created: %s", zip_path)
        return str(zip_path)
    except Exception as exc:
        logger.error("Failed to create resource pack zip: %s", exc)
        return None


def import_yaml_tasks(pack_dir, resource_pack):
    """Scan tasks/*.yaml and create/update Task records.

    Each YAML file is parsed to extract metadata and the full definition is stored
    in task_definition. The execution_mode is inferred from the presence of 'states'.

    Args:
        pack_dir: Resource pack source directory (Path object).
        resource_pack: ResourcePack model instance (kept for backward compatibility, not used).

    Returns:
        dict: {created: int, updated: int, errors: list}
    """
    from tasks.models import Task

    tasks_dir = pack_dir / "tasks"
    if not tasks_dir.is_dir():
        return {"created": 0, "updated": 0, "errors": []}

    stats = {"created": 0, "updated": 0, "errors": []}

    for yaml_file in sorted(tasks_dir.glob("*.yaml")):
        try:
            with open(yaml_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not isinstance(data, dict):
                stats["errors"].append(f"{yaml_file.name}: invalid YAML (not a dict)")
                continue

            name = data.get("name", yaml_file.stem)
            description = data.get("description", "")
            has_states = "states" in data and isinstance(data["states"], dict)
            # spec-2026-07-27 阶段 5: chain 已废弃, 默认走 pipeline
            execution_mode = "state_machine" if has_states else "pipeline"

            tags = [data.get("target_app", "")]
            tags = [t for t in tags if t]

            retry_policy = {
                "max_retries": 3,
                "delay_seconds": 5,
            }

            task, created = Task.objects.update_or_create(
                name=name,
                defaults={
                    "description": description,
                    "execution_mode": execution_mode,
                    "task_definition": data,
                    "tags": tags,
                    "retry_policy": retry_policy,
                    "is_enabled": True,
                    "source_type": "yaml_import",
                    # N197-8: auto-bind task to the resource pack it was imported from
                    "resource_pack": resource_pack,
                },
            )

            if created:
                stats["created"] += 1
                logger.info("Task created: %s (mode=%s)", name, execution_mode)
            else:
                stats["updated"] += 1
                logger.info("Task updated: %s (mode=%s)", name, execution_mode)

        except yaml.YAMLError as exc:
            stats["errors"].append(f"{yaml_file.name}: YAML parse error: {exc}")
            logger.error("YAML parse error in %s: %s", yaml_file.name, exc)
        except Exception as exc:
            stats["errors"].append(f"{yaml_file.name}: {exc}")
            logger.exception("Failed to import task from %s", yaml_file.name)

    logger.info(
        "Tasks import done: created=%d updated=%d errors=%d",
        stats["created"], stats["updated"], len(stats["errors"]),
    )
    return stats


def import_pipelines(pack_dir, resource_pack):
    """Scan pipelines/*.json and tasks/*.json, create/update Task records.

    Each pipeline JSON file is the single source of truth for a task definition.
    The file name (stem) is used as the task name, and the full JSON content
    is stored in task_definition. This ensures the DB is always in sync with
    the JSON files — no manual DB maintenance needed.

    The function scans both ``pipelines/`` (legacy) and ``tasks/`` (new format)
    directories for ``.json`` files.  If both directories contain the same file
    (same stem), the ``tasks/`` version wins (newer format takes precedence).

    Args:
        pack_dir: Resource pack source directory (Path object).
        resource_pack: ResourcePack model instance (used for game_profile association).

    Returns:
        dict: {created: int, updated: int, errors: list}
    """
    from tasks.models import Task

    stats = {"created": 0, "updated": 0, "errors": []}

    # Collect JSON files from both pipelines/ (legacy) and tasks/ (new format)
    json_files: dict[str, Path] = {}  # stem → path (tasks/ wins on conflict)
    for candidate in ("pipelines", "tasks"):
        d = pack_dir / candidate
        if d.is_dir():
            for jf in sorted(d.glob("*.json")):
                json_files[jf.stem] = jf  # later dir overwrites earlier

    if not json_files:
        return stats

    for _, json_file in sorted(json_files.items()):
        try:
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                stats["errors"].append(f"{json_file.name}: invalid JSON (not a dict)")
                continue

            name = data.get("name", json_file.stem)
            description = data.get("description", "")

            defaults = {
                "description": description,
                "execution_mode": "pipeline",
                "task_definition": data,
                "is_enabled": True,
                "source_type": "yaml_import",  # reuse yaml_import to avoid migration
                # N197-8: auto-bind task to the resource pack it was imported from
                "resource_pack": resource_pack,
            }

            # Associate with the resource pack's game_profile if set
            if resource_pack.game_profile_id:
                defaults["game_profile"] = resource_pack.game_profile

            task, created = Task.objects.update_or_create(
                name=name,
                defaults=defaults,
            )

            if created:
                stats["created"] += 1
                logger.info("Pipeline task created: %s (from %s)", name, json_file.name)
            else:
                stats["updated"] += 1
                logger.info("Pipeline task updated: %s (from %s)", name, json_file.name)

        except json.JSONDecodeError as exc:
            stats["errors"].append(f"{json_file.name}: JSON parse error: {exc}")
            logger.error("JSON parse error in %s: %s", json_file.name, exc)
        except Exception as exc:
            stats["errors"].append(f"{json_file.name}: {exc}")
            logger.exception("Failed to import pipeline from %s", json_file.name)

    logger.info(
        "Pipelines import done: created=%d updated=%d errors=%d",
        stats["created"], stats["updated"], len(stats["errors"]),
    )
    return stats


def write_task_to_json_file(task, resource_pack):
    """Write a Task record to a tasks/*.json file in the resource pack directory.

    This is the reverse of import_pipelines — instead of reading JSON → DB,
    we write DB → JSON. This ensures the JSON file is always the source of
    truth, even when tasks are created/edited through the API.

    The file is written to ``<pack_dir>/tasks/<task_name>.json``.

    Args:
        task: Task model instance (must have task_definition, name, description).
        resource_pack: ResourcePack model instance (must have directory_path).

    Returns:
        str: Path to the written JSON file, or None on failure.
    """
    pack_dir = Path(resource_pack.directory_path)
    tasks_dir = pack_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    # Build the JSON content from the task record
    data = dict(task.task_definition or {})
    data["name"] = task.name
    data["description"] = task.description or ""

    # Sanitise filename: replace unsafe chars, keep .json extension
    safe_name = re.sub(r"[^\w\-\. ]+", "_", task.name).strip()
    if not safe_name:
        safe_name = f"task_{task.id}"
    json_path = tasks_dir / f"{safe_name}.json"

    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Task written to JSON file: %s (from task %s)", json_path, task.name)
        return str(json_path)
    except Exception as exc:
        logger.error("Failed to write task %s to JSON: %s", task.name, exc)
        return None


def delete_task_json_file(task, resource_pack):
    """Delete the tasks/*.json file for a Task from the resource pack directory.

    Args:
        task: Task model instance (used for name).
        resource_pack: ResourcePack model instance (must have directory_path).

    Returns:
        bool: True if deleted, False if file not found or error.
    """
    pack_dir = Path(resource_pack.directory_path)
    tasks_dir = pack_dir / "tasks"

    # Try both the sanitised name and the original name
    safe_name = re.sub(r"[^\w\-\. ]+", "_", task.name).strip()
    candidates = [
        tasks_dir / f"{safe_name}.json",
        tasks_dir / f"{task.name}.json",
    ]
    # Also try the stem of the task's original file if source_type is yaml_import
    # and task_definition was originally loaded from a JSON file.

    for json_path in candidates:
        if json_path.is_file():
            try:
                json_path.unlink()
                logger.info("Deleted JSON file: %s (for task %s)", json_path, task.name)
                return True
            except Exception as exc:
                logger.error("Failed to delete JSON file %s: %s", json_path, exc)
                return False

    logger.warning("JSON file not found for task %s (tried: %s)", task.name, candidates)
    return False


def import_templates(pack_dir, resource_pack):
    """Scan templates/ directory and register all .png files as Template records.

    Each .png file is registered with name = subdirectory/filename and
    template_type = parent subdirectory name (e.g. 'login', 'get_pvp').

    Args:
        pack_dir: Resource pack source directory (Path object).
        resource_pack: ResourcePack model instance to link templates to.

    Returns:
        dict: {created: int, updated: int, errors: list}
    """
    templates_dir = pack_dir / "templates"
    if not templates_dir.is_dir():
        return {"created": 0, "updated": 0, "errors": []}

    stats = {"created": 0, "updated": 0, "errors": []}

    for png_file in sorted(templates_dir.rglob("*.png")):
        try:
            rel_path = str(png_file.relative_to(pack_dir)).replace("\\", "/")
            parent_dir = png_file.relative_to(templates_dir).parent
            template_type = str(parent_dir).replace("\\", "/") if str(parent_dir) != "." else "root"
            name = str(png_file.relative_to(templates_dir)).replace("\\", "/")

            template, created = Template.objects.update_or_create(
                resource_pack=resource_pack,
                name=name,
                defaults={
                    "image_path": rel_path,
                    "template_type": template_type,
                    "match_threshold": 0.8,
                    "is_active": True,
                },
            )

            if created:
                stats["created"] += 1
            else:
                stats["updated"] += 1

        except Exception as exc:
            stats["errors"].append(f"{png_file.name}: {exc}")
            logger.exception("Failed to import template %s", png_file)

    logger.info(
        "Templates import done: created=%d updated=%d errors=%d",
        stats["created"], stats["updated"], len(stats["errors"]),
    )
    return stats


def import_monitors(pack_dir, resource_pack):
    """Scan monitors/*.yaml and create/update MonitorRule records.

    Each YAML file is parsed and the full definition is stored in rule_definition.
    The name and description are extracted from the YAML metadata.

    Args:
        pack_dir: Resource pack source directory (Path object).
        resource_pack: ResourcePack model instance to link rules to.

    Returns:
        dict: {created: int, updated: int, errors: list}
    """
    from monitors.models import MonitorRule

    monitors_dir = pack_dir / "monitors"
    if not monitors_dir.is_dir():
        return {"created": 0, "updated": 0, "errors": []}

    stats = {"created": 0, "updated": 0, "errors": []}

    for yaml_file in sorted(monitors_dir.glob("*.yaml")):
        try:
            with open(yaml_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not isinstance(data, dict):
                stats["errors"].append(f"{yaml_file.name}: invalid YAML")
                continue

            name = data.get("name", yaml_file.stem)

            rule, created = MonitorRule.objects.update_or_create(
                name=name,
                resource_pack=resource_pack,
                defaults={
                    "rule_definition": data,
                    "is_enabled": True,
                },
            )

            if created:
                stats["created"] += 1
                logger.info("MonitorRule created: %s", name)
            else:
                stats["updated"] += 1
                logger.info("MonitorRule updated: %s", name)

        except yaml.YAMLError as exc:
            stats["errors"].append(f"{yaml_file.name}: YAML error: {exc}")
            logger.error("YAML parse error in %s: %s", yaml_file.name, exc)
        except Exception as exc:
            stats["errors"].append(f"{yaml_file.name}: {exc}")
            logger.exception("Failed to import monitor from %s", yaml_file.name)

    logger.info(
        "Monitors import done: created=%d updated=%d errors=%d",
        stats["created"], stats["updated"], len(stats["errors"]),
    )
    return stats


def import_config(pack_dir, resource_pack):
    """Read config/settings.json and store it in ResourcePack.config_data.

    Args:
        pack_dir: Resource pack source directory (Path object).
        resource_pack: ResourcePack model instance to update.

    Returns:
        dict: {settings: dict or None, errors: list}
    """
    config_dir = pack_dir / "config"
    if not config_dir.is_dir():
        return {"settings": None, "errors": []}

    stats = {"settings": None, "errors": []}
    settings_path = config_dir / "settings.json"

    if settings_path.is_file():
        try:
            with open(settings_path, encoding="utf-8") as f:
                config_json = json.load(f)
            resource_pack.config_data = config_json
            resource_pack.save(update_fields=["config_data", "updated_at"])
            stats["settings"] = config_json
            logger.info("Config imported for pack %s: %s keys", resource_pack.name, len(config_json))
        except (json.JSONDecodeError, Exception) as exc:
            stats["errors"].append(f"settings.json: {exc}")
            logger.error("Failed to import config from %s: %s", settings_path, exc)
    else:
        logger.info("No settings.json found in %s", config_dir)

    return stats


def migrate_resource_pack(resource_pack_path, activate=False, deep_import=False):
    """Register a resource pack directory from resources/ into the database.

    TD-004 (Option A): This function no longer copies files into
    `MEDIA_ROOT/resource_packs/`. The directory under `resources/` is the
    single source of truth; the database only stores metadata.

    Flow:
    1. Read manifest.json for metadata.
    2. Validate directory structure.
    3. Create/update ResourcePack database record (directory_path points to
       the canonical `resources/<name>/` directory).
    4. Optionally deep-import tasks, templates, monitors, config.
    5. Create an export zip in MEDIA_ROOT/resource_pack_zips/ (transient).

    Args:
        resource_pack_path: Resource pack directory path under resources/.
        activate: Whether to activate the pack after import.
        deep_import: Whether to import tasks/templates/monitors/config.

    Returns:
        dict: Import result statistics.
    """
    pack_dir = Path(resource_pack_path)
    if not pack_dir.is_dir():
        logger.error("Resource pack directory does not exist: %s", resource_pack_path)
        return {"error": "Resource pack directory does not exist"}

    stats = {
        "manifest": None,
        "validation": None,
        "resource_pack_id": None,
        "directory": str(pack_dir),
        "zip_created": False,
        "zip_path": "",
        "tasks_imported": None,
        "pipelines_imported": None,
        "templates_imported": None,
        "monitors_imported": None,
        "config_data": None,
    }

    manifest = read_manifest(pack_dir)
    if manifest is None:
        return {"error": "manifest.json missing or invalid"}
    stats["manifest"] = manifest

    validation = validate_resource_pack_structure(str(pack_dir))
    stats["validation"] = validation
    if not validation["valid"]:
        logger.error("Resource pack validation failed: %s", validation["errors"])
        return {"error": "Resource pack validation failed", "details": validation["errors"]}

    dest_dir = get_destination_dir(manifest)
    # Ensure canonical directory exists and is in sync with pack_dir.
    # For packs already under resources/ this is a no-op; for imports from
    # elsewhere the caller is responsible for placing files under resources/.
    if pack_dir.resolve() != dest_dir.resolve():
        if dest_dir.exists():
            shutil.rmtree(str(dest_dir), ignore_errors=True)
        shutil.copytree(str(pack_dir), str(dest_dir))
        pack_dir = dest_dir

    resource_pack = create_or_update_pack(manifest, str(pack_dir), activate)
    stats["resource_pack_id"] = resource_pack.id

    if deep_import:
        stats["tasks_imported"] = import_yaml_tasks(pack_dir, resource_pack)
        stats["pipelines_imported"] = import_pipelines(pack_dir, resource_pack)
        stats["templates_imported"] = import_templates(pack_dir, resource_pack)
        stats["monitors_imported"] = import_monitors(pack_dir, resource_pack)
        stats["config_data"] = import_config(pack_dir, resource_pack)

    zip_path = create_pack_zip(pack_dir, manifest)
    if zip_path:
        stats["zip_created"] = True
        stats["zip_path"] = zip_path

    logger.info(
        "Resource pack migration complete: name=%s, version=%s, dir=%s, zip=%s",
        manifest.get("name"), manifest.get("version"), pack_dir, zip_path,
    )
    return stats
