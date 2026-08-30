"""自定义异常体系"""


class AutoBaseError(Exception):
    """自动化基础异常"""

    def __init__(self, message: str = "", *args, **kwargs):
        self.message = message
        super().__init__(message, *args, **kwargs)

    def __str__(self) -> str:
        return self.message or self.__class__.__name__


class DeviceError(AutoBaseError):
    """设备操作异常：连接失败、设备不可用等"""
    pass


class VerifyError(AutoBaseError):
    """验证异常：前置/后置验证失败"""
    pass


class CoordinateError(AutoBaseError):
    """坐标异常：坐标越界、转换失败等"""
    pass


class StepExecuteError(AutoBaseError):
    """步骤执行异常：步骤执行失败"""
    pass


# ------------------------------------------------------------------
# N191 §10.10 决策点 4 C (AI 可调试性, 2026-07-27):
# transformer 缺失/失败时 fail fast, 报错必带 4 类归因字段, 让 AI 能
# 直接判断根因类别 (config/code/data/device), 不需要从头排查。
# 4 条 AI 可调试性总原则之 2: 报错必归因。
# ------------------------------------------------------------------
class CoordTransformerError(AutoBaseError):
    """坐标 transformer 构建失败/缺失异常 (N191 §10.10 决策点 4 C)。

    当 task_definition.base_resolution 已配置但 transformer 构建失败时抛出。
    base_resolution 未填 (legacy 任务) 不抛本异常, 正常走 legacy 路径。

    Attributes:
        root_cause_category: 根因类别, 取值:
            - ``"config"``: 配置错误 (base_resolution 格式错 / 字段缺失)
            - ``"code"``: 代码 bug (transformer 构造函数异常)
            - ``"data"``: 数据问题 (base_resolution 与 device 分辨率不合法)
            - ``"device"``: 设备问题 (device.get_resolution 失败 / hwnd 缺失)
        missing_field: 缺失字段名 (config 类别时填, 如 "base_resolution")
        task_id: 任务 ID (可选, 用于跨任务关联)
        device_id: 设备 ID (可选, 用于跨设备对比)
        base_resolution: 用户配置的 base_resolution (用于诊断)
        device_resolution: 设备实际分辨率 (device 类别时填)
    """

    def __init__(
        self,
        message: str,
        *,
        root_cause_category: str = "code",
        missing_field: str = "",
        task_id: str = "",
        device_id: str = "",
        base_resolution: str = "",
        device_resolution: str = "",
    ) -> None:
        self.root_cause_category = root_cause_category
        self.missing_field = missing_field
        self.task_id = task_id
        self.device_id = device_id
        self.base_resolution = base_resolution
        self.device_resolution = device_resolution
        # 把归因信息拼到 message 里, 让 str(exception) 也带完整诊断。
        enriched_msg = (
            f"{message} | root_cause={root_cause_category}"
            f" | missing_field={missing_field or 'N/A'}"
            f" | base_resolution={base_resolution or 'N/A'}"
            f" | device_resolution={device_resolution or 'N/A'}"
            f" | task_id={task_id or 'N/A'}"
            f" | device_id={device_id or 'N/A'}"
        )
        super().__init__(enriched_msg)

    def to_dict(self) -> dict[str, str]:
        """返回结构化归因字典, 供 structured_logger 写入 JSONL。"""
        return {
            "error_type": "CoordTransformerError",
            "root_cause_category": self.root_cause_category,
            "missing_field": self.missing_field,
            "task_id": self.task_id,
            "device_id": self.device_id,
            "base_resolution": self.base_resolution,
            "device_resolution": self.device_resolution,
            "message": self.message,
        }
