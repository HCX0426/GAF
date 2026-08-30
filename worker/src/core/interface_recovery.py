"""界面恢复机制 (Interface Recovery)

节点失败后识别当前界面 → BFS 推理回退路径 → 回到期望界面或存档。

设计文档: docs/business/tasks/recovery-design.md

核心流程 (§3.2):
    1. 截图当前界面
    2. 跑 popup_handler 关临时弹窗
    3. 重新截图识别底层界面 (含 transient 重试)
    4. BFS 推理 current_state → expected_state 最短路径
    5. 执行回退动作序列 (每步截图验证)
    6. 未知界面兜底 (存档 + 返回 NEEDS_HUMAN)

与 engine 的集成 (§5.2):
    engine 在 `if not continue_on_error:` 失败分支内调用 `recover()`。
    RECOVERED / ALREADY_THERE → engine 重试当前节点 (不更新 _current_node_id)。
    NEEDS_HUMAN / RECOVERY_FAILED → engine 返回 FAILED + 暂停任务。
"""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


# 模板类识别节点 (路径推断适用)
_TEMPLATE_NODE_TYPES = frozenset({
    "template_match", "template_match_any", "feature_match",
})

# PATH_STATE_MAPPING: 精确匹配层 (§3.3)
# 键: template 路径片段 (相对路径,不含扩展名)
# 值: interface_states.yaml 中的状态名
# 未来 (Phase 2+) 可迁移到 yaml 配置化
PATH_STATE_MAPPING: dict[str, str] = {
    "public/主界面": "main_menu",
    "public/地图标识": "map_view",
}

# transitions.action 支持的类型清单 (§4.1)
_VALID_ACTION_TYPES = frozenset({
    "template_match", "key_press", "click", "swipe", "wait",
})


class RecoveryOutcome(Enum):
    """恢复结果枚举 (§4.3)。"""
    RECOVERED = "recovered"          # 成功回退到期望界面
    NEEDS_HUMAN = "needs_human"      # 未知界面,已存档
    ALREADY_THERE = "already_there"  # 当前就在期望界面,无需回退
    RECOVERY_FAILED = "failed"       # 回退路径执行失败 (如返回键没反应)


@dataclass
class InterfaceRecoveryResult:
    """恢复结果数据结构 (§4.3)。

    字段 None vs 空列表语义:
        None — "未执行" (如 path_taken=None 表示未尝试回退)
        []   — "执行了但为空"
    不用 field(default_factory=list) 以保持 None 语义清晰。
    """
    outcome: RecoveryOutcome
    current_state: str | None = None
    expected_state: str | None = None
    path_taken: list[str] | None = None
    actions_executed: list[dict] | None = None
    archive_path: str | None = None    # NEEDS_HUMAN 时填充
    error_msg: str | None = None       # RECOVERY_FAILED 时填充
    screenshots: list[str] | None = None  # debug_mode 时填充


class InterfaceRecoveryManager:
    """界面恢复 Manager (§5.1)。

    通过依赖注入接收截图/模板匹配/动作执行函数,便于单元测试。
    engine 在节点失败时调用 recover() 主入口。
    """

    def __init__(
        self,
        states_config_path: str,
        screenshot_fn: Callable[[], Any],
        template_match_fn: Callable[..., Any | None],
        action_executor_fn: Callable[[dict], bool],
        popup_handler: Any | None = None,
        archive_dir: str = "debug/unknown_states",
        max_recovery_steps: int = 5,
        archive_dedupe_window: int = 10,
    ):
        """初始化 Manager,加载并校验 interface_states.yaml。

        Args:
            states_config_path: interface_states.yaml 路径
            screenshot_fn: 截图函数 (无参,返回截图数据)
            template_match_fn: 模板匹配函数,
                签名 (screenshot, template, roi: dict|None, threshold) -> dict|None
                (orchestrator 应注入包装了 resolve_resource_path 的版本)
            action_executor_fn: 动作执行函数,签名 (action: dict) -> bool
            popup_handler: PopupHandler 实例 (复用现有弹窗处理)
            archive_dir: 未知界面存档目录
            max_recovery_steps: 回退最多步数,防无限循环
            archive_dedupe_window: 存档去重窗口秒数 (§10.4)

        Raises:
            ValueError: yaml 校验失败 (from/to 未定义 / action.type 非法 / 显式自环)
            FileNotFoundError: states_config_path 不存在
        """
        self._screenshot_fn = screenshot_fn
        self._template_match_fn = template_match_fn
        self._action_executor_fn = action_executor_fn
        self._popup_handler = popup_handler
        self._archive_dir = Path(archive_dir)
        self._max_recovery_steps = max_recovery_steps
        self._archive_dedupe_window = archive_dedupe_window

        # spec §4.4.2 — transient 参数改为从 node_config 读取 (recover 调用时).
        # __init__ 时机拿不到 node_config, 故不再在这里硬编码默认值;
        # 默认值 (1.5s / 2 次) 在 recover() 内通过 node_config.get(..., default) 取.
        # 存档去重缓存: (pipeline_name, node_id) -> last_archive_time (monotonic)
        self._last_archive_time: dict[tuple[str, str], float] = {}

        # 加载并校验 yaml
        path = Path(states_config_path)
        if not path.is_file():
            raise FileNotFoundError(f"interface_states.yaml 不存在: {path}")

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        states_data = data.get("states", {}) or {}
        transitions_data = data.get("transitions", []) or []

        # 校验 + 缓存 states
        self._states: dict[str, dict] = states_data
        self.safe_states: list[str] = [
            name for name, cfg in states_data.items()
            if cfg.get("is_safe_state", False)
        ]

        # 校验 + 缓存 transitions
        self._transitions: list[dict] = []
        for t in transitions_data:
            from_state = t.get("from")
            to_state = t.get("to")
            action = t.get("action", {}) or {}
            action_kind = action.get("node_type") or action.get("type")

            # §10.3 校验: from/to 必须在 states 中已定义
            if from_state not in states_data:
                raise ValueError(
                    f"transition.from '{from_state}' 未在 states 中定义"
                )
            if to_state not in states_data:
                raise ValueError(
                    f"transition.to '{to_state}' 未在 states 中定义"
                )
            # §10.3 校验: 显式自环拒绝
            if from_state == to_state:
                raise ValueError(
                    f"显式自环不允许 (from == to == '{from_state}')"
                )
            # §4.1 校验: action.type 必须在清单中
            if action_kind not in _VALID_ACTION_TYPES:
                raise ValueError(
                    f"不支持的 action.type '{action_kind}',"
                    f"允许值: {sorted(_VALID_ACTION_TYPES)}"
                )

            self._transitions.append(t)

        # 构建邻接表 (用于 BFS): from_state -> [(to_state, action), ...]
        self._adjacency: dict[str, list[tuple[str, dict]]] = {}
        for t in self._transitions:
            self._adjacency.setdefault(t["from"], []).append(
                (t["to"], t.get("action", {}) or {})
            )

        logger.info(
            "InterfaceRecoveryManager 初始化完成: %d 个状态, %d 条转移, %d 个安全状态",
            len(self._states), len(self._transitions), len(self.safe_states),
        )

    # ------------------------------------------------------------------
    # 主入口 (§3.2 调用时序)
    # ------------------------------------------------------------------

    def recover(
        self,
        expected_state: str,
        pipeline_name: str,
        node_id: str,
        node_config: dict,
        execution_context: dict,
        attempt: int = 0,
        exclude_edges: list[tuple[str, str]] | None = None,
    ) -> InterfaceRecoveryResult:
        """节点失败后调用,尝试回退到 expected_state (§5.1)。

        Args:
            expected_state: 期望界面状态名 (由 engine 调用 infer_expected_state 得到)
            pipeline_name: pipeline 名称
            node_id: 失败节点 ID
            node_config: 失败节点配置
            execution_context: 执行上下文字典,字段见 §4.2
            attempt: 恢复尝试序号 (0=第一次, 1=第二次...)。当 attempt>0
                时, 调用方应同时传 exclude_edges 把上次失败的路径边排除掉,
                否则 BFS 会返回同一条路径 (§3.2 步骤 4 换路径策略)。
            exclude_edges: 要排除的边列表 [(from_state, to_state), ...]。
                BFS 跳过这些边, 强制寻找替代路径。None 表示不排除。

        Returns:
            InterfaceRecoveryResult
        """
        if attempt > 0:
            logger.info(
                "节点 %s 第 %d 次恢复尝试, 排除 %d 条边",
                node_id, attempt, len(exclude_edges or []),
            )

        # spec §4.4.2 — transient 参数从 node_config 读取 (默认 1.5s / 2 次).
        # __init__ 时机拿不到 node_config, 故此处取值后向下传递.
        transient_wait_s = float(node_config.get("transient_wait_s", 1.5))
        transient_max_retries = int(node_config.get("transient_max_retries", 2))

        # 步骤 1: 截图当前界面
        screenshot = self._screenshot_fn()

        # 步骤 2: 跑 popup_handler 关临时弹窗
        screenshot_after_popup = None
        if self._popup_handler is not None:
            try:
                self._popup_handler.check_and_handle(screenshot)
                # 重新截图 (popup 关闭后底层界面可能已变化)
                screenshot_after_popup = self._screenshot_fn()
                screenshot = screenshot_after_popup
            except Exception as exc:
                logger.warning("popup_handler 执行异常,继续用原截图: %s", exc)

        # 步骤 3: 识别底层界面 (含 transient 重试)
        current_state, best_score, best_match_state = self._identify_with_transient_retry(
            screenshot, transient_wait_s, transient_max_retries,
        )

        # 步骤 3a: 判断 current_state == expected_state?
        if current_state == expected_state:
            logger.info(
                "节点 %s 当前已在期望界面 '%s',跳过回退 (ALREADY_THERE)",
                node_id, expected_state,
            )
            return InterfaceRecoveryResult(
                outcome=RecoveryOutcome.ALREADY_THERE,
                current_state=current_state,
                expected_state=expected_state,
            )

        # 步骤 4: BFS 推理路径 (current_state 为 None 时无法推理)
        # attempt>0 时传 exclude_edges 强制走替代路径 (§3.2 换路径策略)
        path: list[str] | None = None
        if current_state is not None:
            path = self.find_path(
                current_state, expected_state,
                exclude_edges=exclude_edges,
            )

        # 步骤 5: 执行回退动作序列
        if path is not None and len(path) >= 2:
            result = self._execute_path(path, expected_state)
            # 把 archive 字段补全 (供 NEEDS_HUMAN 时存档用)
            if result.outcome == RecoveryOutcome.RECOVERY_FAILED:
                # 回退失败也走存档兜底
                return self._archive_and_finish(
                    screenshot=screenshot,
                    pipeline_name=pipeline_name,
                    node_id=node_id,
                    node_config=node_config,
                    expected_state=expected_state,
                    execution_context=execution_context,
                    current_state=current_state,
                    best_score=best_score,
                    best_match_state=best_match_state,
                    path_taken=result.path_taken,
                    actions_executed=result.actions_executed,
                    error_msg=result.error_msg,
                )
            return result

        # 步骤 6: 未知界面兜底 (current_state is None 或 path is None)
        return self._archive_and_finish(
            screenshot=screenshot,
            pipeline_name=pipeline_name,
            node_id=node_id,
            node_config=node_config,
            expected_state=expected_state,
            execution_context=execution_context,
            current_state=current_state,
            best_score=best_score,
            best_match_state=best_match_state,
            path_taken=path,
            actions_executed=None,
        )

    # ------------------------------------------------------------------
    # 识别 (§3.2 步骤 3 + transient 重试)
    # ------------------------------------------------------------------

    def identify_state(self, screenshot: Any) -> tuple[str | None, float]:
        """识别当前界面状态 (§5.1)。

        detect_templates 是 OR 逻辑 — 任一模板命中即识别为该状态。

        Args:
            screenshot: 截图数据

        Returns:
            (state_name, score) — 命中返回 (状态名, 置信度)
                                  未命中返回 (None, 最高匹配置信度)
        """
        best_state: str | None = None
        best_score: float = 0.0

        for state_name, state_cfg in self._states.items():
            templates = state_cfg.get("detect_templates", []) or []
            for tmpl_cfg in templates:
                template = tmpl_cfg.get("template")
                if not template:
                    continue
                threshold = tmpl_cfg.get("threshold", 0.8)
                roi_list = tmpl_cfg.get("roi")
                # interface_states.yaml 的 roi 是 [x, y, w, h] 列表格式,
                # find_template 需要 dict 格式
                roi_dict = None
                if roi_list and isinstance(roi_list, list) and len(roi_list) == 4:
                    roi_dict = {
                        "x": roi_list[0], "y": roi_list[1],
                        "w": roi_list[2], "h": roi_list[3],
                    }

                try:
                    match = self._template_match_fn(
                        screenshot, template, roi=roi_dict, threshold=threshold,
                    )
                except Exception as exc:
                    logger.warning(
                        "状态 '%s' 模板 '%s' 匹配异常: %s",
                        state_name, template, exc,
                    )
                    continue

                if match is not None:
                    score = float(match.get("confidence", 0.0))
                    if score >= threshold:
                        logger.debug(
                            "状态 '%s' 命中 (template=%s, score=%.3f)",
                            state_name, template, score,
                        )
                        return state_name, score
                    # 未达阈值但记录最高分 (供 context.json best_match_score)
                    if score > best_score:
                        best_score = score
                        best_state = state_name
                elif best_state is None:
                    # 完全未命中时 best_state 保持 None
                    pass

        return None, best_score

    def _identify_with_transient_retry(
        self, screenshot: Any,
        transient_wait_s: float = 1.5,
        transient_max_retries: int = 2,
    ) -> tuple[str | None, float, str | None]:
        """识别 + transient 重试 (§3.2 步骤 3 + §10.4 第一层)。

        spec §4.4.2 — transient 参数由调用方 (recover) 从 node_config
        读取后传入, 不再使用 self._transient_* 硬编码. 保留方法签名默认值
        是为了向后兼容 (如有外部直接调用本方法的场景).

        Args:
            screenshot: 截图数据
            transient_wait_s: 每次重试前等待秒数 (默认 1.5)
            transient_max_retries: 最大重试次数 (默认 2)

        Returns:
            (current_state, best_score, best_match_state)
            - current_state: 命中的状态名,未命中为 None
            - best_score: 最高匹配置信度 (供 context.json)
            - best_match_state: 最高分状态名 (供 context.json)
        """
        state, score = self.identify_state(screenshot)
        if state is not None:
            return state, score, state

        # transient 重试 (loading 消散 / 网络恢复 / 点击延迟)
        logger.info(
            "首次识别未命中,启动 transient 重试 (等待 %.1fs × 最多 %d 次)",
            transient_wait_s, transient_max_retries,
        )
        best_score = score
        best_match_state: str | None = None

        for attempt in range(transient_max_retries):
            time.sleep(transient_wait_s)
            screenshot = self._screenshot_fn()
            state, score = self.identify_state(screenshot)
            if state is not None:
                logger.info(
                    "transient 重试第 %d 次命中状态 '%s'",
                    attempt + 1, state,
                )
                return state, score, state
            if score > best_score:
                best_score = score
                best_match_state = state  # state 为 None 时保持 None

        logger.warning(
            "transient 重试 %d 次仍未命中,确认为未知界面",
            transient_max_retries,
        )
        return None, best_score, best_match_state

    # ------------------------------------------------------------------
    # BFS 路径推理 (§3.2 步骤 4 + §10.3)
    # ------------------------------------------------------------------

    def find_path(
        self,
        from_state: str,
        to_state: str,
        exclude_edges: list[tuple[str, str]] | None = None,
    ) -> list[str] | None:
        """BFS 找最短回退路径 (§5.1)。

        BFS 天然处理环 (visited set),不会无限循环。
        显式自环已在 __init__ 校验时拒绝。

        Args:
            from_state: 起始状态
            to_state: 目标状态
            exclude_edges: 要排除的边列表 [(from, to), ...]。
                spec 阶段 3 — 任务 3.3 换路径策略: 第二次恢复尝试时,
                调用方把第一次失败的路径边传入, BFS 跳过这些边强制
                寻找替代路径。None 表示不排除 (默认行为, 向后兼容)。

        Returns:
            状态名列表 [from, intermediate1, ..., to]
            无路径返回 None
        """
        if from_state == to_state:
            return [from_state]
        if from_state not in self._adjacency:
            return None

        # Normalize exclude_edges to a set of (from, to) tuples for O(1) lookup
        excluded: set[tuple[str, str]] = set(exclude_edges) if exclude_edges else set()

        # BFS
        queue: deque[tuple[str, list[str]]] = deque()
        queue.append((from_state, [from_state]))
        visited: set[str] = {from_state}

        while queue:
            current, path = queue.popleft()
            for next_state, _action in self._adjacency.get(current, []):
                # Skip excluded edges (spec 阶段 3 — 任务 3.3)
                if (current, next_state) in excluded:
                    continue
                if next_state == to_state:
                    return path + [next_state]
                if next_state in visited:
                    continue
                visited.add(next_state)
                queue.append((next_state, path + [next_state]))

        return None

    # ------------------------------------------------------------------
    # 回退路径执行 (§3.2 步骤 5 + §10.1)
    # ------------------------------------------------------------------

    def _execute_path(
        self, path: list[str], expected_state: str,
    ) -> InterfaceRecoveryResult:
        """执行回退路径,每步后截图验证 (§3.2 步骤 5)。

        连续 2 步未到达 expected_state → RECOVERY_FAILED (§10.1)。
        max_recovery_steps 防无限循环。
        """
        actions_executed: list[dict] = []
        path_taken: list[str] = [path[0]]
        consecutive_failures = 0

        # path = [from, intermediate1, ..., to]
        # 每条边对应一个 action
        for i in range(len(path) - 1):
            if i >= self._max_recovery_steps:
                logger.warning(
                    "回退步数达上限 %d,终止 (path=%s)",
                    self._max_recovery_steps, path,
                )
                break

            from_state = path[i]
            to_state = path[i + 1]
            action = self._find_action(from_state, to_state)
            if action is None:
                logger.warning(
                    "找不到 %s -> %s 的 action,终止回退",
                    from_state, to_state,
                )
                return InterfaceRecoveryResult(
                    outcome=RecoveryOutcome.RECOVERY_FAILED,
                    current_state=path[-1] if path_taken else from_state,
                    expected_state=expected_state,
                    path_taken=path_taken,
                    actions_executed=actions_executed,
                    error_msg=f"no action for edge {from_state} -> {to_state}",
                )

            # 执行 action
            try:
                success = self._action_executor_fn(action)
            except Exception as exc:
                logger.warning("action 执行异常: %s", exc)
                success = False

            actions_executed.append({
                "node_type": action.get("node_type") or action.get("type"),
                "type": action.get("type"),
                "from": from_state,
                "to": to_state,
                "success": success,
            })

            if not success:
                consecutive_failures += 1
                if consecutive_failures >= 2:
                    logger.warning(
                        "连续 %d 步回退失败,终止 (§10.1)",
                        consecutive_failures,
                    )
                    return InterfaceRecoveryResult(
                        outcome=RecoveryOutcome.RECOVERY_FAILED,
                        current_state=from_state,
                        expected_state=expected_state,
                        path_taken=path_taken,
                        actions_executed=actions_executed,
                        error_msg=f"consecutive {consecutive_failures} action failures",
                    )
                continue

            # action 成功,截图验证是否到达 to_state
            consecutive_failures = 0
            time.sleep(0.5)  # 给界面过渡动画时间
            screenshot = self._screenshot_fn()
            current_state, _ = self.identify_state(screenshot)

            if current_state == to_state:
                path_taken.append(to_state)
            elif current_state == expected_state:
                # 提前到达 expected_state
                path_taken.append(current_state)
                logger.info("提前到达 expected_state '%s'", expected_state)
                return InterfaceRecoveryResult(
                    outcome=RecoveryOutcome.RECOVERED,
                    current_state=current_state,
                    expected_state=expected_state,
                    path_taken=path_taken,
                    actions_executed=actions_executed,
                )
            else:
                # action 执行了但界面没变到 to_state
                logger.warning(
                    "action 执行后界面为 '%s' (期望 '%s')",
                    current_state, to_state,
                )
                path_taken.append(current_state or to_state)
                consecutive_failures += 1
                if consecutive_failures >= 2:
                    return InterfaceRecoveryResult(
                        outcome=RecoveryOutcome.RECOVERY_FAILED,
                        current_state=current_state,
                        expected_state=expected_state,
                        path_taken=path_taken,
                        actions_executed=actions_executed,
                        error_msg="consecutive state verification failures",
                    )

        # 检查是否到达 expected_state
        if path_taken and path_taken[-1] == expected_state:
            return InterfaceRecoveryResult(
                outcome=RecoveryOutcome.RECOVERED,
                current_state=expected_state,
                expected_state=expected_state,
                path_taken=path_taken,
                actions_executed=actions_executed,
            )

        return InterfaceRecoveryResult(
            outcome=RecoveryOutcome.RECOVERY_FAILED,
            current_state=path_taken[-1] if path_taken else None,
            expected_state=expected_state,
            path_taken=path_taken,
            actions_executed=actions_executed,
            error_msg="path exhausted without reaching expected_state",
        )

    def _find_action(self, from_state: str, to_state: str) -> dict | None:
        """从 transitions 中查找 from -> to 的 action。"""
        for t in self._transitions:
            if t["from"] == from_state and t["to"] == to_state:
                return t.get("action", {}) or {}
        return None

    # ------------------------------------------------------------------
    # 未知界面存档 (§3.2 步骤 6 + §4.2 + §10.4 第二层)
    # ------------------------------------------------------------------

    def archive_unknown_state(
        self,
        screenshot: Any,
        context: dict,
    ) -> str:
        """未知界面存档,返回存档目录路径 (§5.1)。

        Args:
            screenshot: 失败时截图
            context: 存档上下文字典 (见 §4.2 字段表)

        Returns:
            存档目录路径 (绝对路径字符串)
        """
        pipeline_name = context.get("pipeline_name", "unknown")
        node_id = context.get("node_id", "unknown")
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        archive_dir_name = f"{pipeline_name}_{node_id}_{timestamp}"
        archive_dir = self._archive_dir / archive_dir_name
        archive_dir.mkdir(parents=True, exist_ok=True)

        # 保存截图 (screenshot 可能是 numpy ndarray 或 PIL Image)
        screenshot_path = archive_dir / "screenshot.png"
        self._save_screenshot(screenshot, screenshot_path)

        # 保存 context.json
        context_path = archive_dir / "context.json"
        with open(context_path, "w", encoding="utf-8") as f:
            json.dump(context, f, ensure_ascii=False, indent=2, default=str)

        logger.info("未知界面已存档: %s", archive_dir)
        return str(archive_dir)

    def _archive_and_finish(
        self,
        screenshot: Any,
        pipeline_name: str,
        node_id: str,
        node_config: dict,
        expected_state: str,
        execution_context: dict,
        current_state: str | None,
        best_score: float,
        best_match_state: str | None,
        path_taken: list[str] | None,
        actions_executed: list[dict] | None,
        error_msg: str | None = None,
    ) -> InterfaceRecoveryResult:
        """存档 + 返回 NEEDS_HUMAN 结果 (步骤 6 兜底)。

        含 §10.4 第二层去重: 同一 (pipeline_name, node_id) 在
        archive_dedupe_window 秒内不重复存档。
        """
        # §10.4 第二层: 去重检查
        key = (pipeline_name, node_id)
        now = time.monotonic()
        last_time = self._last_archive_time.get(key)
        if last_time is not None and (now - last_time) < self._archive_dedupe_window:
            logger.info(
                "节点 %s 在 %ds 去重窗口内已存档,跳过本次存档",
                node_id, self._archive_dedupe_window,
            )
            return InterfaceRecoveryResult(
                outcome=RecoveryOutcome.NEEDS_HUMAN,
                current_state=current_state,
                expected_state=expected_state,
                path_taken=path_taken,
                actions_executed=actions_executed,
                archive_path=None,  # 跳过存档,无路径
                error_msg=error_msg,
            )

        # 构建 context.json (§4.2 字段表)
        context = {
            "pipeline_name": pipeline_name,
            "node_id": node_id,
            "node_type": execution_context.get("node_type"),
            "node_config": node_config,
            "expected_state": expected_state,
            "expected_state_source": execution_context.get("expected_state_source"),
            "matched_states": [],  # 未知界面,通常为空
            "best_match_score": best_score,
            "best_match_state": best_match_state,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "device_id": execution_context.get("device_id"),
            "execution_id": execution_context.get("execution_id"),
            "recovery_attempt": execution_context.get("recovery_attempt"),
            "retry_count": execution_context.get("retry_count"),
            "previous_node_id": execution_context.get("previous_node_id"),
            "previous_node_result": execution_context.get("previous_node_result"),
            "recovery_path_attempted": path_taken,
            "recovery_actions_executed": actions_executed,
        }

        archive_path = self.archive_unknown_state(screenshot, context)
        self._last_archive_time[key] = now

        return InterfaceRecoveryResult(
            outcome=RecoveryOutcome.NEEDS_HUMAN,
            current_state=current_state,
            expected_state=expected_state,
            path_taken=path_taken,
            actions_executed=actions_executed,
            archive_path=archive_path,
            error_msg=error_msg,
        )

    @staticmethod
    def _save_screenshot(screenshot: Any, path: Path) -> None:
        """保存截图到文件 (支持 numpy ndarray / PIL Image / 字节流)。"""
        try:
            import cv2
            import numpy as np
            if isinstance(screenshot, np.ndarray):
                cv2.imwrite(str(path), screenshot)
                return
        except ImportError:
            pass

        try:
            from PIL import Image
            if isinstance(screenshot, Image.Image):
                screenshot.save(str(path))
                return
        except ImportError:
            pass

        # fallback: 当作字节流写入
        try:
            with open(path, "wb") as f:
                f.write(screenshot)
        except Exception as exc:
            logger.warning("截图保存失败: %s", exc)

    # ------------------------------------------------------------------
    # expected_state 推断 (§3.3 + §5.1,静态方法)
    # ------------------------------------------------------------------

    @staticmethod
    def infer_expected_state(
        node_config: dict,
        previous_node_chain: list[dict] | None = None,
        safe_states: list[str] | None = None,
    ) -> tuple[str, str]:
        """确定期望界面状态 (3 级优先级,详见 §3.3)。

        Args:
            node_config: 失败节点的 config
            previous_node_chain: 成功节点信息列表,元素结构 {"id": node_id, "config": node_config}。
                                 index 0 = 最早成功节点,末尾 = 最近成功节点。
                                 递归回溯时从末尾往头遍历 (最近 → 最早),取元素 ["config"] 做推断。
            safe_states: 安全状态名列表 (从 interface_states.yaml 加载)

        Returns:
            (state_name, source) — source 取值:
                - "manual": 优先级 1,来自 node_config["expected_state"] 显式标注
                - "auto_inferred": 优先级 2,直接从节点 config 路径推断 (模板类识别节点)
                - "previous_node_chain": 优先级 2,递归回溯命中成功节点链中的识别/标注节点
                - "safe_fallback": 优先级 3,降级到 safe_states[0]
        """
        # 优先级 1: 手动标注
        manual_state = node_config.get("expected_state")
        if manual_state:
            return manual_state, "manual"

        # 优先级 2a: 模板类识别节点路径推断
        # node_config 中的 node_type 字段 (pipeline JSON 中是 node_type,不是 type)
        node_type = node_config.get("node_type") or node_config.get("type")
        if node_type in _TEMPLATE_NODE_TYPES:
            template = node_config.get("template")
            if template:
                inferred = InterfaceRecoveryManager._infer_state_from_template_path(template)
                if inferred:
                    return inferred, "auto_inferred"

        # 优先级 2b: 递归回溯 (非模板识别节点 + 非识别类节点)
        if previous_node_chain:
            # 从末尾往头遍历 (最近 → 最早)
            for node_info in reversed(previous_node_chain):
                prev_config = node_info.get("config", {}) or {}
                # 找手动标注节点
                manual = prev_config.get("expected_state")
                if manual:
                    return manual, "previous_node_chain"
                # 找模板类识别节点
                prev_type = prev_config.get("node_type") or prev_config.get("type")
                if prev_type in _TEMPLATE_NODE_TYPES:
                    prev_template = prev_config.get("template")
                    if prev_template:
                        inferred = InterfaceRecoveryManager._infer_state_from_template_path(prev_template)
                        if inferred:
                            return inferred, "previous_node_chain"

        # 优先级 3: 降级到安全状态
        if safe_states:
            return safe_states[0], "safe_fallback"

        # 兜底 (safe_states 为空时,用 main_menu 作为最后防线)
        return "main_menu", "safe_fallback"

    @staticmethod
    def _infer_state_from_template_path(template_path: str) -> str | None:
        """从 template 路径推断状态名 (§3.3 PATH_STATE_MAPPING 两层结构)。

        第一层: 精确匹配 (PATH_STATE_MAPPING)
        第二层: 通配 fallback (<task>_state 规则)
        """
        if not template_path:
            return None

        # 规范化: 去掉扩展名,统一分隔符
        clean_path = template_path.replace("\\", "/")
        # 去掉扩展名
        for ext in (".png", ".jpg", ".jpeg", ".bmp"):
            if clean_path.lower().endswith(ext):
                clean_path = clean_path[: -len(ext)]
                break

        # 第一层: 精确匹配
        for path_fragment, state_name in PATH_STATE_MAPPING.items():
            if path_fragment in clean_path:
                return state_name

        # 第二层: 通配 fallback (<task>_state)
        # 取 templates/ 之后的第一级目录作为 <task> 名
        # 示例: BrownDust-II/templates/get_email/邮箱 → get_email
        parts = clean_path.split("/")
        try:
            templates_idx = parts.index("templates")
            if templates_idx + 1 < len(parts):
                task_name = parts[templates_idx + 1]
                return f"{task_name}_state"
        except ValueError:
            pass

        # 不含 templates/ 的相对路径,取第一级目录
        if len(parts) >= 2:
            # 例如 get_email/邮箱 → get_email_state
            return f"{parts[0]}_state"

        return None
