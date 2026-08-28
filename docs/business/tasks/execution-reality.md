---
summary: GAF 任务执行引擎指南（单一 Pipeline 引擎）
applies_to: ['backend', 'agent', 'design', 'frontend']
key_decisions:
  - spec-2026-07-27-execution-path-unification 完成后 chain 路径已废弃
  - 所有任务统一走 PipelineEngine（线性 nodes 或图 nodes+edges）
  - state_machine 模式保留（走独立 Python 模块路径）
last_updated: 2026-08-02 (spec-2026-08-02-backend-execution-unification)
---

# GAF 任务执行引擎指南

> 版本：2.0 | 日期：2026-07-27 | 状态：spec-2026-07-27-execution-path-unification 完成后归一化
>
> **重大变更**：原"双轨执行路径"（chain / pipeline）已归一化为单一 PipelineEngine。
> 旧 chain 任务由 migration 0049 自动迁移为 pipeline schema（线性 nodes）。

## 0. 为什么需要这份文档

spec-2026-07-27-execution-path-unification 之前，GAF 有两条执行路径（chain / pipeline），
能力不对等且代码重复。归一化后：
- **chain 路径整体废弃**：`_execute_chain` / `_execute_step` / `_run_action` 等方法已删除
- **PipelineEngine 吸收 chain 优点**：PipelineNode 支持 `pre_verify` / `post_verify` / `retry` / `fallback` / `continue_on_error` 字段
- **线性模式**：pipeline JSON 无 edges 时按 nodes 列表顺序自动链接（等价于原 chain 顺序执行）
- **state_machine 保留**：仍走独立 Python 模块路径（task_definition 含 `module` 字段时分发）

本指南是任务执行的**权威参考**。

---

## 1. 执行路径总览

| 维度 | Pipeline（默认） | state_machine（特殊） |
|------|------------------|----------------------|
| **数据模型** | `Task.task_definition` (JSONField, 含 `nodes`) | `Task.task_definition` (JSONField, 含 `module`) |
| **Backend 入口** | `TaskViewSet.execute` / `PipelineViewSet.execute` → `dispatch_task`；TaskChain 节点 → `dispatch_task`（`force_agent_id` 固定链 Agent, B1 2026-08-27） | 同左 → `dispatch_task` |
| **Agent 接收** | `MessageHandler.handle_task_assign`（统一入口，`handle_pipeline_execute` 已删除） | 同左 |
| **Agent 执行** | `TaskOrchestrator.execute_pipeline` → `PipelineEngine` | `TaskOrchestrator.execute_pipeline` → `_execute_state_machine_dispatch` |
| **CLI 工具** | `manage.py run_pipeline <id> [--wait]` | 同左（`task_definition.module` 字段分发） |
| **支持动作** | ✅ 48 个 agent 注册节点（后端 catalog 52，含 4 类 legacy）（含识别/控制流/设备生命周期） | ✅ Python 模块自定义（`build_state_machine` 工厂） |
| **节点内控制流** | ✅ `pre_verify` / `post_verify` / `retry` / `fallback` / `continue_on_error` | 由 Python 代码自行实现 |
| **线性模式** | ✅ 无 edges 时按 nodes 顺序执行 | N/A |
| **图模式** | ✅ nodes + edges DAG（branch/goto/loop） | N/A |
| **断点续跑** | ✅ `serialize()` / `restore_context()` | ❌ 不支持 |
| **前端编辑器** | ✅ `/tasks/pipeline` React Flow 图编辑器 + `/tasks/:taskId/edit` JSON 编辑器 | ✅ `/tasks/:taskId/edit` JSON 编辑器 |
| **执行监控** | ✅ `/ops/executions` | ✅ `/ops/executions`（同一页面） |
| **适用场景** | 99% 任务（含 BD2 迁移、模板/OCR/分支） | 需要复杂 Python 逻辑的状态机（罕见） |

> **chain 模式已废弃**：原 `execution_mode='chain'` 的任务由 migration 0049 转为
> `execution_mode='pipeline'`，task_definition 从 `{"steps": [...]}` 转为 `{"nodes": [...]}`。
> `Task.ExecutionMode` 枚举仅保留 `PIPELINE` 和 `STATE_MACHINE`。

---

## 2. Pipeline 路径（48 个 agent 注册节点（后端 catalog 52，含 4 类 legacy））

### 2.1 支持的节点类型

`agent/src/engine/nodes/` 下注册的节点（通过 `@register_node`）：

| 类别 | 节点 |
|------|------|
| **检测/识别** | `template_match`, `template_match_any`, `ocr`, `color_detect`, `feature_match`, `neural_network`, `nn_classifier`, `nn_regressor` |
| **复合匹配** | `and_match`, `or_match`, `custom_match` |
| **输入动作** | `click`, `long_press`, `swipe`, `swipe_until`, `multi_swipe`, `multi_scroll`, `multi_touch`, `key_press`, `text_input`, `wheel`, `direct_hit` |
| **Maa 协议动作** | `jump_back`, `wait_freezes`, `next`, `stop`, `anchor` |
| **控制流** | `branch`, `goto`, `loop`, `sub_pipeline`, `wait`, `sort_select` |
| **设备/应用生命周期** | `start_app`, `stop_app`, `device_control`, `random_delay` |
| **通知/监控** | `notify`, `monitor`（✅ Phase 1 接入 PopupHandler；`context.monitor_manager` 缺失或 handler 异常时返回 `fail_result` 暴露问题，不静默 Mock 回退） |

> 未列入前表的已注册节点: `roi_resolver` / `python_call` / `log_message`(2026-08-26 注册) / UIAutomation 语义 6 类(`uia_set_value`/`uia_invoke`/`uia_get_state`/`uia_get_window_title`/`uia_select`/`uia_scroll`)。

### 2.2 节点内控制流字段（吸收原 chain step 字段）

每个 PipelineNode 支持以下可选字段：

| 字段 | 类型 | 作用 |
|------|------|------|
| `pre_verify` | `dict` | 节点执行前的强验证（template/color/text 等），失败则跳过节点 |
| `post_verify` | `dict` | 节点执行成功后的验证，失败则标记节点失败 |
| `retry` | `dict` | 重试配置：`max_retries` / `base_delay` / `backoff_factor`（指数退避） |
| `fallback` | `dict` | 节点失败后的回退动作：`action` + `params`（inline dict） |
| `continue_on_error` | `bool` | 节点失败时是否继续下一个节点（默认 False，失败即终止 pipeline） |

### 2.3 线性模式（替代原 chain）

pipeline JSON 无 `edges` 字段时，`PipelineGraph.from_dict` 按 `nodes` 列表顺序自动生成 next 链：

```json
{
  "nodes": [
    {"id": "click_login", "node_type": "click", "config": {"x": 100, "y": 200}, "post_verify": {"type": "template", "template": "main.png"}},
    {"id": "wait_load", "node_type": "wait", "config": {"seconds": 2}},
    {"id": "click_enter", "node_type": "click", "config": {"x": 300, "y": 400}}
  ]
}
```

等价于显式 edges：
```json
{
  "edges": [
    {"from_node": "click_login", "to_node": "wait_load"},
    {"from_node": "wait_load", "to_node": "click_enter"}
  ]
}
```

### 2.4 图模式（DAG）

支持 `branch` / `goto` / `loop` 等控制流节点，详见 §2.1 节点列表。

### 2.5 pipeline JSON 示例（BD2 get_guild 等价）

```json
{
  "name": "get_guild",
  "description": "公会奖励领取",
  "entry_node": "back_to_main",
  "nodes": [
    {
      "id": "back_to_main",
      "node_type": "template_match",
      "params": {
        "template": "public/主界面",
        "roi": [1720, 20, 120, 70],
        "threshold": 0.8
      },
      "next_node_id": "click_guild_icon"
    },
    {
      "id": "click_guild_icon",
      "node_type": "template_match",
      "params": {
        "template": "get_guild/公会标识",
        "roi": [310, 111, 130, 100],
        "threshold": 0.8,
        "click_on_match": true
      },
      "next_node_id": "verify_guild_shop"
    }
  ]
}
```

---

## 3. state_machine 模式（特殊场景）

### 3.1 现状

- ✅ Backend `Task.execution_mode` choices 含 `state_machine`
- ✅ Backend `Task.task_definition` 可存状态机 JSON（含 `module` 字段）
- ✅ Frontend `Tasks/Editor.tsx` 有 state_machine tab
- ✅ `agent/src/core/state_machine.py` 的 `StateMachine` 类实现完整
- ✅ **spec-2026-07-27 阶段 6 起**：`execute_pipeline` 检测 `task_definition.module` 字段
  自动分发到 `_execute_state_machine_dispatch`（设备切换沿用原 chain 语义）

### 3.2 task_definition JSON 示例

```json
{
  "module": "custom_tasks.browndust.guild_fsm",
  "max_iterations": 1000
}
```

模块需暴露 `build_state_machine(device_manager, image_processor) -> StateMachine` 工厂函数。

### 3.3 何时用 state_machine

- ✅ 需要复杂 Python 逻辑（无法用节点表达的场景）
- ✅ 已有 Python StateMachine 实现的遗留任务
- ❌ 不推荐新任务使用 — PipelineEngine 的 branch+goto 已能覆盖大多数状态机语义

### 3.4 用 Pipeline 实现状态机语义（推荐）

用 `branch` + `goto` 节点实现状态机：

```json
{
  "nodes": [
    {
      "id": "check_state",
      "node_type": "template_match",
      "params": {"template": "main_menu", "threshold": 0.8},
      "next_node_id": "branch_state"
    },
    {
      "id": "branch_state",
      "node_type": "branch",
      "params": {
        "conditions": [
          {"if_matched": true, "goto": "in_game"},
          {"if_matched": false, "goto": "launch_app"}
        ]
      }
    },
    {
      "id": "launch_app",
      "type": "start_app",
      "params": {"package": "com.example.game"},
      "next_node_id": "check_state"
    },
    {
      "id": "in_game",
      "type": "next",
      "next_node_id": null
    }
  ]
}
```

---

## 4. BD2 任务迁移指南

### 4.1 BD2 ChainManager 调用 → GAF Pipeline 节点映射

| BD2-AUTO ChainManager | GAF Pipeline 节点 | 备注 |
|-----------------------|-------------------|------|
| `chain.template_click(name, roi=...)` | `template_match` + `click_on_match: true` | 模板匹配后点击 |
| `chain.text_click(text, roi=...)` | `ocr` + `click_on_match: true` | OCR 识别后点击 |
| `chain.color_click(color, roi=...)` | `color_detect` + `click_on_match: true` | 颜色匹配后点击 |
| `chain.pos_click(pos)` | `click` | 直接坐标点击 |
| `chain.swipe(start, end, duration)` | `swipe` | 滑动 |
| `chain.key_press(key)` | `key_press` | 按键 |
| `chain.text_input(text)` | `text_input` | 输入文本 |
| `chain.sleep(ms)` | `wait` | 等待 |
| `chain.if_exists(template)` | `branch` + `template_match` | 分支 |
| `chain.with_pre_verify(...)` | 节点 `pre_verify` 字段 | 前置验证（spec-2026-07-27 阶段 2 吸收） |
| `chain.custom_step(fn)` | `sub_pipeline` 或展开为节点序列 | 自定义函数需重写 |

### 4.2 BD2 ROI 坐标系

BD2 ROI 基于 1920×1080 基准分辨率。GAF Pipeline 的 `roi` 字段也用基准坐标，由 Agent 端 `CoordinateTransformer` 在运行时转换。

### 4.3 BD2 `back_to_main` 助手

BD2 用 Python 函数实现 `back_to_main`，GAF 需展开为节点序列：

```
1. template_match(public/主界面) → 命中则结束
2. template_match(public/地图标识) + click → 回主界面
3. template_match(public/返回键1) + click → 回退
4. key_press(escape) → 关弹窗
5. key_press(h) → 主页快捷键
6. OCR("结束游戏") + key_press(escape) → 处理结束游戏弹窗
7. 循环 1-6 直到主界面出现或超时
```

可定义为可复用的 `sub_pipeline` 节点。

### 4.4 迁移步骤

1. **导入模板**：BD2 `templates/**/*.png` → GAF `resources_template` 表
2. **创建 ResourcePack**：`BrownDust-II`
3. **构造 Pipeline JSON**：按 §2.5 格式，参考 §4.1 映射表
4. **绑定 GameAccount + Device**
5. **执行验证**：`POST /api/v2/tasks/<pk>/execute/`

---

## 5. 前端编辑器现状

| 编辑器 | 路由 | 状态 | 说明 |
|--------|------|------|------|
| `TaskFormModal` | `/tasks` 弹窗 | ✅ 可用 | 编辑 Task 基础字段（name/desc/mode/accounts/devices），不能编辑 nodes |
| `PipelineEditorPage` | `/tasks/pipeline` | ✅ 可用 | React Flow 图编辑器，编辑 Pipeline.graph_data |
| `Tasks/Editor.tsx` | `/tasks/:taskId/edit` | ✅ 可用 | pipeline/state_machine JSON 编辑器 |

### 5.1 推荐

- **复杂任务**：用 `/tasks/pipeline` 的 Pipeline 编辑器（图编辑）
- **简单 Task**：用 `/tasks` 的 TaskFormModal（仅基础字段）+ 直接编辑 JSON
- **state_machine 编辑**：用 `/tasks/:taskId/edit` 的 `Tasks/Editor.tsx`

---

## 6. 相关文件

### Backend
- [models.py](file:///d:/code/GAF/backend/tasks/models.py) — Task 模型（execution_mode: pipeline / state_machine）
- [views.py](file:///d:/code/GAF/backend/tasks/views.py) — Task API（含 validate）
- [pipeline/views.py](file:///d:/code/GAF/backend/pipeline/views.py) — PipelineViewSet.execute（已改调 `dispatch_task`）
- [tasks.py](file:///d:/code/GAF/backend/tasks/tasks.py) — `dispatch_task` Celery 任务（统一入口，支持 `task=None` Pipeline 执行）
- [run_pipeline.py](file:///d:/code/GAF/backend/pipeline/management/commands/run_pipeline.py) — CLI 工具（`manage.py run_pipeline <id>`）
- [0049_chain_to_pipeline_unification.py](file:///d:/code/GAF/backend/tasks/migrations/0049_chain_to_pipeline_unification.py) — chain→pipeline 数据迁移

### Agent
- [orchestrator.py](file:///d:/code/GAF/agent/src/core/orchestrator.py) — `execute_pipeline`（统一入口，含 state_machine 分发）
- [pipeline_engine.py](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py) — PipelineEngine 图执行器
- [node.py](file:///d:/code/GAF/agent/src/engine/node.py) — PipelineNode（含 pre_verify/retry/fallback 等字段）
- [parser.py](file:///d:/code/GAF/agent/src/engine/parser.py) — Pipeline JSON 解析器（含线性模式）
- [nodes/](file:///d:/code/GAF/agent/src/engine/nodes/) — 48 个 agent 注册节点（后端 catalog 52，含 4 类 legacy）实现
- [handler.py](file:///d:/code/GAF/agent/src/client/handler.py) — WebSocket 消息处理（`handle_pipeline_execute` 已删除，统一走 `handle_task_assign`）
- [connection.py](file:///d:/code/GAF/agent/src/client/connection.py) — WebSocket 连接（`handler_map` 中 `pipeline.execute` 已移除）

### Frontend
- [PipelineEditorPage.tsx](file:///d:/code/GAF/frontend/src/pages/Tasks/PipelineEditor/PipelineEditorPage.tsx) — Pipeline 图编辑器
- [Tasks/index.tsx](file:///d:/code/GAF/frontend/src/pages/Tasks/index.tsx) — Task 列表页
- [Editor.tsx](file:///d:/code/GAF/frontend/src/pages/Tasks/Editor.tsx) — Task JSON 编辑器

---

## 7. 反思与演进历史

- **v1.0（2026-05）**：双轨设计 — Task chain 和 Pipeline 并存，能力差距大
- **v1.2（2026-07-22）**：Phase 7 接入 state_machine 分发，但 chain/pipeline 双轨仍并存
- **v2.0（2026-07-27）**：spec-2026-07-27-execution-path-unification 完成 —
  chain 路径整体废弃，PipelineEngine 吸收 chain 优点（节点内控制流字段），
  线性模式支持无 edges 的 nodes 列表，state_machine 分发统一到 execute_pipeline
- **v2.1（2026-08-02）**：spec-2026-08-02-backend-execution-unification 完成 —
  Backend 端执行入口归一化，`PipelineViewSet.execute` 改调 `dispatch_task`，
  删除 agent `handle_pipeline_execute`，新建 `run_pipeline` CLI 工具，
  `_check_exec*.py` ad-hoc 脚本清理

### 7.1 归一化的关键决策

1. **不写 chain→pipeline 编译器**：chain schema 直接废弃，老任务一次性数据迁移
2. **PipelineNode 字段扩展**：pre_verify/post_verify/retry/fallback/continue_on_error
   下沉到基类，所有节点类型均可使用
3. **线性模式**：无 edges 时 Parser 按 nodes 顺序自动链接，等价于原 chain 顺序执行
4. **state_machine 保留**：仍走独立 Python 模块路径，但分发统一到 execute_pipeline
   （通过 task_definition.module 字段检测）

### 7.2 相关 spec

- [spec-2026-07-27-execution-path-unification](../../specs/archived/2026-07/2026-07-27-execution-path-unification.md) — 执行路径归一化设计
- spec-2026-08-02-backend-execution-unification（历史 spec 文档未留存） — Backend 执行入口归一化
- [chain-mode-structured-logging.md](../../architecture/agent/chain-mode-structured-logging.md) — chain 接入 StructuredLogger 的临时方案（已废弃）
