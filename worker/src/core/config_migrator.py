"""Configuration version migration system.

Provides incremental config schema evolution with backup/rollback safety,
inspired by Alas ConfigUpdater (redirection + save_callback pattern).
Supports chained migrations (v1 -> v2 -> v3 -> ... -> vN) where each
step is an independent, registered transformation function.
"""

import copy
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class ConfigMigrator:
    """Manages configuration version migrations with safety guarantees.

    Each migration step is a callable ``(config: dict) -> dict`` that receives
    the config dict at version *N* and must return it transformed to version
    *N+1*.  Steps are registered via :meth:`register_version` and executed
    in order by :meth:`migrate`.

    Attributes:
        _migrations: Ordered mapping of ``{target_version: migration_fn}``.
        _backup: Deep copy of the original config before any migration runs.
        _log: Chronological list of migration records for audit.
        save_callback: Optional hook invoked after a successful migration so
            the caller can persist the result.
    """

    def __init__(self, save_callback: Callable[[dict[str, Any], int], None] | None = None):
        """Initialise the migrator with an optional persistence hook.

        Args:
            save_callback: Called as ``save_callback(config, new_version)``
                after every successful migration step.  Use this to write the
                updated config to disk / database.
        """
        self._migrations: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}
        self._backup: dict[str, Any] | None = None
        self._log: list[dict[str, Any]] = []
        self.save_callback = save_callback

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_version(self, version: int, migration_fn: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        """Register a migration function that upgrades config to *version*.

        The function must accept a dict at version *(version-1)* and return
        the dict mutated (or a new dict) at *version*.

        Args:
            version: Target version number this function produces.
            migration_fn: Callable ``(config: dict) -> dict``.

        Raises:
            ValueError: If *version* <= 0 or a migration for this version is
                already registered.
        """
        if version <= 0:
            raise ValueError(f"Version must be > 0, got {version}")
        if version in self._migrations:
            raise ValueError(f"Migration for version {version} already registered")
        self._migrations[version] = migration_fn
        logger.debug("Registered migration to version %d", version)

    def migrate(self, config: dict[str, Any], from_ver: int, to_ver: int) -> dict[str, Any]:
        """Execute incremental migration from *from_ver* to *to_ver*.

        If *from_ver* < *to_ver*, all intermediate steps between them are
        applied in ascending order (chained migration).  A deep-copy backup
        is taken before the first step; on failure the backup is restored.

        Args:
            config: The configuration dictionary to migrate.
            from_ver: Current version of *config*.  Must be >= 1.
            to_ver: Desired target version.  Must be >= *from_ver*.

        Returns:
            The migrated configuration dictionary at *to_ver*.

        Raises:
            ValueError: If version numbers are invalid or a required migration
                step is missing.
            RuntimeError: If any migration step fails; the original config is
                automatically restored from backup.
        """
        if from_ver < 1:
            raise ValueError(f"from_ver must be >= 1, got {from_ver}")
        if to_ver < from_ver:
            raise ValueError(f"to_ver ({to_ver}) must be >= from_ver ({from_ver})")
        if from_ver == to_ver:
            logger.info("Config already at version %d, nothing to do", to_ver)
            return config

        self._create_backup(config)

        current = copy.deepcopy(config)
        current_version = from_ver

        try:
            for target in range(from_ver + 1, to_ver + 1):
                if target not in self._migrations:
                    raise ValueError(
                        f"No migration registered for version {target}. "
                        f"Available versions: {sorted(self._migrations.keys())}"
                    )

                fn = self._migrations[target]
                prev_snapshot = copy.deepcopy(current)

                logger.info("Migrating config from v%d -> v%d ...", current_version, target)
                current = fn(current)

                if not isinstance(current, dict):
                    raise TypeError(
                        f"Migration fn for v{target} returned {type(current).__name__}, expected dict"
                    )

                self._record_log(current_version, target, prev_snapshot, current)
                current_version = target

                if self.save_callback is not None:
                    try:
                        self.save_callback(current, target)
                    except Exception as exc:
                        logger.warning("save_callback failed after v%d: %s", target, exc)

            logger.info(
                "Migration complete: v%d -> v%d (%d steps applied)",
                from_ver, to_ver, to_ver - from_ver,
            )
            return current

        except Exception:
            logger.error(
                "Migration failed at v%d -> v%d, rolling back to v%d",
                current_version, current_version + 1, from_ver,
            )
            self._rollback()
            raise RuntimeError(
                f"Migration from v{from_ver} to v{to_ver} failed at step "
                f"v{current_version}. Original config has been restored."
            ) from None

    def detect_version(self, config: dict[str, Any]) -> int:
        """Detect the schema version of a configuration dictionary.

        Looks for the reserved key ``'__config_version__'`` first.  If absent,
        heuristics are applied based on known field presence/absence patterns
        from registered migrations.  When no heuristic matches, version ``1``
        is assumed (legacy / unversioned config).

        Args:
            config: Configuration dictionary to inspect.

        Returns:
            Detected version number (integer >= 1).
        """
        explicit = config.get("__config_version__")
        if explicit is not None:
            try:
                ver = int(explicit)
                if ver >= 1:
                    return ver
            except (TypeError, ValueError):
                pass

        detected = self._heuristic_detect(config)
        if detected > 0:
            return detected

        logger.info("No version marker found, assuming legacy config v1")
        return 1

    def get_latest_version(self) -> int:
        """Return the highest registered (target) version number.

        Returns:
            The latest version, or ``0`` if no migrations are registered.
        """
        if not self._migrations:
            return 0
        return max(self._migrations.keys())

    @property
    def migration_log(self) -> list[dict[str, Any]]:
        """Read-only access to the audit log of all performed migrations."""
        return list(self._log)

    # ------------------------------------------------------------------
    # Safety helpers
    # ------------------------------------------------------------------

    def _create_backup(self, config: dict[str, Any]) -> None:
        """Store a deep copy of the original config for rollback."""
        self._backup = copy.deepcopy(config)
        logger.debug("Backup created (%d top-level keys)", len(self._backup))

    def _rollback(self) -> dict[str, Any]:
        """Restore the config from the backup taken before migration started.

        Returns:
            The backed-up (original) configuration dictionary.

        Raises:
            RuntimeError: If no backup exists (should never happen in normal
                flow because :meth:`_create_backup` is called first).
        """
        if self._backup is None:
            raise RuntimeError("Cannot roll back — no backup available")
        restored = copy.deepcopy(self._backup)
        logger.info("Rollback complete — config restored to pre-migration state")
        return restored

    def _record_log(
        self,
        from_ver: int,
        to_ver: int,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> None:
        """Append an entry to the internal migration audit log.

        Args:
            from_ver: Source version of this step.
            to_ver: Target version of this step.
            before: Config snapshot before the step ran.
            after: Config snapshot after the step completed.
        """
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "from_version": from_ver,
            "to_version": to_ver,
            "changed_keys": self._diff_keys(before, after),
        }
        self._log.append(entry)
        logger.debug(
            "Log entry: v%d->v%d changed keys=%s",
            from_ver, to_ver, entry["changed_keys"],
        )

    @staticmethod
    def _diff_keys(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
        """Compute which top-level keys were added, removed or modified.

        Args:
            before: Dictionary state before the change.
            after: Dictionary state after the change.

        Returns:
            List of key names that differ between the two snapshots.
        """
        all_keys = set(before.keys()) | set(after.keys())
        changed = [k for k in sorted(all_keys) if before.get(k) != after.get(k)]
        return changed

    # ------------------------------------------------------------------
    # Heuristic version detection
    # ------------------------------------------------------------------

    def _heuristic_detect(self, config: dict[str, Any]) -> int:
        """Try to infer version by checking field presence against known patterns.

        Scans registered migrations in reverse order (newest first).  For each
        migration target version we check whether fields that version *adds*
        are present in the config.  The highest matching version wins.

        Args:
            config: Configuration dictionary to inspect.

        Returns:
            Detected version, or ``0`` if no heuristic matches.
        """
        best_match = 0
        for target_ver in sorted(self._migrations.keys(), reverse=True):
            fn = self._migrations[target_ver]
            hints = getattr(fn, "_version_hints", None)
            if hints and all(k in config for k in hints.get("added", [])):
                best_match = target_ver - 1
                break
        return best_match


# ======================================================================
# Built-in example migration rules
# ======================================================================

def _migrate_v1_to_v2(config: dict[str, Any]) -> dict[str, Any]:
    """Rename deprecated field names (v1 -> v2).

    Field mappings:
        - ``old_name``  -> ``new_name``
        - ``old_timeout`` -> ``timeout_seconds``
    """
    renames = {"old_name": "new_name", "old_timeout": "timeout_seconds"}
    for old_key, new_key in renames.items():
        if old_key in config:
            config[new_key] = config.pop(old_key)
    config["__config_version__"] = 2
    return config

# Attach hints so heuristic detection can use them later
_migrate_v1_to_v2._version_hints = {"added": ["new_name", "timeout_seconds"], "removed": ["old_name", "old_timeout"]}


def _migrate_v2_to_v3(config: dict[str, Any]) -> dict[str, Any]:
    """Coerce string-typed numeric fields to native int (v2 -> v3).

    Fields converted (with default fallback when value is not parseable):
        - ``retry_count``: str -> int, default ``3``
        - ``max_workers``: str -> int, default ``4``
    """
    conversions = {"retry_count": 3, "max_workers": 4}
    for key, default in conversions.items():
        if key in config:
            val = config[key]
            if isinstance(val, str):
                try:
                    config[key] = int(val)
                except (ValueError, TypeError):
                    logger.warning("Could not convert '%s'='%s' to int, using default %d", key, val, default)
                    config[key] = default
            elif not isinstance(val, int):
                config[key] = default
    config["__config_version__"] = 3
    return config

_migrate_v2_to_v3._version_hints = {"added": [], "modified": ["retry_count", "max_workers"]}


def _migrate_v3_to_v4(config: dict[str, Any]) -> dict[str, Any]:
    """Fill in newly-introduced fields with safe defaults (v3 -> v4).

    New fields only written when the key does **not** already exist, preserving
    user-set values from manual edits or forward-compatible configs.

    New fields:
        - ``enable_debug``: bool, default ``False``
        - ``log_level``: str, default ``"INFO"``
        - ``feature_flags``: dict, default ``{}``
    """
    defaults = {
        "enable_debug": False,
        "log_level": "INFO",
        "feature_flags": {},
    }
    for key, default_val in defaults.items():
        config.setdefault(key, default_val)
    config["__config_version__"] = 4
    return config

_migrate_v3_to_v4._version_hints = {"added": ["enable_debug", "log_level", "feature_flags"]}


def create_default_migrator(
    save_callback: Callable[[dict[str, Any], int], None] | None = None,
) -> ConfigMigrator:
    """Factory: build a :class:`ConfigMigrator` pre-loaded with built-in rules.

    This registers the three example migrations (v1->v2, v2->v3, v3->v4)
    so callers get a ready-to-use instance without manually calling
    :meth:`ConfigMigrator.register_version` for each step.

    Args:
        save_callback: Optional persistence hook forwarded to the constructor.

    Returns:
        A :class:`ConfigMigrator` instance with v1..v4 migrations registered.
    """
    migrator = ConfigMigrator(save_callback=save_callback)
    migrator.register_version(2, _migrate_v1_to_v2)
    migrator.register_version(3, _migrate_v2_to_v3)
    migrator.register_version(4, _migrate_v3_to_v4)
    return migrator
