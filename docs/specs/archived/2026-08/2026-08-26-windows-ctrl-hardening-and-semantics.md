---
summary: Windows 控制层加固与语义化 — 收敛 TD-396/397/398/399/395 的控制层债务，按架构方向分阶段根治
applies_to: ['agent', 'backend']
applies_to_code_paths:
  - agent/src/engine/pipeline_execution.py
  - agent/src/platforms/windows/
  - agent/src/devices/base.py
  - agent/src/client/handler.py
  - backend/tasks/tasks.py
  - docs/archive/active-tech-debt.md
last_updated: 2026-08-26
archived: true
---

# Windows 控制层加固与语义化 (TD-396/397/398/399/395 收敛)

> 决策（2026-08-26 用户）：先立 spec、从架构方向修改；本轮不零散打补丁。
> 用户已可随时用 Trae 电脑控制代看桌面，语义化作为 GAF 侧架构演进而非临时救急。
> 基准事实：computer-use 手动 set_value+Enter 20 秒闭环（百度搜索→返回）；GAF agent 等价任务多轮失败，失败全在"模拟按键 + 像素截图"这一层（TD-398 证据链）。

## 阶段状态表

| 阶段 | 状态 | 完成时间 | commit | 验收 evidence |
|------|------|----------|--------|---------------|
| P0 债务收尾（396 关条、397 并入 398、395 更新） | ✅ | 2026-08-26 | - + 前链 -/-/-/-/-/- | active-tech-debt 清单收敛；TD-396 标记待 10 次执行最终确认 |
| P1 节点级超时兜底（TD-399） | ✅ | 2026-08-26 | - | 无 timeout 节点统一走复用线程池 + MAX_STEP_TIMEOUT 兜底（pipeline_execution.py）；agent 全套 2082 passed |
| P2 语义层抽象（UIAutomation 通道 + 能力声明） | ✅ | 2026-08-26 | - | uia_set_value/uia_invoke/uia_get_state 节点创建 + 注册（uia_control.py + platforms/windows/uia/）；Chrome 实测 set_value 成功 |
| P3 语义化 Chrome 场景（任务 19 重写并闭环） | ✅ | 2026-08-26 | - | 任务 19（语义版）exec 33 success，7.8s ≤ 20s，含 Alt+Home 返回；uia_get_state 替代 OCR 截图验证 |
| P4 工具类清理（TD-395 schema 误报） | ✅ | 2026-08-26 | - | check_schema_unification --full：103 warns → 0 errors, 0 warns；warns[:10] 截断移除 |
| P5 测试 + 全量回归 + 提交 | ✅ | 2026-08-26 | - | agent 2082 passed / backend gaf_ai+tasks 718 passed / ruff 全过 / governance 17 checks |

## 背景

2026-08-26 Chrome 百度任务 e2e 暴露控制层四类真实缺陷（每类均经 py-spy / 截图 OCR / computer-use 对照证实）：

1. **无限挂起无兜底**：pipeline 节点超时（`pipeline_execution.py` `if "timeout" in node.config`）只对显式配 timeout 的节点生效；key_press/click/text_input 等默认主线程直跑，任何未知阻塞永久卡（exec 28 卡 n1 截图→恢复引擎分钟级兜底）。→ **TD-399**
2. **输入注入不可靠**：组合键 Ctrl+L 泄漏 'l'、特殊字符注入错乱（TD-398，组合键已修 -）。→ 语义化根治残留。
3. **窗口可见性依赖**：截图是"显示器全屏"而非目标窗口；Chrome 不在前台可见则 OCR 验证必然失败（TD-397/398 残留）。
4. **工具类误报**：check_schema_unification 过宽（TD-395，P3）。

## 架构方向

控制层分层演进（与现有游戏路径并存，不替换）：

```
┌─ 语义层（新增）──────────────────────────────┐
│  uia_set_value / uia_invoke / uia_get_state   │  ← accessibility 注入，无需焦点/可见
└───────────────────────────────────────────────┘
┌─ 现有像素/按键层（保留，游戏主路径）──────────────┐
│  key_press / text_input / click / wait / template│
└───────────────────────────────────────────────┘
┌─ 执行护栏（P1，跨两层）────────────────────────┐
│  所有节点默认 wall-clock 超时（线程池 + Future） │
└───────────────────────────────────────────────┘
```

- **对撞策略**：P1 让"任何单点卡死"都变成"节点超时→fail→恢复引擎"，两层通用。
- **对语义层**：P2 在 agent 增加 UIAutomation 通道节点；P3 用语义节点重写浏览器场景任务，绕开"模拟按键+像素"脆弱链。

## 修复方案

### P0 债务收尾 (docs/archive/active-tech-debt.md)
- TD-396：置"✅ 已修复，待 10 次执行最终确认后可迁移 fixed.md"；追加本轮 8 个 commit 哈希。
- TD-397：标记"并入 TD-398（根因实为输入注入/窗口可见性）"。
- TD-398：更新"组合键已修 (-)、截图已护栏 (-)；像素链验证环节交由 P2/P3 语义层替代"。
- TD-395：保持 🔧，注明接修阶段=P4。

### P1 节点级超时兜底 (TD-399)
`agent/src/engine/pipeline_execution.py`：
- **不再用 `if "timeout" in node.config` 分支**；统一：所有节点经复用线程池执行，`future.result(timeout=step_timeout)`（默认 `MAX_STEP_TIMEOUT`，保留节点显式 timeout 可覆盖）。
- 保留超时后的 `_step_cancel_event` + 3s 宽限期逻辑（TD-353 已有）。
- 性能回归防线：线程池复用现有 `_reusable_executor`（2026-08-02 已建，无每节点新建开销）；主线程直跑仅保留在无超时风险且已验证的纯计算路径（如变量渲染），由阶段验收数据支撑。
- 验证：按一个关键节点注入 sleep(60) → 节点在 `MAX_STEP_TIMEOUT` 内 fail，pipeline 继续/终止而非永久挂。

### P2 语义层抽象（UIAutomation 通道）
`agent/src/platforms/windows/uia/`（新增）：
- `uia_session.py`：Windows UIAutomation 客户端（基于 uiautomation/pywin32 之一，先确认依赖是否已在 env；无则用纯 ctypes 最小实现：IUIAutomation COM 定位控件 + ValuePattern SetValue / InvokePattern Invoke）。
- 节点类型（`engine/nodes/uia_*.py`）：
  - `uia_set_value`：按自动化 id / name 定位 edit 控件并 SetValue（不依赖焦点）。
  - `uia_invoke`：对按钮 Invoke。
  - `uia_get_state`：读取控件 value/name/rect/visibility，写回 context 变量（供 wait/校验）。
- 设备能力声明：`devices/base.py` 或 handler 增加 `capabilities['uia']`，任务 SDL 可按能力路由。
- 契约：新增节点类型同步更新 authoring-guide §2.8（截图模式/前置要求/能力边界）。

### P3 语义化 Chrome 场景
- 任务 19 重写（新任务或改造）：
  - `uia_set_value(地址栏, www.baidu.com)` → `uia_invoke(回车/导航)` 或 key_press(enter)（已修组合）→ `uia_get_state` 确认 URL/标题含 baidu（替代 OCR 截图验证）→ `key_press(alt+home)`。
  - 目标：成功且 ≤20s；截图仅作 debug 佐证，不再作为成败 gate。
- 若 UIA 对 Chrome 地址栏定位不可行，回退：标题匹配节点（读取前台窗口标题含 baidu）作为验证。

### P4 工具类 (TD-395)
- `scripts/hooks/check_schema_unification.py`：CANVAS_LEGACY_RULES 收窄 + 白名单（recovery_engine/monitor/handlers/script_dsl）；NODE_TYPE_CODE_RULES 接受双读；去掉 `warns[:10]` 截断或打印总数。
- 验收：`--full` 零误报。

## 验证标准
- P1：模拟卡死节点在 MAX_STEP_TIMEOUT 内 fail；agent 全套 pytest + ruff 通过。
- P2：uia_set_value/uia_get_state 节点在 Chrome 上执行成功（side-effect 测试脚本）。
- P3：任务 19（语义版）一次 success ≤20s（含 Alt+Home 返回）。
- P5：backend + agent 全量回归（backend gaf_ai 62 + tasks 61 + agent suites）通过；`git commit` 走 governance 17 checks。

## 不做什么（边界）
- 不替换现有像素/按键层（游戏主路径不扰）。
- 语义层仅新增能力，不迁移存量游戏任务。
- 不做 agent 输入层的 accessibility 全量替换 —— 只加"语义节点"通路，供浏览器/桌面场景选用。