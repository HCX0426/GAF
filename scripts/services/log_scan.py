"""日志报错行扫描核心 — 单一权威源 (spec 2026-08-29-services-management-monitor P2 归一化).

scripts/services/health.py (daemon 健康快照计数) 与 backend/gaf_core/log_files.py
(服务日志检索层/仅报错过滤) 必须共用同一套报错模式、噪声排除与行分类,
禁止在任一使用方另行复制 — 双套漂移 (此前靠注释"保持一致"维护) 曾导致
前端 error_boundary 上报行被计入服务健康报错 (2026-08-29).

本模块纯标准库, 无 Django/网络依赖, 可被脚本与后台进程安全引用.
"""

from __future__ import annotations

import re
from datetime import datetime

# 报错行匹配 (语义权威源): logging 级别 / Traceback / Python 异常冒号式
ERROR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(ERROR|CRITICAL|FATAL)\b"),
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"(?:Exception|Error)[:(]"),
)

# 连接级噪音: 客户端断连/取消 (ECONNRESET/ECONNABORTED/EPIPE/WinError 10053/10054)
# 是正常网络现象, 不是服务故障, 不计入"服务报错" (展示层 filter=error 仍可见).
# 前端自动上报噪声: 前端错误边界 ([error_boundary] 视图) 把浏览器运行时错误
# (开发期 HMR 窗口瞬时未定义引用等) 落到后端日志, 非 web 服务故障 — 前端
# 运行时问题已在 console 捕获/前端错误上报链路独立追踪, 不污染服务健康.
NOISE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ECONNRESET|ECONNABORTED|EPIPEBROKEN|BrokenPipe"),
    re.compile(r"WinError\s+1005[34]"),
    re.compile(r"\[error_boundary\]"),
    re.compile(r"ReferenceError:.*is not defined"),
)


def is_error_line(line: str) -> bool:
    """判断一行是否为报错行 (基于 ERROR_PATTERNS, 先排除 NOISE_PATTERNS 噪音)."""
    if any(p.search(line) for p in NOISE_PATTERNS):
        return False
    return any(p.search(line) for p in ERROR_PATTERNS)


# 常见日志行首时间戳格式: "2026-08-29 10:25:16[...]" / "[2026-08-29 01:02:33]" /
# "10:25:16" (无日期, 视为当天)
_LINE_TS_RE = re.compile(
    r"^\[?\s*(?:(?P<date>\d{4}-\d{2}-\d{2})\s+)?(?P<time>\d{2}:\d{2}:\d{2})"
)


def parse_line_ts(line: str) -> float | None:
    """解析日志行首时间戳为 epoch 秒; 解析失败返回 None. 仅支持完整/当日时间."""
    m = _LINE_TS_RE.match(line)
    if not m:
        return None
    date_part = m.group("date") or datetime.now().strftime("%Y-%m-%d")
    try:
        return datetime.strptime(f"{date_part} {m.group('time')}", "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return None
