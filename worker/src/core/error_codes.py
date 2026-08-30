"""Agent-side node error codes (P0-3 fix, 2026-07-27).

之前 fail_result 的 error_code 默认空字符串, 大量节点调用 fail_result
时不传 error_code, 导致 JSONL structured_logger 的 error_code 字段为空,
AI 诊断时无法按错误类型分类 (只能解析 error_msg 字符串, 脆弱且不可靠)。

本模块镜像 backend/gaf_core/error_codes.py 的 NodeErrorCode 枚举, 让
agent 侧也能引用统一的错误码定义。fail_result 默认 error_code 从 "" 改为
NodeErrorCode.UNKNOWN.value, 保证每个失败结果都有可分类的 error_code。

设计原则:
- 与 backend NodeErrorCode 保持同步 (同名字段), 跨进程一致
- StrEnum: json.dumps 直接输出字符串值, 无需 .value 转换
- 仅枚举 "AI 诊断关心的" 错误类别, 不覆盖所有异常

同步规则: 修改本文件时同步修改 backend/gaf_core/error_codes.py (反之亦然)。
"""

from __future__ import annotations

from enum import StrEnum


class NodeErrorCode(StrEnum):
    """节点级错误码 (agent 侧镜像, 与 backend/gaf_core/error_codes.py 同步)。

    用于 AutoResult.error_code 和 JSONL structured_logger 的 error_code 字段,
    让 AI 诊断时能按错误类型分类 (而非解析 error_msg 字符串)。

    分类 (按节点行为):
    - 识别类: NO_MATCH / LOW_CONFIDENCE / OCR_EMPTY
    - 竞态类: SCREEN_UNCHANGED / SCREEN_TIMEOUT
    - 设备类: DEVICE_ERROR / DEVICE_DISCONNECTED
    - 输入类: COORD_INVALID / TARGET_NOT_FOUND
    - 验证类: PRE_VERIFY_FAILED / POST_VERIFY_FAILED
    - 通用: UNKNOWN
    """

    # 识别类 (template_match / feature_match / ocr / color_detect)
    NO_MATCH = "NO_MATCH"                # 模板/特征匹配未找到
    LOW_CONFIDENCE = "LOW_CONFIDENCE"    # 置信度低于阈值
    OCR_EMPTY = "OCR_EMPTY"              # OCR 未识别到任何文字
    COLOR_NOT_FOUND = "COLOR_NOT_FOUND"  # 颜色检测未找到目标颜色

    # 竞态类 (ClickNode 防护 + post_verify)
    SCREEN_UNCHANGED = "SCREEN_UNCHANGED"  # 点击后画面未变化 (轻量防护 UNCHANGED)
    SCREEN_TIMEOUT = "SCREEN_TIMEOUT"      # 等待画面变化超时 (轻量防护 TIMEOUT)

    # 设备类
    DEVICE_ERROR = "DEVICE_ERROR"              # 设备操作通用错误
    DEVICE_DISCONNECTED = "DEVICE_DISCONNECTED"  # 设备连接断开

    # 输入类 (click / swipe / key_press)
    COORD_INVALID = "COORD_INVALID"        # 坐标解析失败
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"  # target 变量未找到
    PARAM_INVALID = "PARAM_INVALID"        # 参数校验失败 (如 clicks < 1)

    # 验证类
    PRE_VERIFY_FAILED = "PRE_VERIFY_FAILED"    # pre_verify 强验证失败
    POST_VERIFY_FAILED = "POST_VERIFY_FAILED"  # post_verify 强验证失败

    # 超时与中断
    TIMEOUT = "TIMEOUT"            # 节点执行超时
    INTERRUPTED = "INTERRUPTED"    # 被外部中断

    # 通用
    UNKNOWN = "UNKNOWN"  # 未分类错误 (默认, fail_result 兜底)


def normalize_error_code(error_code: str | NodeErrorCode | None) -> str:
    """归一化 error_code 为非空字符串。

    - None / "" → NodeErrorCode.UNKNOWN.value (保证 AI 可分类)
    - NodeErrorCode → .value (StrEnum 已是字符串, str() 也行)
    - str → 原样返回

    Args:
        error_code: 原始 error_code (可能为 None / 空串 / StrEnum / str).

    Returns:
        非空错误码字符串 (至少为 "UNKNOWN")。
    """
    if not error_code:
        return NodeErrorCode.UNKNOWN.value
    return str(error_code)
