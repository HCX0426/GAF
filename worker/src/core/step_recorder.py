"""执行步骤记录器
每步执行完成后将步骤记录（截图路径、识别结果、耗时）上报到 Server

N196: api_base_url 从 server_url 推导，避免硬编码 localhost:8000。
"""
import logging
import os
import time
from dataclasses import dataclass, field
from urllib import parse as urllib_parse

from engine.context import StepState

logger = logging.getLogger(__name__)


def _derive_http_base(server_url: str) -> str:
    """从 WebSocket server_url 推导 HTTP base URL。"""
    if not server_url:
        return "http://127.0.0.1:8000"
    parsed = urllib_parse.urlparse(server_url)
    scheme = "https" if parsed.scheme == "wss" else "http"
    if not parsed.hostname:
        return "http://127.0.0.1:8000"
    if parsed.port:
        return f"{scheme}://{parsed.hostname}:{parsed.port}"
    return f"{scheme}://{parsed.hostname}"


@dataclass
class StepRecord:
    """单步执行记录数据结构"""

    step_index: int
    node_id: str = ""
    node_type: str = ""
    node_name: str = ""
    status: str = "pending"
    screenshot_path: str = ""
    recognition_result: dict = field(default_factory=dict)
    error_message: str = ""
    started_at: float | None = None
    completed_at: float | None = None

    @property
    def duration(self) -> float:
        """计算步骤执行耗时（毫秒）"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at) * 1000
        return 0.0

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            'step_index': self.step_index,
            'node_id': self.node_id,
            'node_type': self.node_type,
            'node_name': self.node_name,
            'status': self.status,
            'screenshot_path': self.screenshot_path,
            'recognition_result': self.recognition_result,
            'error_message': self.error_message,
            'duration': self.duration,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
        }


class StepRecorder:
    """执行步骤记录器，收集并上报步骤执行数据"""

    def __init__(self, execution_id: str, server_url: str = ""):
        """初始化步骤记录器

        Args:
            execution_id: 执行ID
            server_url: Agent 的 WebSocket server_url，
                用于推导 HTTP base URL。为空时使用环境变量 GAF_SERVER_URL
                或默认值。
        """
        if not server_url:
            ws_path = os.environ.get("GAF_WS_AGENT_PATH", "ws/protocol/agents/")
            server_url = os.environ.get("GAF_SERVER_URL", f"ws://127.0.0.1:8000/{ws_path}")
        http_base = _derive_http_base(server_url)
        api_prefix = os.environ.get("GAF_API_PREFIX", "api/v2")
        self.api_base_url = f"{http_base}/{api_prefix}"
        self.execution_id = execution_id
        self.steps: list[StepRecord] = []
        self.current_step: StepRecord | None = None

    def start_step(self, step_index: int, node_id: str, node_type: str, node_name: str):
        """开始记录一个新步骤

        Args:
            step_index: 步骤索引
            node_id: 节点ID
            node_type: 节点类型
            node_name: 节点名称
        """
        self.current_step = StepRecord(
            step_index=step_index,
            node_id=node_id,
            node_type=node_type,
            node_name=node_name,
            status="running",
            started_at=time.time(),
        )

    def record_recognition(self, result: dict):
        """记录识别结果

        Args:
            result: 识别结果字典
        """
        if self.current_step:
            self.current_step.recognition_result = result

    def record_screenshot(self, path: str):
        """记录截图路径

        Args:
            path: 截图文件路径
        """
        if self.current_step:
            self.current_step.screenshot_path = path

    def complete_step(self, success: bool = True):
        """完成当前步骤并上报

        Args:
            success: 是否成功

        Returns:
            完成的步骤记录
        """
        if self.current_step:
            self.current_step.completed_at = time.time()
            self.current_step.status = "completed" if success else "failed"
            self.steps.append(self.current_step)
            self._report_step(self.current_step)
            step = self.current_step
            self.current_step = None
            return step
        return None

    def fail_step(self, error: str):
        """标记当前步骤失败并上报

        Args:
            error: 错误信息

        Returns:
            失败的步骤记录
        """
        if self.current_step:
            self.current_step.completed_at = time.time()
            self.current_step.status = "failed"
            self.current_step.error_message = error
            self.steps.append(self.current_step)
            self._report_step(self.current_step)
            step = self.current_step
            self.current_step = None
            return step
        return None

    def skip_step(self, step_index: int):
        """记录一个跳过步骤

        Args:
            step_index: 步骤索引

        Returns:
            跳过的步骤记录
        """
        record = StepRecord(
            step_index=step_index,
            status="skipped",
            completed_at=time.time(),
        )
        self.steps.append(record)
        self._report_step(record)
        return record

    def _report_step(self, step: StepRecord):
        """上报步骤记录到 Server（非阻塞，失败不中断执行）

        Args:
            step: 步骤记录
        """
        try:
            import requests
            url = f"{self.api_base_url}/executions/{self.execution_id}/steps/"
            requests.post(url, json=step.to_dict(), timeout=5)
        except Exception as e:
            logger.warning("上报步骤记录失败: %s", e)

    def get_summary(self) -> dict:
        """获取执行汇总统计

        Returns:
            包含 total_steps, completed, failed, total_duration_ms 的字典
        """
        completed = sum(1 for s in self.steps if s.status == StepState.COMPLETED.value)
        failed = sum(1 for s in self.steps if s.status == StepState.FAILED.value)
        total_duration = sum(s.duration for s in self.steps)
        return {
            'total_steps': len(self.steps),
            'completed': completed,
            'failed': failed,
            'total_duration_ms': total_duration,
        }
