"""4-digit business error codes for the GAF API.

The code space is divided by functional area so callers can quickly identify
whether an error is generic, auth-related, business-specific, rate-limited,
or caused by a third-party integration.
"""

from enum import IntEnum, StrEnum


class ErrorCode(IntEnum):
    """Canonical error codes returned in `{ code, message, data }` responses."""

    # 0xxx — Success
    SUCCESS = 0

    # 1xxx — Generic / platform errors
    INTERNAL_ERROR = 1000
    INVALID_PARAMS = 1001
    NOT_FOUND = 1002
    PERMISSION_DENIED = 1003
    METHOD_NOT_ALLOWED = 1004

    # 2xxx — Authentication / authorization
    UNAUTHORIZED = 2001
    TOKEN_EXPIRED = 2002
    TOKEN_INVALID = 2003
    API_KEY_MISSING = 2010
    API_KEY_INVALID = 2011

    # 3xxx — Business errors
    DEVICE_OFFLINE = 3001
    TASK_CONFLICT = 3002
    RESOURCE_PACK_NOT_ENABLED = 3010
    QUOTA_EXCEEDED = 3050

    # 4xxx — Rate limiting / circuit breaker
    RATE_LIMITED = 4001
    QUOTA_EXHAUSTED = 4002

    # 5xxx — Third-party integration errors
    LLM_UNAVAILABLE = 5001
    ADB_FAILED = 5010


class NodeErrorCode(StrEnum):
    """节点级错误码（spec 阶段 5 — 任务 1.8）。

    用于 AutoResult.error_code 和 JSONL structured_logger 的 error_code 字段，
    让 AI 诊断时能按错误类型分类（而非解析 error_msg 字符串）。

    设计原则：
    - 字符串枚举（StrEnum），json.dumps 直接输出字符串值
    - 名称即错误码，不附数字（与 ErrorCode IntEnum 区分用途）
    - 仅枚举"AI 诊断关心的"错误类别，不覆盖所有异常

    分类（按节点行为）：
    - 识别类：NO_MATCH / LOW_CONFIDENCE / OCR_EMPTY
    - 竞态类：SCREEN_UNCHANGED / SCREEN_TIMEOUT
    - 设备类：DEVICE_ERROR / DEVICE_DISCONNECTED
    - 输入类：COORD_INVALID / TARGET_NOT_FOUND
    - 验证类：PRE_VERIFY_FAILED / POST_VERIFY_FAILED
    - 通用：UNKNOWN
    """

    # 识别类（template_match / feature_match / ocr / color_detect）
    NO_MATCH = "NO_MATCH"                # 模板/特征匹配未找到
    LOW_CONFIDENCE = "LOW_CONFIDENCE"    # 置信度低于阈值
    OCR_EMPTY = "OCR_EMPTY"              # OCR 未识别到任何文字
    COLOR_NOT_FOUND = "COLOR_NOT_FOUND"  # 颜色检测未找到目标颜色

    # 竞态类（ClickNode 防护 + post_verify）
    SCREEN_UNCHANGED = "SCREEN_UNCHANGED"  # 点击后画面未变化（轻量防护 UNCHANGED）
    SCREEN_TIMEOUT = "SCREEN_TIMEOUT"      # 等待画面变化超时（轻量防护 TIMEOUT）

    # 设备类
    DEVICE_ERROR = "DEVICE_ERROR"              # 设备操作通用错误
    DEVICE_DISCONNECTED = "DEVICE_DISCONNECTED"  # 设备连接断开

    # 输入类（click / swipe / key_press）
    COORD_INVALID = "COORD_INVALID"        # 坐标解析失败
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"  # target 变量未找到
    PARAM_INVALID = "PARAM_INVALID"        # 参数校验失败（如 clicks < 1）

    # 验证类
    PRE_VERIFY_FAILED = "PRE_VERIFY_FAILED"      # pre_verify 强验证失败
    POST_VERIFY_FAILED = "POST_VERIFY_FAILED"  # post_verify 强验证失败

    # 超时与中断
    TIMEOUT = "TIMEOUT"            # 节点执行超时
    INTERRUPTED = "INTERRUPTED"    # 被外部中断

    # 通用
    UNKNOWN = "UNKNOWN"  # 未分类错误（默认）
