---
start_ts: 2026-08-26T20:00:00+08:00
end_ts: 2026-08-26T22:30:00+08:00
duration_min: 150
within_baseline: false
root_cause_if_over: "含 2 轮 agent 全量回归（~6min）+ backend 回归（~6min）+ RAG 语料全量重建（4min）+ 多轮真实 Chrome e2e；纯编码时长在基准内，super-linear 来自回归/实测而非实现"
---
# Windows 控制层加固与语义化 (TD-396/397/398/399/395 收敛) — spec-context 承载体

> B2 大修改 evidence 所需的决策承载记录。任务：收敛历次 Chrome 浏览器任务暴露的
> 控制层四类债务，按架构方向分层演进，不零散打补丁。

## 用户决策原文

- "Trae 电脑控制 vs GAF agent，我 gaf 得这些还能提升？或者说之后怎么不犯这种错了…有时候等在一个动作几分钟都没反应？也不停止…你说让 agent 支持'浏览器/桌面语义层操作'（对齐 Trae accessibility 思路），你自己评估下，都先评估再决定"
- "spec 先？从架构方向修改好点"（批准立项 spec，从架构方向改，不零散打补丁）
- 背景基准事实：computer-use 手动 set_value+Enter 20 秒闭环（百度搜索→返回）；GAF agent 等价任务多轮失败，失败全在"模拟按键 + 像素截图"层。

## N151 5 步法评估

1. **架构盘点**：控制层现状 = 像素/按键层（key_press/text_input/click/template/OCR 验证）为主，Windows 设备经 `platforms/windows/input*.py`；超时保护被节点显式 timeout gated（默认主线程直跑）。
2. **识别反模式**：① 无限挂起无兜底（TD-399，exec 28 实锤）；② 输入注入不可靠（TD-398 组合键泄漏）；③ 截图是全屏而非目标窗口（TD-397 窗口可见性依赖）；④ 工具类正则过宽误报（TD-395）。
3. **A/B/C 备选**：
   - A) 逐节点打超时补丁 + 修模拟按键 → 治标，窗口可见性依赖仍在（拒绝）
   - B) 新增 UIAutomation 语义通道节点（accessibility 注入，无需焦点/可见）+ 统一超时护栏 + 保留像素层 → 分层演进，对齐 Trae accessibility 思路（采用）
   - C) 用 Trae 电脑控制替换 GAF agent 输入层 → 架构外泄、跨产品耦合（拒绝）
4. **拒绝双套/最小化**：语义层仅新增能力，不迁移存量游戏任务；不替换像素层（游戏主路径不扰）。
5. **AI 自决边界**：用户已批准立项；实施均在前述架构方向内，自决推进。

## N167 七维度评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 1 架构长远性 | 9 | 语义层与像素层分层并存，后续桌面/浏览器场景走 accessibility 通路 |
| 2 全局归一化 | 8 | 超时护栏跨两层统一（线程池 + Future + MAX_STEP_TIMEOUT） |
| 3 一致性 | 8 | uia_* 节点契约（截图模式/前置要求/能力边界）纳入 authoring-guide §2.8 |
| 4 可测试性 | 8 | 超时路径注入 sleep 可测；uia 节点在 Chrome 实测闭环 |
| 5 代码质量 | 8 | ruff 全过；既有测试更新为 key_combo / bring_to_foreground 契约 |
| 6 性能 | 7 | 复用线程池无每节点新建开销；语义节点单步 <100ms |
| 7 长期维护成本 | 8 | 输入可靠性问题从"修按键"转为"换通道根治"，降低同根因复发 |

总分 56/70（≥19 且领先），自决采纳。

## 关键实施决策

- **P1 统一超时（TD-399）**：不再 `if "timeout" in node.config` 分支；所有节点经复用线程池执行，`future.result(timeout=step_timeout)`，默认 `MAX_STEP_TIMEOUT`，保留显式 timeout 覆盖；超时后 `_step_cancel_event` + 3s 宽限期（TD-353）。
- **P2 语义通道（TD-398 残根）**：`platforms/windows/uia/uia_session.py`（uiautomation 包 COM 包装）+ `engine/nodes/uia_control.py` 三个节点 `uia_set_value / uia_invoke / uia_get_state`，ValuePattern/InvokePattern 注入，不依赖焦点/可见。
- **P3 语义化 Chrome 场景**：任务 19 重写为 `uia_set_value(地址栏) → key_press(enter) → uia_get_state(验证) → key_press(alt+home)`，exec 33 success 7.8s；uia_get_state 替代 OCR 截图验证。
- **P4 工具类（TD-395）**：CANVAS_LEGACY_RULES 收窄为带引号键访问 + 目录级白名单（backend/scheduler/、monitor/handlers、script_dsl 等）；NODE_TYPE_CODE_RULES 双读豁免（estimator/validators）；移除 warns[:10] 截断；103 warns → 0。
- **回归 stumble**：agent `test_engine_nodes_smoke_action`（key_combo 契约）与 `test_windows_input_pseudo_background`（bring_to_foreground 契约）测试未随 -/- 更新 → 本轮一并修正；backend 3 个 retrieval 命中率测试失败为语料陈旧（增量索引滞后于日内大量代码变更），全量重建 ChromaDB 语料后 5/5 通过。

## N173 用时字段

- start_ts: 2026-08-26T20:00:00+08:00
- end_ts: 2026-08-26T22:30:00+08:00
- duration_min: 150
- within_baseline: false（原因见 frontmatter root_cause_if_over）