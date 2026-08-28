"""Celery tasks for the core app.

Hosts periodic cleanup tasks:

- ``cleanup_old_archives`` (spec §8.3) — scans
  ``settings.DEBUG_ARCHIVE_DIR`` for ``*.tar.gz`` files older than
  ``DEBUG_ARCHIVE_RETENTION_DAYS`` (default 30 days) and unlinks them.
  Also scans ``<DEBUG_DIR>/structured/`` for ``*.jsonl`` files older
  than the same retention (N190, 2026-07-26 — without this, structured
  JSONL logs grow monotonically since pack_logs doesn't include them
  in the tar.gz archive). Without this, per-execution debug artifacts
  grow monotonically.

.. note::

    ``cleanup_old_logs`` (LogEntry 清理) 已移除 — LogEntry 表为真只读
    (F12, 2026-07-31). 不再写入/删除, 保留只读查询.
"""
import logging
from datetime import datetime, timedelta
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(acks_late=True, max_retries=3, retry_backoff=60)
def cleanup_old_archives():
    """Delete tar.gz archives + 过期的归一化执行目录 older than retention.

    N194 归一化 + 嵌套结构 (2026-07-29): scans two locations:

    1. ``settings.DEBUG_ARCHIVE_DIR`` 下递归扫 ``**/*.tar.gz`` (嵌套结构
       ``<archive_dir>/<YYYYMMDD>/<pipeline>/<exec_id>.tar.gz`` + 旧扁平
       ``<archive_dir>/<exec_id>.tar.gz`` 兼容). 按 mtime 过期删除, 删除后
       若日期/pipeline 目录为空则一并清理.
    2. ``<DEBUG_DIR>/`` 下递归扫嵌套结构
       ``<YYYYMMDD>/<pipeline>/<HHMMSS_suffix>/`` + 旧扁平
       ``<YYYYMMDD_HHMMSS>_<name>_<suffix>/``. 按 mtime 过期删除整个 exec_dir,
       删除后若日期/pipeline 目录为空则一并清理.

    Runs daily via celery beat. Returns summary dict for observability.
    """
    import re
    import shutil

    archive_dir = getattr(settings, 'DEBUG_ARCHIVE_DIR', None)
    debug_dir = getattr(settings, 'DEBUG_DIR', None)
    if not archive_dir and not debug_dir:
        logger.warning(
            'cleanup_old_archives: DEBUG_ARCHIVE_DIR 和 DEBUG_DIR 均未配置, 跳过清理',
        )
        return {
            'deleted_count': 0, 'exec_dirs_deleted': 0,
            'skipped': 'both DEBUG_ARCHIVE_DIR and DEBUG_DIR unset',
        }

    retention_days = int(getattr(
        settings, 'DEBUG_ARCHIVE_RETENTION_DAYS', 30,
    ))
    cutoff = timezone.now() - timedelta(days=retention_days)
    cutoff_ts = cutoff.timestamp()

    deleted_count = 0
    exec_dirs_deleted = 0
    error_count = 0

    date_pattern = re.compile(r'^\d{8}$')        # YYYYMMDD
    exec_pattern = re.compile(r'^\d{6}_')        # HHMMSS_<suffix>
    legacy_pattern = re.compile(r'^\d{8}_\d{6}_')  # 旧扁平 YYYYMMDD_HHMMSS_*

    def _try_rmtree_if_empty(path: Path) -> None:
        """删除空目录 (pipeline 目录 / 日期目录), 避免留下空壳."""
        try:
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
                logger.debug(
                    'cleanup_old_archives: 已清理空目录 %s', path,
                )
        except OSError:
            pass  # 非空或并发写入, 忽略

    # --- 1. Sweep tar.gz archives under DEBUG_ARCHIVE_DIR (嵌套 + 扁平兼容) ---
    if archive_dir:
        archive_path = Path(archive_dir)
        if archive_path.is_dir():
            # 递归扫所有 .tar.gz (嵌套 + 扁平都覆盖)
            for entry in archive_path.rglob('*.tar.gz'):
                try:
                    mtime = entry.stat().st_mtime
                    if mtime < cutoff_ts:
                        entry.unlink()
                        deleted_count += 1
                        logger.info(
                            'cleanup_old_archives: 已删除过期归档 %s (mtime=%s)',
                            entry, mtime,
                        )
                        # 清理空的父目录 (pipeline 目录 → 日期目录)
                        _try_rmtree_if_empty(entry.parent)
                        _try_rmtree_if_empty(entry.parent.parent)
                except OSError as exc:
                    error_count += 1
                    logger.warning(
                        'cleanup_old_archives: 删除归档失败 %s: %s',
                        entry, exc,
                    )
        else:
            logger.warning(
                'cleanup_old_archives: 归档目录不存在: %s', archive_dir,
            )

    # --- 2. Sweep 归一化 exec_dir under <DEBUG_DIR>/ (嵌套 + 扁平兼容) ---
    if debug_dir:
        debug_root = Path(debug_dir)
        if debug_root.is_dir():
            for entry in debug_root.iterdir():
                if not entry.is_dir():
                    continue
                # Skip special dirs: _global (catch-all logs), archives (tar.gz)
                if entry.name in ('_global', 'archives'):
                    continue

                # --- 2a. 新嵌套格式: <DEBUG_DIR>/<YYYYMMDD>/<pipeline>/<HHMMSS_suffix>/ ---
                if date_pattern.match(entry.name):
                    date_dir = entry
                    for pipeline_entry in date_dir.iterdir():
                        if not pipeline_entry.is_dir():
                            continue
                        pipeline_dir = pipeline_entry
                        for exec_entry in pipeline_dir.iterdir():
                            if not exec_entry.is_dir():
                                continue
                            if not exec_pattern.match(exec_entry.name):
                                continue
                            try:
                                mtime = exec_entry.stat().st_mtime
                                if mtime < cutoff_ts:
                                    shutil.rmtree(exec_entry)
                                    exec_dirs_deleted += 1
                                    logger.info(
                                        'cleanup_old_archives: 已删除过期执行目录 %s (mtime=%s)',
                                        exec_entry, mtime,
                                    )
                            except OSError as exc:
                                error_count += 1
                                logger.warning(
                                    'cleanup_old_archives: 删除执行目录失败 %s: %s',
                                    exec_entry, exc,
                                )
                        # 清理空的 pipeline 目录
                        _try_rmtree_if_empty(pipeline_dir)
                    # 清理空的日期目录
                    _try_rmtree_if_empty(date_dir)

                # --- 2b. 旧扁平格式兼容: <DEBUG_DIR>/<YYYYMMDD_HHMMSS>_<name>_<suffix>/ ---
                elif legacy_pattern.match(entry.name):
                    try:
                        mtime = entry.stat().st_mtime
                        if mtime < cutoff_ts:
                            shutil.rmtree(entry)
                            exec_dirs_deleted += 1
                            logger.info(
                                'cleanup_old_archives: 已删除过期执行目录(旧扁平) %s (mtime=%s)',
                                entry.name, mtime,
                            )
                    except OSError as exc:
                        error_count += 1
                        logger.warning(
                            'cleanup_old_archives: 删除执行目录失败 %s: %s',
                            entry.name, exc,
                        )

            # --- 2c. Legacy structured/ directory (exec-*.jsonl, pre-N194 产物) ---
            structured_dir = debug_root / 'structured'
            if structured_dir.is_dir():
                for jsonl_file in structured_dir.glob('exec-*.jsonl'):
                    try:
                        mtime = jsonl_file.stat().st_mtime
                        if mtime < cutoff_ts:
                            jsonl_file.unlink()
                            exec_dirs_deleted += 1
                            logger.info(
                                'cleanup_old_archives: 已删除 legacy structured 文件 %s (mtime=%s)',
                                jsonl_file.name, mtime,
                            )
                    except OSError as exc:
                        error_count += 1
                        logger.warning(
                            'cleanup_old_archives: 删除 legacy structured 文件失败 %s: %s',
                            jsonl_file.name, exc,
                        )
                _try_rmtree_if_empty(structured_dir)

            # --- 2d. Flat log files at debug root (pre-N197 产物, 已迁移到日期目录) ---
            for flat_log_name in ('agent.log', 'daemon.log'):
                flat_log = debug_root / flat_log_name
                if flat_log.is_file():
                    try:
                        mtime = flat_log.stat().st_mtime
                        if mtime < cutoff_ts:
                            flat_log.unlink()
                            deleted_count += 1
                            logger.info(
                                'cleanup_old_archives: 已删除过期扁平日志 %s (mtime=%s)',
                                flat_log_name, mtime,
                            )
                    except OSError as exc:
                        error_count += 1
                        logger.warning(
                            'cleanup_old_archives: 删除扁平日志失败 %s: %s',
                            flat_log_name, exc,
                        )

            # --- 2e. 过期日期目录整体清理 (N197, 2026-08-09) ---
            # 上面的 2a/2b 清理了 exec_dir, 但留下了 system 级日志
            # (agent/system/, backend/system/, backend/tasks/ 等).
            # 如果整个日期目录已超过保留期, 直接删除整个目录 (含所有子目录).
            for entry in debug_root.iterdir():
                if not entry.is_dir():
                    continue
                if not date_pattern.match(entry.name):
                    continue
                # 跳过今天的日期目录 (防止误删正在写入的日志)
                today_str = datetime.now().strftime('%Y%m%d')
                if entry.name >= today_str:
                    continue
                # 用目录内最新 mtime 作为判断依据
                try:
                    latest_mtime = max(
                        (f.stat().st_mtime for f in entry.rglob('*') if f.is_file()),
                        default=entry.stat().st_mtime,
                    )
                    if latest_mtime < cutoff_ts:
                        shutil.rmtree(entry)
                        exec_dirs_deleted += 1
                        logger.info(
                            'cleanup_old_archives: 已删除过期日期目录 %s (latest_mtime=%s)',
                            entry.name, latest_mtime,
                        )
                except (OSError, ValueError) as exc:
                    error_count += 1
                    logger.warning(
                        'cleanup_old_archives: 删除日期目录失败 %s: %s',
                        entry.name, exc,
                    )

    logger.info(
        'cleanup_old_archives: 完成, 删除 %d 个过期归档 + %d 个过期执行目录 '
        '(retention=%d days, archive_dir=%s, debug_dir=%s)',
        deleted_count, exec_dirs_deleted, retention_days, archive_dir, debug_dir,
    )

    return {
        'deleted_count': deleted_count,
        'exec_dirs_deleted': exec_dirs_deleted,
        'error_count': error_count,
        'retention_days': retention_days,
        'cutoff': cutoff.isoformat(),
        'archive_dir': archive_dir,
        'debug_dir': debug_dir,
    }


# 定时备份: 保存在服务器 MEDIA_ROOT/backups/ 的压缩快照数上限 (超出删除最旧).
BACKUP_RETENTION_COUNT = 7


@shared_task(acks_late=True, max_retries=3, retry_backoff=60)
def scheduled_backup():
    """每天定时创建全量备份快照并存盘 (MEDIA_ROOT/backups/).

    复用与 ``tasks.backup_views.create_backup`` 相同的 dumpdata + ZIP 逻辑,
    但输出到服务器本地目录而不是作为 HTTP 附件返回, 便于无人值守自动备份.

    - 快照文件: ``<MEDIA_ROOT>/backups/gaf_backup_<tag>.zip``
      (tag = YYYYMMDD_HHMMSS, 与手动备份命名风格一致)
    - 保留策略: 最多保留 ``BACKUP_RETENTION_COUNT`` 份, 超出按 mtime 删除最旧.
    - 由 Celery Beat / APScheduler (config/celery.py beat_schedule) 每日触发.

    Returns summary dict for observability (Celery eager/dev 模式也会执行).
    """
    import json as _json
    import shutil as _shutil
    import tempfile as _tempfile
    import zipfile as _zipfile
    from datetime import datetime as _datetime

    from django.core.management import call_command

    backups_dir = Path(settings.MEDIA_ROOT) / 'backups'
    backups_dir.mkdir(parents=True, exist_ok=True)

    tag = _datetime.now().strftime('%Y%m%d_%H%M%S')
    tmp_dir = Path(
        _tempfile.mkdtemp(prefix='gaf_scheduled_backup_'),
    )
    try:
        db_file = tmp_dir / 'database.json'
        with db_file.open('w') as f:
            call_command('dumpdata', '--exclude=contenttypes', '--exclude=auth.permission', stdout=f)

        summary = {
            'created_at': timezone.now().isoformat(),
            'tag': tag,
            'type': 'scheduled',
            'db_engine': settings.DATABASES['default']['ENGINE'],
        }
        summary_file = tmp_dir / 'backup_info.json'
        with summary_file.open('w') as f:
            _json.dump(summary, f, indent=2, ensure_ascii=False)

        snapshot = backups_dir / f'gaf_backup_{tag}.zip'
        with _zipfile.ZipFile(snapshot, 'w', _zipfile.ZIP_DEFLATED) as zf:
            for entry in tmp_dir.iterdir():
                zf.write(entry, entry.name)

        # Retention: keep only the newest N snapshots, delete the rest.
        existing = sorted(backups_dir.glob('gaf_backup_*.zip'), key=lambda p: p.stat().st_mtime)
        removed = 0
        while len(existing) > BACKUP_RETENTION_COUNT:
            oldest = existing.pop(0)
            try:
                oldest.unlink()
                removed += 1
            except OSError as exc:
                logger.warning('scheduled_backup: 删除旧快照失败 %s: %s', oldest, exc)

        logger.info(
            'scheduled_backup: 快照完成 %s (retention=%d, removed=%d)',
            snapshot, BACKUP_RETENTION_COUNT, removed,
        )
        return {
            'snapshot': str(snapshot),
            'tag': tag,
            'size_bytes': snapshot.stat().st_size,
            'removed_old': removed,
            'retention': BACKUP_RETENTION_COUNT,
        }
    except Exception:
        logger.exception('scheduled_backup failed for tag=%s', tag)
        raise
    finally:
        _shutil.rmtree(tmp_dir, ignore_errors=True)
