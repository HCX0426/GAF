"""TD-415 regression: DateRotatingFileHandler 跨天轮转自愈.

- 旧文件不存在时压缩抛出 OSError 不得中断轮转 (必须仍打开新文件)
- emit 后 _stream 必须可用 (不置 None)
- 轮转后新日志写入新文件 (不丢日志)
"""

from __future__ import annotations

import logging
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from utils.log_rotation import DateRotatingFileHandler


def _make_handler(tmp: str) -> DateRotatingFileHandler:
    return DateRotatingFileHandler(
        debug_root=tmp,
        app_name="test-app",
        log_name="test",
        retention_days=7,
    )


def test_rotation_self_heal_when_old_file_missing() -> None:
    """旧文件不存在 (压缩抛 OSError) → 仍打开新文件且后续日志可写."""
    with tempfile.TemporaryDirectory() as tmp:
        handler = _make_handler(tmp)
        try:
            # 模拟"昨天"文件: 把 handler 当前日期拨到昨天, 且不造旧文件
            yesterday = datetime.now().strftime("%Y%m%d")
            # 让 handler 认为今天是昨天 → 下一次 emit 触发轮转
            day_dir = Path(tmp) / yesterday / "test-app" / "system"
            day_dir.mkdir(parents=True, exist_ok=True)
            handler._current_date = "19700101"  # 强制"昨天"是 1970-01-01
            handler._current_log_path = str(day_dir / "missing-old.log")  # 文件不存在

            logger = logging.getLogger("td415_test")
            logger.setLevel(logging.DEBUG)
            logger.handlers = [handler]
            logger.info("hello after rotation")
            # 必须成功写入当天文件
            today = datetime.now().strftime("%Y%m%d")
            today_file = Path(tmp) / today / "test-app" / "system" / "test.log"
            assert today_file.exists(), "轮转后未打开新文件"
            content = today_file.read_text(encoding="utf-8")
            assert "hello after rotation" in content
            assert handler._stream is not None
        finally:
            handler.close()


def test_emit_rebuilds_stream_after_close() -> None:
    """stream 被置 None (如 close 误用) 后, emit 能自愈重建并写入."""
    with tempfile.TemporaryDirectory() as tmp:
        handler = _make_handler(tmp)
        try:
            handler.close()  # close() 会把 _stream 置 None
            logger = logging.getLogger("td415_reopen")
            logger.setLevel(logging.DEBUG)
            logger.handlers = [handler]
            logger.info("after close self-heal")
            today = datetime.now().strftime("%Y%m%d")
            today_file = Path(tmp) / today / "test-app" / "system" / "test.log"
            assert today_file.exists()
            assert "after close self-heal" in today_file.read_text(encoding="utf-8")
        finally:
            handler.close()