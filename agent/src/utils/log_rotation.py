"""DateRotatingFileHandler — 按日期分桶的日志轮转处理器.

Writes logs to ``<debug_root>/<YYYYMMDD>/<app>/system/<log_name>.log``.
At midnight, compresses the previous day's file with gzip and creates
a new file in the new date directory. Automatically cleans up date
directories older than *retention_days*.

Usage::

    handler = DateRotatingFileHandler(
        debug_root="/path/to/debug",
        app_name="agent",       # agent → debug/YYYYMMDD/agent/system/
        log_name="agent",       # file → agent.log
        retention_days=30,
    )
    logger.addHandler(handler)
"""

import gzip
import logging
import os
import shutil
from datetime import datetime, timedelta


class DateRotatingFileHandler(logging.Handler):
    """按日期分桶的日志轮转 Handler.

    Directory layout::

        <debug_root>/
        ├── 20260809/
        │   └── agent/
        │       └── system/
        │           └── agent.log          # current day, plain text
        ├── 20260808/
        │   └── agent/
        │       └── system/
        │           └── agent.log.gz       # previous days, gzip'd
        └── ...

    Rotation triggers automatically when the calendar date changes.
    """

    def __init__(
        self,
        debug_root: str,
        app_name: str,
        log_name: str,
        retention_days: int = 30,
        encoding: str = "utf-8",
    ):
        """初始化.

        Args:
            debug_root: debug 根目录 (如 ``/path/to/debug``)
            app_name:   应用名, 决定子目录层级 (``agent`` → ``agent/system/``,
                        ``backend`` → ``backend/system/``)
            log_name:   日志文件名 (不带扩展名, 如 ``agent`` / ``daemon``)
            retention_days: 保留天数, 过期日期目录自动删除
            encoding:   文件编码
        """
        super().__init__()
        self._debug_root = os.path.abspath(debug_root)
        self._app_name = app_name
        self._log_name = log_name
        self._retention_days = retention_days
        self._encoding = encoding
        self._current_date: str | None = None
        self._stream = None
        self._current_log_path: str | None = None
        self.terminator = "\n"
        self._open_today()

    # ------------------------------------------------------------------
    # 文件管理
    # ------------------------------------------------------------------

    def _open_today(self) -> None:
        """打开当天的日志文件, 创建目录 (如不存在)."""
        today = datetime.now().strftime("%Y%m%d")
        log_dir = os.path.join(
            self._debug_root, today, self._app_name, "system",
        )
        os.makedirs(log_dir, exist_ok=True)
        self._current_log_path = os.path.join(log_dir, f"{self._log_name}.log")
        self._stream = open(self._current_log_path, "a", encoding=self._encoding)  # noqa: SIM115 - long-lived self._stream held across writes, closed in close()
        self._current_date = today

    def _rotate_if_needed(self) -> None:
        """如果日期变了则执行轮转: 压缩旧文件 → 创建新文件 → 清理过期."""
        today = datetime.now().strftime("%Y%m%d")
        if today == self._current_date:
            return

        # 1. Flush & close old file
        if self._stream:
            self._stream.flush()
            self._stream.close()
            self._stream = None

        # 2. Compress old file → .gz
        if self._current_log_path and os.path.exists(self._current_log_path):
            gz_path = self._current_log_path + ".gz"
            with open(self._current_log_path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            os.remove(self._current_log_path)

        # 3. Open new file for today
        self._open_today()

        # 4. Cleanup old date directories
        self._cleanup_old_dirs()

    def _cleanup_old_dirs(self) -> None:
        """删除超过保留期的日期目录."""
        cutoff = datetime.now() - timedelta(days=self._retention_days)
        if not os.path.isdir(self._debug_root):
            return
        for entry in os.listdir(self._debug_root):
            entry_path = os.path.join(self._debug_root, entry)
            if not os.path.isdir(entry_path):
                continue
            try:
                dir_date = datetime.strptime(entry, "%Y%m%d")
            except ValueError:
                continue
            if dir_date < cutoff:
                shutil.rmtree(entry_path, ignore_errors=True)

    # ------------------------------------------------------------------
    # logging.Handler interface
    # ------------------------------------------------------------------

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._rotate_if_needed()
            msg = self.format(record)
            self._stream.write(msg + self.terminator)
            self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        if self._stream:
            self._stream.flush()
            self._stream.close()
            self._stream = None
        super().close()
