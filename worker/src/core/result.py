"""统一结果类"""

from dataclasses import dataclass
from typing import Any

from core.error_codes import normalize_error_code


@dataclass
class AutoResult:
    """自动化操作统一返回结果

    新增字段（spec 阶段 3.4.2）用于诊断：
    - error_code: 节点级错误码（NodeErrorCode 枚举值字符串），便于 AI 分类
    - node_id: 节点 ID，由 engine 自动填充
    - node_type: 节点类型，由 engine 自动填充
    - structured_log_path: 本次执行的 JSONL 结构化日志绝对路径
      （docs/architecture/agent/chain-mode-structured-logging.md — chain 模式
      也接入 StructuredLogger 后，handler 通过此字段把日志路径回传 backend）。
      空串表示未生成（execute 未执行或 logger 初始化失败）。向后兼容默认空串。
    新字段默认空字符串，向后兼容旧调用代码。

    P0-3 fix (AI 可调试性, 2026-07-27): error_code 现在通过 fail_result
    创建时会被 normalize_error_code 归一化, 空/None 兜底为
    NodeErrorCode.UNKNOWN.value, 保证每个失败结果都有可分类的 error_code
    (JSONL structured_logger 的 error_code 字段不再为空)。
    """
    success: bool
    data: Any = None
    error_msg: str = ""
    error_code: str = ""
    elapsed_time: float = 0.0
    is_interrupted: bool = False
    retry_count: int = 0
    node_id: str = ""
    node_type: str = ""
    structured_log_path: str = ""

    @property
    def failed(self) -> bool:
        """是否失败"""
        return not self.success

    def __bool__(self) -> bool:
        """布尔转换：成功为 True"""
        return self.success


def success_result(data: Any = None, elapsed_time: float = 0.0, retry_count: int = 0) -> AutoResult:
    """创建成功结果"""
    return AutoResult(
        success=True,
        data=data,
        elapsed_time=elapsed_time,
        retry_count=retry_count,
    )


def fail_result(
    error_msg: str = "",
    data: Any = None,
    elapsed_time: float = 0.0,
    is_interrupted: bool = False,
    retry_count: int = 0,
    error_code: str = "",
    node_id: str = "",
    node_type: str = "",
) -> AutoResult:
    """创建失败结果

    P0-3 fix (AI 可调试性, 2026-07-27): error_code 经 normalize_error_code
    归一化, 空/None 兜底为 NodeErrorCode.UNKNOWN.value。调用方不传 error_code
    时不再产生空字符串, 保证 JSONL structured_logger 的 error_code 字段非空,
    AI 可按错误类型分类诊断。

    Args:
        error_code: 节点级错误码 (NodeErrorCode 枚举或字符串)。空/None
            兜底为 "UNKNOWN"。建议调用方传具体枚举值 (如
            NodeErrorCode.NO_MATCH) 让 AI 精确分类。
        node_id: 节点 ID（engine 可自动填充）
        node_type: 节点类型（engine 可自动填充）
    """
    return AutoResult(
        success=False,
        data=data,
        error_msg=error_msg,
        error_code=normalize_error_code(error_code),
        elapsed_time=elapsed_time,
        is_interrupted=is_interrupted,
        retry_count=retry_count,
        node_id=node_id,
        node_type=node_type,
    )
