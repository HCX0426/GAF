"""重试装饰器：通用重试 + 中断检查装饰器

迁移自 BD2-AUTO 的 auto_decorators 模块，适配 GAF 架构：
- 使用 Python 标准 logging 替代自定义 Logger
- 支持通过 stop_event (threading.Event) 进行中断检查
- 支持自定义中断检查回调函数
- 返回 StepResult 统一结果类型
"""

import logging
import threading
import time
from collections.abc import Callable
from functools import wraps

from core.result import AutoResult as StepResult

logger = logging.getLogger(__name__)


def with_retry_and_check(
    max_retries: int = 3,
    retry_interval: float = 1.0,
    check_interrupt: Callable[[], bool] | None = None,
):
    """通用重试 + 前置中断检查装饰器

    执行流程：
    1. 中断检查 → 如果被中断则立即返回失败结果
    2. 执行目标函数 → 成功则返回
    3. 失败则等待 retry_interval 后重试
    4. 重试耗尽后返回最终失败结果

    Args:
        max_retries: 最大重试次数（不含首次执行），默认 3
        retry_interval: 重试间隔时间（秒），默认 1.0
        check_interrupt: 中断检查回调函数，返回 True 表示需要中断，
                         为 None 时使用 OperationHandler.stop_event 检查

    Returns:
        装饰器函数
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs) -> StepResult:
            stop_event: threading.Event | None = getattr(self, "_stop_event", None)
            total_start = time.monotonic()
            last_error = ""
            retry_count = 0

            for attempt in range(max_retries + 1):
                if _should_interrupt(stop_event, check_interrupt):
                    elapsed = time.monotonic() - total_start
                    logger.debug("[%s] 任务被中断", func.__name__)
                    return StepResult.fail(
                        error_msg=f"{func.__name__} 任务被中断",
                        elapsed_time=elapsed,
                        retry_count=retry_count,
                    )

                try:
                    result = func(self, *args, **kwargs)
                    if isinstance(result, StepResult):
                        if result.success:
                            result.retry_count = retry_count
                            return result
                        last_error = result.error_msg
                    elif result:
                        return StepResult.ok(
                            data=result,
                            elapsed_time=time.monotonic() - total_start,
                            retry_count=retry_count,
                        )
                    else:
                        last_error = f"{func.__name__} 返回 False"
                except Exception as e:
                    last_error = str(e)
                    logger.warning(
                        "[%s] 第%d次执行异常: %s",
                        func.__name__, attempt + 1, str(e),
                    )

                if attempt < max_retries:
                    retry_count += 1
                    logger.info(
                        "[%s] 第%d次重试（共%d次），等待%.1f秒",
                        func.__name__, retry_count, max_retries, retry_interval,
                    )
                    _interruptible_sleep(retry_interval, stop_event)

            elapsed = time.monotonic() - total_start
            return StepResult.fail(
                error_msg=last_error or f"{func.__name__} 重试{max_retries}次后仍失败",
                elapsed_time=elapsed,
                retry_count=retry_count,
            )

        return wrapper

    return decorator


def _should_interrupt(
    stop_event: threading.Event | None,
    check_interrupt: Callable[[], bool] | None,
) -> bool:
    """检查是否应该中断执行

    优先使用自定义中断检查回调，其次检查 stop_event。

    Args:
        stop_event: 线程事件对象，set 状态表示需要中断
        check_interrupt: 自定义中断检查回调函数

    Returns:
        True 表示应该中断执行
    """
    if check_interrupt is not None:
        try:
            return bool(check_interrupt())
        except Exception:
            return False

    if stop_event is not None:
        return stop_event.is_set()

    return False


def _interruptible_sleep(
    seconds: float,
    stop_event: threading.Event | None,
) -> None:
    """可中断的睡眠

    使用 threading.Event.wait 替代 time.sleep，支持提前中断。

    Args:
        seconds: 睡眠时间（秒）
        stop_event: 线程事件对象，set 状态会提前结束睡眠
    """
    if stop_event is not None:
        stop_event.wait(timeout=seconds)
    else:
        time.sleep(seconds)
