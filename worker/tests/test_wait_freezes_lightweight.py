"""wait_for_change_lightweight 单元测试 (spec 阶段 4.2.1 — 任务 1.7)

轻量竞态防护：ClickNode 默认调用此方法检测点击后画面是否变化。
与 wait_for_change 不同：
- 默认 2s 超时（不是 30s），适应点击-导航竞态的快速判断
- 返回 ScreenChangeOutcome 枚举（CHANGED/UNCHANGED/TIMEOUT/SKIPPED），
  不是 bool，让 ClickNode 能区分"画面没变"与"设备异常"
- 画面变化立即返回（不等稳定），未变化只记 warning 不 fail
"""

from __future__ import annotations

import numpy as np
import pytest
from core.wait_freezes import ScreenChangeOutcome, WaitFreezes

pytestmark = pytest.mark.unit


def _solid_frame(color: int, size: tuple[int, int] = (100, 100, 3)) -> np.ndarray:
    """生成指定颜色的纯色帧。"""
    frame = np.zeros(size, dtype=np.uint8)
    frame[:, :, :] = color
    return frame


class TestScreenChangeOutcomeEnum:
    """ScreenChangeOutcome 枚举值约定。"""

    def test_enum_values_are_strings(self):
        """枚举值必须是字符串，便于 JSON 序列化进 JSONL。"""
        assert ScreenChangeOutcome.CHANGED.value == "CHANGED"
        assert ScreenChangeOutcome.UNCHANGED.value == "UNCHANGED"
        assert ScreenChangeOutcome.TIMEOUT.value == "TIMEOUT"
        assert ScreenChangeOutcome.SKIPPED.value == "SKIPPED"

    def test_enum_is_str_compatible(self):
        """StrEnum 应可直接与字符串比较。"""
        assert ScreenChangeOutcome.CHANGED == "CHANGED"


class TestWaitForChangeLightweight:
    """wait_for_change_lightweight 行为测试。"""

    def test_returns_changed_when_frame_differs_from_baseline(self):
        """画面变化应立即返回 CHANGED。"""
        wf = WaitFreezes()
        call_count = [0]
        baseline = _solid_frame(0)

        def capture_fn():
            call_count[0] += 1
            # 第 1 次返回 baseline，后续返回不同帧
            if call_count[0] == 1:
                return baseline
            return _solid_frame(255)

        outcome = wf.wait_for_change_lightweight(capture_fn, timeout=2.0)
        assert outcome == ScreenChangeOutcome.CHANGED

    def test_returns_unchanged_when_frame_stays_same_within_timeout(self):
        """超时内画面未变化应返回 UNCHANGED（不 fail，让 ClickNode 决策）。"""
        wf = WaitFreezes()
        same_frame = _solid_frame(128)

        def capture_fn():
            return same_frame.copy()

        outcome = wf.wait_for_change_lightweight(
            capture_fn, timeout=0.2, poll_interval=0.05,
        )
        assert outcome == ScreenChangeOutcome.UNCHANGED

    def test_returns_timeout_when_capture_fn_returns_none(self):
        """有 baseline 后 capture_fn 持续返回 None 应返回 TIMEOUT（设备异常）。"""
        wf = WaitFreezes()
        call_count = [0]
        baseline = _solid_frame(0)

        def capture_fn():
            call_count[0] += 1
            # 第 1 次返回有效 baseline，后续返回 None（模拟设备掉线）
            if call_count[0] == 1:
                return baseline
            return None

        outcome = wf.wait_for_change_lightweight(
            capture_fn, timeout=0.2, poll_interval=0.05,
        )
        assert outcome == ScreenChangeOutcome.TIMEOUT

    def test_returns_skipped_when_baseline_is_none(self):
        """首帧 baseline 为 None 应返回 SKIPPED（无法检测变化）。"""
        wf = WaitFreezes()

        def capture_fn():
            return None

        outcome = wf.wait_for_change_lightweight(capture_fn, timeout=0.1)
        assert outcome == ScreenChangeOutcome.SKIPPED

    def test_change_detected_immediately_without_full_timeout(self):
        """画面一旦变化应立即返回，不应等满 timeout。"""
        wf = WaitFreezes()
        call_count = [0]
        baseline = _solid_frame(0)

        def capture_fn():
            call_count[0] += 1
            if call_count[0] == 1:
                return baseline
            # 第 2 次就变化，应该立即返回
            return _solid_frame(255)

        import time as _time
        start = _time.monotonic()
        outcome = wf.wait_for_change_lightweight(
            capture_fn, timeout=2.0, poll_interval=0.05,
        )
        elapsed = _time.monotonic() - start
        assert outcome == ScreenChangeOutcome.CHANGED
        # 应该远小于 2s（一次 poll 即可检测到）
        assert elapsed < 0.5, f"elapsed={elapsed:.3f}s, expected < 0.5s"

    def test_uses_change_threshold_to_detect_small_diff(self):
        """change_threshold 控制什么算"变化"——小幅波动不应触发 CHANGED。"""
        wf = WaitFreezes()
        baseline = _solid_frame(100)

        # 用一个几乎相同但略有差异的帧（差异 < 1%）
        slightly_different = baseline.copy()
        slightly_different[0, 0, :] = 110  # 单像素小变化

        call_count = [0]

        def capture_fn():
            call_count[0] += 1
            if call_count[0] == 1:
                return baseline
            return slightly_different.copy()

        # change_threshold=0.05 要求 5% 差异才算变化
        outcome = wf.wait_for_change_lightweight(
            capture_fn, timeout=0.2, change_threshold=0.05, poll_interval=0.05,
        )
        # 单像素变化不够，应判为 UNCHANGED
        assert outcome == ScreenChangeOutcome.UNCHANGED


class TestWaitForChangeLightweightIntegrationWithClickNode:
    """轻量防护与 ClickNode 集成的契约测试（任务 1.6 用）。"""

    def test_lightweight_does_not_raise_on_device_capture_failure(self):
        """capture_fn 抛异常应被吞掉，返回 TIMEOUT 不向上传播。"""
        wf = WaitFreezes()

        def capture_fn():
            raise RuntimeError("device disconnected")

        # 不应抛异常
        outcome = wf.wait_for_change_lightweight(capture_fn, timeout=0.1)
        # 设备异常 → 视为 TIMEOUT
        assert outcome in (ScreenChangeOutcome.TIMEOUT, ScreenChangeOutcome.SKIPPED)
