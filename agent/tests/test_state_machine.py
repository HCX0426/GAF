"""状态机单元测试 + 集成测试 (合并)

合并说明: 原 test_state_machine.py + test_state_machine_integration.py
合并后消除重复的 Mock 辅助类。
"""

import threading
import time

import numpy as np
import pytest
from core.state_machine import _CACHE_MISS, StateMachine, StateNode, StateTransition

pytestmark = pytest.mark.e2e


class _MockDeviceManager:
    """模拟设备管理器"""

    def get_active_device(self):
        """返回模拟设备"""
        return _MockDevice()


class _MockDevice:
    """模拟设备"""

    def capture_screen(self):
        """返回模拟截图数据"""
        return np.zeros((100, 100, 3), dtype=np.uint8)


class _MockImageProcessor:
    """模拟图像处理器"""
    pass


# ===========================================================================
# 基本状态转移 (原 test_state_machine.py)
# ===========================================================================


class TestStateMachineBasic:
    """基本状态转移测试"""

    def test_state_machine_basic(self):
        """验证基本状态转移流程：init -> running -> done"""
        sm = StateMachine(
            device_manager=_MockDeviceManager(),
            image_processor=_MockImageProcessor(),
        )

        visited = []

        init_node = StateNode(
            name="init",
            action=lambda: visited.append("init_action"),
            transitions=[
                StateTransition(
                    target="running",
                    condition=lambda _: True,
                    priority=0,
                ),
            ],
        )
        running_node = StateNode(
            name="running",
            action=lambda: visited.append("running_action"),
            transitions=[
                StateTransition(
                    target="done",
                    condition=lambda _: True,
                    priority=0,
                ),
            ],
        )
        done_node = StateNode(
            name="done",
            action=lambda: visited.append("done_action"),
            is_terminal=True,
        )

        sm.add_state(init_node)
        sm.add_state(running_node)
        sm.add_state(done_node)
        sm.set_initial_state("init")

        result = sm.run(max_iterations=10)
        assert result.success is True
        assert "init_action" not in visited
        assert "running_action" not in visited
        assert "done_action" in visited


class TestStateMachinePriority:
    """优先级转移测试"""

    def test_state_machine_priority(self):
        """验证高优先级转移优先执行"""
        sm = StateMachine(
            device_manager=_MockDeviceManager(),
            image_processor=_MockImageProcessor(),
        )

        visited = []

        start_node = StateNode(
            name="start",
            action=lambda: None,
            transitions=[
                StateTransition(
                    target="low_priority",
                    condition=lambda _: True,
                    priority=10,
                ),
                StateTransition(
                    target="high_priority",
                    condition=lambda _: True,
                    priority=0,
                ),
            ],
        )
        low_node = StateNode(
            name="low_priority",
            action=lambda: visited.append("low"),
            is_terminal=True,
        )
        high_node = StateNode(
            name="high_priority",
            action=lambda: visited.append("high"),
            is_terminal=True,
        )

        sm.add_state(start_node)
        sm.add_state(low_node)
        sm.add_state(high_node)
        sm.set_initial_state("start")

        result = sm.run(max_iterations=10)
        assert result.success is True
        assert "high" in visited
        assert "low" not in visited


class TestStateMachineStop:
    """停止状态机测试"""

    def test_state_machine_stop(self):
        """验证手动停止状态机返回中断结果"""
        sm = StateMachine(
            device_manager=_MockDeviceManager(),
            image_processor=_MockImageProcessor(),
        )

        loop_node = StateNode(
            name="loop",
            action=lambda: time.sleep(0.01),
            transitions=[],
        )

        sm.add_state(loop_node)
        sm.set_initial_state("loop")

        def stop_after_delay():
            """延迟后停止状态机"""
            time.sleep(0.05)
            sm.stop()

        t = threading.Thread(target=stop_after_delay)
        t.start()

        result = sm.run(max_iterations=10000)
        t.join()
        assert result.success is False
        assert result.is_interrupted is True
        assert "手动停止" in result.error_msg


# ===========================================================================
# 集成测试 (原 test_state_machine_integration.py)
# ===========================================================================


class TestStateMachineIntegration:
    """状态机集成测试"""

    def test_state_transition(self):
        """测试状态转换：idle -> running"""
        sm = StateMachine(
            device_manager=_MockDeviceManager(),
            image_processor=_MockImageProcessor(),
        )
        sm.add_state(StateNode(
            name='idle',
            action=lambda: None,
            transitions=[
                StateTransition(target='running', condition=lambda ctx: True),
            ],
        ))
        sm.add_state(StateNode(name='running', action=lambda: None, is_terminal=True))
        sm.set_initial_state('idle')
        result = sm.run(max_iterations=10)
        assert result.success is True
        assert sm.get_current_state() == 'running'

    def test_stuck_detection(self):
        """测试卡顿检测：同一状态连续未转移超过阈值触发 on_stuck"""
        stuck_called = []

        def on_stuck():
            stuck_called.append('idle')

        sm = StateMachine(
            device_manager=_MockDeviceManager(),
            image_processor=_MockImageProcessor(),
        )
        sm.add_state(StateNode(
            name='idle',
            action=lambda: None,
            stuck_threshold=2,
            on_stuck=on_stuck,
        ))
        sm.set_initial_state('idle')
        sm.run(max_iterations=5)
        assert len(stuck_called) >= 1
        assert stuck_called[0] == 'idle'

    def test_recognition_cache(self):
        """测试识别结果缓存：同一截图内容命中缓存"""
        sm = StateMachine(
            device_manager=_MockDeviceManager(),
            image_processor=_MockImageProcessor(),
        )
        sm.add_state(StateNode(name='idle', action=lambda: None))
        sm.set_initial_state('idle')

        key = sm._make_cache_key('idle', 'target', 'screenshot_data')
        sm._set_cached_result(key, True)

        cached = sm._get_cached_result(key)
        assert cached is True

    def test_cache_miss_sentinel(self):
        """测试缓存未命中使用哨兵值"""
        sm = StateMachine(
            device_manager=_MockDeviceManager(),
            image_processor=_MockImageProcessor(),
        )
        sm.add_state(StateNode(name='idle', action=lambda: None))
        sm.set_initial_state('idle')

        result = sm._get_cached_result('nonexistent_key')
        assert result is _CACHE_MISS

    def test_cache_eviction(self):
        """测试缓存淘汰：超过容量时移除最旧条目"""
        sm = StateMachine(
            device_manager=_MockDeviceManager(),
            image_processor=_MockImageProcessor(),
            result_cache_size=2,
        )
        sm.add_state(StateNode(name='idle', action=lambda: None))
        sm.set_initial_state('idle')

        sm._set_cached_result('key1', True)
        sm._set_cached_result('key2', True)
        sm._set_cached_result('key3', True)

        assert sm._get_cached_result('key1') is _CACHE_MISS
        assert sm._get_cached_result('key2') is True
        assert sm._get_cached_result('key3') is True
