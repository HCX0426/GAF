---
summary: GAF Pipeline JSON 作者指南 — 39 节点类型目录 + 通用字段 + BD2 迁移示例
applies_to: ['backend', 'agent', 'design']
key_decisions:
  - 节点类型目录（48 类，后端 catalog 52 含 legacy 4）
  - 通用生命周期字段
  - BD2 get_guild 完整 Pipeline JSON 示例
  - 前后端节点类型差异
last_updated: 2026-07-22
---

# GAF Pipeline JSON 作者指南

> 版本：1.2 | 日期：2026-07-22 | 配套：[task-execution-reality.md](execution-reality.md) | 修订：补充 swipe_until / template_match_any 节点，修正 pipeline API 路径

## 0. 定位

本文档是 **Pipeline JSON 的作者手册**：列出全部 48 个节点类型（后端 catalog 52 含 4 类 legacy）、通用生命周期字段、常见编排模式，并提供 BD2 `get_guild` 的完整 Pipeline JSON 示例。

**适用场景**：手写 Pipeline JSON、把 BD2 链式任务翻译成 Pipeline、校对前端编辑器产物。

**不适用**：链式任务（Task chain，6 个基础 action）— 那是 `custom-task-design.md` 的范畴。

---

## 1. JSON 顶层结构

```json
{
  "nodes": [
    {
      "node_id": "node_1",
      "node_type": "template_match",
      "next_node_id": "node_2",
      "config": { /* 节点专属字段 */ },
      "pre_delay": 0.5,
      "post_delay": 0.0,
      "repeat": 1,
      "continue_on_error": false
    }
  ]
}
```

### 1.1 必填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `node_id` | string | 节点唯一 ID，被 `next_node_id` / `branch.cases[].next_node_id` / `goto.target` / `loop.body_start_node_id` 引用 |
| `node_type` | string | 节点类型，见 §2 目录（parser 也接受 `type` / `action` 作为同义词，但**作者应统一用 `node_type`**） |

### 1.2 流转字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `next_node_id` | string \| null | 顺序执行的下一节点；`null` 或缺省表示流程结束 |
| `next_node_id_on_success` | string \| null | （可选）成功时的下一节点，覆盖 `next_node_id` |
| `next_node_id_on_failure` | string \| null | （可选）失败时的下一节点，覆盖 `next_node_id` |

### 1.3 通用生命周期字段（所有节点共享）

> 来自 Maa 协议，在 `worker/src/engine/pipeline_engine.py` 的 `_apply_pre_lifecycle` / `_apply_post_lifecycle` 中实现，**对所有节点类型生效**。

| 字段 | 类型 | 默认 | 作用 |
|------|------|------|------|
| `pre_delay` | float (秒) | 0 | 节点执行**前**等待时长 |
| `post_delay` | float (秒) | 0 | 节点执行**后**等待时长 |
| `pre_wait_freezes` | float \| bool \| object | false | 节点执行前等待画面静止（秒数=超时；true=默认 5s；object=精细配置） |
| `post_wait_freezes` | float \| bool \| object | false | 节点执行后等待画面静止 |
| `repeat` | int | 1 | 节点重复执行次数 |
| `repeat_until_failure` | bool | false | 重复直到节点失败（与 `repeat` 互斥语义，引擎按 `repeat` 循环） |
| `continue_on_error` | bool | false | 节点失败时是否继续下一节点（false=整体失败） |

### 1.4 控制流专属字段

`branch` / `goto` / `loop` / `sub_pipeline` / Maa 协议节点有专属字段，见 §2 对应小节。

---

## 2. 节点类型目录（48 类，后端 catalog 52 含 legacy 4）

> 来源：`worker/src/engine/nodes/__init__.py` 中 `@register_node` 装饰器注册的全部类型。
> 状态标记：✅ 生产可用 | 🔧 Mock/骨架 | ⚠️ 前端未支持

### 2.1 画面识别（8 类）

| node_type | 文件 | 状态 | 关键 config 字段 |
|-----------|------|------|-----------------|
| `template_match` | `template_match.py` | ✅ | `template`（资源路径）、`roi`（[x,y,w,h]）、`threshold`（0-1）、`click_on_match`（bool）、`timeout`（秒） |
| `template_match_any` | `template_match_any.py:30` | ⚠️ 前端未支持 | `templates`（数组，按序尝试）、`threshold`、`roi`、`click_on_match`、`method`、`scale` — 多模板任一匹配，首个命中即返回 |
| `ocr` | `ocr.py` | ✅ | `engine`（rapid/paddle/onnx_paddle/dgocr）、`text`/`texts`（待匹配文本）、`roi`、`expected`、`click_on_match` |
| `color_detect` | `color_detect.py` | ✅ | `color`（[r,g,b]）、`roi`、`tolerance`、`count`（期望像素数） |
| `feature_match` | `feature_match.py` | ✅ | `template`、`roi`、`method`（ORB/SIFT）、`min_matches` |
| `neural_network` | `neural_network.py` | ✅ | `model`、`input`、`expected` |
| `nn_classifier` | `nn_recognition.py:87` | ⚠️ 前端未支持 | `model`、`roi`、`classes`、`expected` |
| `nn_regressor` | `nn_recognition.py:192` | ⚠️ 前端未支持 | `model`、`roi`、`expected_range` |

### 2.2 复合匹配（3 类，⚠️ 前端全部未支持）

| node_type | 文件 | 作用 |
|-----------|------|------|
| `and_match` | `composite_match.py:45` | 多个子匹配全部成立 |
| `or_match` | `composite_match.py:112` | 任一子匹配成立 |
| `custom_match` | `composite_match.py:180` | 自定义 Python 函数 |

### 2.3 输入操作（11 类）

| node_type | 文件 | 状态 | 关键 config 字段 |
|-----------|------|------|-----------------|
| `click` | `click.py` | ✅ | `x`、`y`（或 `template`+`roi` 定位后点击） |
| `direct_hit` | `direct_hit.py:29` | ⚠️ 前端未支持 | `x`、`y`（绕过匹配直接点击） |
| `key_press` | `key_press.py` | ✅ | `key`（如 'Enter'、'Escape'） |
| `long_press` | `long_press.py` | ✅ | `x`、`y`、`duration`（秒） |
| `swipe` | `swipe.py` | ✅ | `start`、`end`（[x,y]）、`duration` |
| `swipe_until` | `swipe_until.py:32` | ⚠️ 前端未支持 | `templates`（候选模板数组）、`threshold`、`click_on_match`、`roi`、`x1`/`y1`/`x2`/`y2`（滑动起止）、`duration`（ms）、`max_swipes`、`delay_between` — 循环滑动直到任一模板匹配 |
| `multi_swipe` | `multi_swipe.py:29` | ⚠️ 前端未支持 | `swipes`（数组，每项 {start,end,duration}） |
| `multi_scroll` | `multi_scroll.py:33` | ⚠️ 前端未支持 | `scrolls`（数组） |
| `multi_touch` | `multi_touch.py:39` | ⚠️ 前端未支持 | `touches`（数组，{action: down/move/up, contact, x, y, pressure}） |
| `text_input` | `text_input.py` | ✅ | `text`（字符串） |
| `wheel` | `wheel.py:31` | ⚠️ 前端未支持 | `x`、`y`、`delta`、`scroll_count` |

### 2.4 Maa 协议动作（5 类，⚠️ 前端全部未支持）

> 来自 MaaFramework 协议，由 `pipeline_engine.py` 特殊处理。详见 `docs/analysis/GAF-vs-MaaFramework-analysis.md`。

| node_type | 文件 | 作用 |
|-----------|------|------|
| `jump_back` | `maa_actions.py:38` | 跳回前一个节点（设置 `_jump_back_target` 上下文） |
| `wait_freezes` | `maa_actions.py:110` | 等待画面静止 |
| `next` | `maa_actions.py:210` | 覆盖 `next_node_id`（设置 `_next_override`） |
| `stop` | `maa_actions.py:269` | 设置 `_stop_requested`，引擎在下一个安全点退出 |
| `anchor` | `maa_actions.py:322` | 锚点标记，配合 `jump_back` 使用 |

### 2.5 控制流（6 类）

| node_type | 文件 | 状态 | 关键 config 字段 |
|-----------|------|------|-----------------|
| `branch` | `branch.py` | ✅ | `cases`（数组，{condition, next_node_id}）、`default_next_node_id` |
| `goto` | `goto.py` | ✅ | `target`（目标 node_id） |
| `loop` | `loop.py` | ✅ | `body_start_node_id`、`body_end_node_id`、`max_iterations`、`exit_condition` |
| `sub_pipeline` | `sub_pipeline.py` | ✅ | `pipeline_id`（引用另一个 Pipeline）、`params`（传参） |
| `wait` | `wait.py` | ✅ | `seconds`（秒数）、`mode`（'fixed'/'random'） |
| `sort_select` | `sort_select.py:53` | ⚠️ 前端未支持 | `candidates`（数组）、`sort_key`、`select_index` |

### 2.6 设备/应用生命周期（5 类）

| node_type | 文件 | 状态 | 关键 config 字段 |
|-----------|------|------|-----------------|
| `start_app` | `app_control.py:41` | ✅ | `package` 或 `window_title` |
| `stop_app` | `app_control.py:131` | ✅ | `package` 或 `window_title` |
| `device_control` | `device_control.py` | ✅ | `action`（'switch_window'/'screenshot'/'activate'）、`window_title` |
| `random_delay` | `random_delay.py` | ✅ | `min_seconds`、`max_seconds` |
| `monitor` | `monitor.py` | ✅ Phase 1 | `action`（"popup"/"skip_story"/"report_error"/"screenshot_monitor"）、`screenshot` — 接入真实 `PopupHandler.check_and_handle()`；`context.monitor_manager` 缺失或 handler 异常时返回 `fail_result` 暴露问题（不静默 Mock 回退，commit `-` + 后续修复） |

### 2.7 通知（1 类）

| node_type | 文件 | 状态 | 关键 config 字段 |
|-----------|------|------|-----------------|
| `notify` | `notify.py` | ✅ | `level`（info/warning/error）、`message`、`channels`（数组） |

### 2.8 节点契约（截图模式 / 前置节点要求 / 能力边界）

> 来源：OCR bug 排查链路归一化分析 (spec-88 TD-336) + 长期归一化现状化 (spec-91 TD-335)。补全 agent 引擎节点层的截图获取契约，明确每个识别/动作节点如何取得 image、是否依赖上游、失败时如何降级。
> 说明：§2.1–§2.7 的节点表已含 4 列，再加 3 列可读性差，故单列本契约子表（4 列）。

| node_type | 截图模式 | 前置节点要求 | 能力边界 |
|-----------|---------|------------|---------|
| `template_match` | 模式 A: 自给自足（节点自截图） | 无 | self-sufficient |
| `feature_match` | 模式 A: 自给自足（节点自截图） | 无 | self-sufficient |
| `color_detect` | 模式 A: 自给自足（节点自截图） | 无 | self-sufficient |
| `maa_actions` | 模式 A: 自给自足（节点自截图） | 无 | self-sufficient |
| `ocr` | 模式 A: 自给自足（context 优先 + device fallback） | 无 | self-sufficient |
| `wait` | 模式 B: 自给自足 + 写回 context（喂子节点） | 无 | self-sufficient |
| `click` | 模式 D: 自截图仅用于 debug 存档 | 无 | self-sufficient |
| `key_press` | 不适用（非识别节点，无截图） | 无 | self-sufficient |
| `swipe` | 模式 D: 自截图仅用于 debug 存档 | 无 | self-sufficient |
| `uia_set_value` / `uia_invoke` / `uia_get_state` / `uia_get_window_title` | 不适用（语义层——accessibility 注入/读取，无截图） | 无 | self-sufficient（受限：目标窗口须为 UIA 可访问控件；`uia_set_value` 需 ValuePattern、`uia_invoke` 需 InvokePattern） |
| `uia_select` | 不适用（语义层——ComboBox 展开+选项选中） | 无 | self-sufficient（受限：ComboBox 需支持 ExpandCollapsePattern/SelectionItemPattern） |
| `uia_scroll` | 不适用（语义层——ScrollPattern 滚动） | 无 | self-sufficient（受限：目标须暴露 IScrollProvider；现代浏览器页面区/Win11 资源管理器列表不暴露（GetPattern=10006→None），Chrome 场景滚动请用 ScrollItemPattern/键鼠；实现走 comtypes GetPattern→QueryInterface 直连，2026-08-26 e2e 验证） |

**契约说明** (spec-91 TD-335 长期归一化后现状):
- **模式 A (识别节点, 5 个)**: `template_match` / `feature_match` / `color_detect` / `maa_actions` / `ocr` — 节点自行 `device.capture_screen()`, context 变量 (`image`/`screenshot`/`last_frame`) 仅用于显式 override (如 `wait` 节点截图后让下游 OCR 复用同一帧避免重复截图). 全部 `self-sufficient`, 可独立编排, 无前置节点要求.
- **模式 B (控制流节点, 1 个)**: `wait` — 循环 `device.capture_screen()` 后 `context.set_variable("image", image)` 喂给子 OCR 节点. 不是识别节点, 截图是为了让子节点复用同一帧.
- **模式 D (动作节点, 3 个)**: `click` / `key_press` / `swipe` — 截图仅用于 debug 存档, 不参与识别也不写回 context.
- **self-sufficient**: 节点自行截图或不需要截图, 不依赖上游产出 image, 可独立编排.
- **OCR device fallback** (spec-91 TD-335 短期 fix 已交付): `ocr._get_image` 依次查 context 变量 (`image`/`screenshot`/`last_frame`) → fallback `device.capture_screen()`. context 空且 device 不可用/失败时返回 None, execute() 报 'No image available (context empty + device capture failed/unavailable)'.

---

## 3. 前后端节点类型差异

> 来源：后端 `PIPELINE_NODE_REGISTRY` 中的 `ALL_NODE_TYPES`（backend/pipeline/schema.py）vs 前端 `frontend/src/types/models/pipeline.ts` 的 `PipelineNodeType` 联合。
> 契约守恒由 `scripts/tests/test_pipeline_node_contract.py`（s42）强制：agent 注册 ⊆ 后端、前端 ⊆ 后端、后端 − agent == legacy 4 类。

### 3.1 前端缺失的类型（后端/agent 可执行，前端编辑器不可配置）

- agent 已注册但前端未暴露：无（`template_match_any` / `swipe_until` / `log_message` 已于 2026-08-26 暴露；前端/agent 现有类型全集一致）
- 后端 legacy（BD2-AUTO，前端/agent 均不支持，仅存量兼容）：`login_account` / `switch_account` / `switch_resource` / `captcha_detect`

**应对**：legacy 4 类手写 JSON 时后端可接受（仅存量兼容，不建议新任务使用）；前端编辑器不可配置。UIAutomation 语义 6 类（`uia_set_value` / `uia_invoke` / `uia_get_state` / `uia_get_window_title` / `uia_select` / `uia_scroll`）已在前端编辑器暴露（分类「语义操作」）。

### 3.2 前端多余的配置组件（后端无对应注册）

- `CaptchaDetectConfig` / `LoginAccountConfig` / `SwitchAccountConfig` / `SwitchResourceConfig`

**应对**：这 4 类在前端编辑器可选但后端 `PipelineNode.create()` 会抛 `ValueError("未知的节点类型")`。手写 JSON 不要使用。

---

## 4. 常见编排模式

### 4.1 模板匹配 → 点击（最常见）

```json
{
  "node_id": "match_btn",
  "node_type": "template_match",
  "next_node_id": "next_step",
  "config": {
    "template": "BrownDust-II/templates/guild_btn.png",
    "roi": [800, 200, 400, 200],
    "threshold": 0.85,
    "click_on_match": true,
    "timeout": 10
  }
}
```

### 4.2 OCR 文字检查 → 分支

```json
{
  "node_id": "check_state",
  "node_type": "ocr",
  "next_node_id": "decide",
  "config": {
    "engine": "rapid",
    "texts": ["已加入", "申请加入"],
    "roi": [500, 300, 400, 100]
  }
},
{
  "node_id": "decide",
  "node_type": "branch",
  "config": {
    "cases": [
      {"condition": "check_state.result == '已加入'", "next_node_id": "exit"},
      {"condition": "check_state.result == '申请加入'", "next_node_id": "click_apply"}
    ],
    "default_next_node_id": "retry"
  }
}
```

### 4.3 循环直到匹配

```json
{
  "node_id": "loop_start",
  "node_type": "loop",
  "next_node_id": "after_loop",
  "config": {
    "body_start_node_id": "scroll_down",
    "body_end_node_id": "check_target",
    "max_iterations": 10,
    "exit_condition": "check_target.matched == true"
  }
}
```

### 4.4 子流程调用

```json
{
  "node_id": "call_login",
  "node_type": "sub_pipeline",
  "next_node_id": "main_flow",
  "config": {
    "pipeline_id": "pipeline-login-flow-v2",
    "params": {"account": "user1"}
  }
}
```

---

## 5. BD2 ChainManager → GAF Pipeline 映射

> 完整映射表见 [task-execution-reality.md](execution-reality.md) §3.1。这里给出口诀：

| BD2 ChainManager API | GAF Pipeline 节点 |
|---------------------|------------------|
| `chain.click_template(tpl)` | `template_match` + `click_on_match: true` |
| `chain.click_text(text)` | `ocr` + `click_on_match: true` |
| `chain.click(x, y)` | `click` |
| `chain.wait_template(tpl, timeout)` | `template_match` + `timeout`（无 `click_on_match`） |
| `chain.swipe(...)` | `swipe` |
| `chain.wait(seconds)` | `wait` |
| `chain.if_found(tpl, then, else)` | `branch`（condition 引用前一个 `template_match` 的 `matched`） |
| `chain.repeat_until(...)` | `loop` |

---

## 6. 完整示例：BD2 `get_guild` 的 Pipeline JSON

> BD2 原始任务：`BD2-AUTO/src/auto_tasks/Default/tasks/get_guild.py`（@auto_task 装饰器 + ChainManager）
> ROI 定义：`BD2-AUTO/src/auto_tasks/Default/config/rois.json`
> 模板资源：5 张 PNG 在 `BD2-AUTO/src/auto_tasks/Default/templates/`（已复制到 `GAF/resources/BrownDust-II/templates/`）

### 6.1 BD2 原始任务逻辑

```python
@auto_task("get_guild")
def get_guild(auto, chain, timeout=300.0):
    chain.custom_step(back_to_main, timeout=chain.remaining_timeout)  # 1. 返回主界面
    chain.template_click(                                              # 2. 点击公会标识
        ["get_guild/公会标识", "get_guild/公会标识2"],
        roi=roi_config.get_roi("guild_icon", "get_guild")              # [310, 111, 130, 100]
    )
    chain.with_pre_verify(                                             # 3. 验证公会商店 + 点返回 + 验证主界面
        verify_type="wait_element", target="get_guild/公会商店",
        roi=roi_config.get_roi("guild_shop", "get_guild")              # [1631, 16, 230, 70]
    ).template_click(
        "public/返回键1",
        roi=roi_config.get_roi("back_button"),                         # [120, 20, 100, 66]
        verify={"type": "exist", "target": "public/主界面",
                "roi": roi_config.get_roi("main_menu"),                # [1720, 20, 120, 70]
                "timeout": 5},
    )
    return True
```

### 6.2 简化版 Pipeline JSON（5 节点，首次端到端验证用）

> **简化说明**：BD2 的 `back_to_main` 是复杂状态机（地图标识 → 返回键 → ESC → H 键 → 确认框处理），首次验证只保留核心公会流程，`back_to_main` 后续可用 `sub_pipeline` 节点封装。
> **多模板回退**：BD2 的 `["公会标识", "公会标识2"]` 用 `next_node_id_on_failure` 链式回退实现。

```json
{
  "nodes": [
    {
      "node_id": "verify_at_main",
      "node_type": "template_match",
      "next_node_id": "click_guild_icon",
      "config": {
        "template": "BrownDust-II/templates/public/主界面.png",
        "roi": [1720, 20, 120, 70],
        "threshold": 0.80,
        "timeout": 5
      },
      "continue_on_error": true
    },
    {
      "node_id": "click_guild_icon",
      "node_type": "template_match",
      "next_node_id": "verify_guild_shop",
      "next_node_id_on_failure": "click_guild_icon_alt",
      "config": {
        "template": "BrownDust-II/templates/get_guild/公会标识.png",
        "roi": [310, 111, 130, 100],
        "threshold": 0.85,
        "click_on_match": true,
        "timeout": 8
      },
      "post_delay": 1.0
    },
    {
      "node_id": "click_guild_icon_alt",
      "node_type": "template_match",
      "next_node_id": "verify_guild_shop",
      "config": {
        "template": "BrownDust-II/templates/get_guild/公会标识2.png",
        "roi": [310, 111, 130, 100],
        "threshold": 0.85,
        "click_on_match": true,
        "timeout": 8
      },
      "post_delay": 1.0
    },
    {
      "node_id": "verify_guild_shop",
      "node_type": "template_match",
      "next_node_id": "click_back_button",
      "config": {
        "template": "BrownDust-II/templates/get_guild/公会商店.png",
        "roi": [1631, 16, 230, 70],
        "threshold": 0.80,
        "timeout": 10
      }
    },
    {
      "node_id": "click_back_button",
      "node_type": "template_match",
      "next_node_id": "verify_back_to_main",
      "config": {
        "template": "BrownDust-II/templates/public/返回键1.png",
        "roi": [120, 20, 100, 66],
        "threshold": 0.85,
        "click_on_match": true,
        "timeout": 5
      },
      "post_delay": 1.5
    },
    {
      "node_id": "verify_back_to_main",
      "node_type": "template_match",
      "next_node_id": null,
      "config": {
        "template": "BrownDust-II/templates/public/主界面.png",
        "roi": [1720, 20, 120, 70],
        "threshold": 0.80,
        "timeout": 5
      }
    }
  ]
}
```

**节点流转图**：
```
verify_at_main → click_guild_icon ──success──→ verify_guild_shop → click_back_button → verify_back_to_main → END
                       │
                       └─failure─→ click_guild_icon_alt ──success──→ verify_guild_shop
                                          │
                                          └─failure─→ (Pipeline 失败)
```

### 6.3 资源准备清单

| 资源 | 来源 | 目标路径（GAF） | 状态 |
|------|------|----------------|------|
| `public/主界面.png` | `BD2-AUTO/.../templates/public/主界面.png` | `GAF/resources/BrownDust-II/templates/public/主界面.png` | ✅ 已导入 |
| `public/返回键1.png` | `BD2-AUTO/.../templates/public/返回键1.png` | `GAF/resources/BrownDust-II/templates/public/返回键1.png` | ✅ 已导入 |
| `get_guild/公会标识.png` | `BD2-AUTO/.../templates/get_guild/公会标识.png` | `GAF/resources/BrownDust-II/templates/get_guild/公会标识.png` | ✅ 已导入 |
| `get_guild/公会标识2.png` | `BD2-AUTO/.../templates/get_guild/公会标识2.png` | `GAF/resources/BrownDust-II/templates/get_guild/公会标识2.png` | ✅ 已导入 |
| `get_guild/公会商店.png` | `BD2-AUTO/.../templates/get_guild/公会商店.png` | `GAF/resources/BrownDust-II/templates/get_guild/公会商店.png` | ✅ 已导入 |
| ROI 定义 | `BD2-AUTO/.../config/rois.json` | 已硬编码到 Pipeline JSON 的 `roi` 字段 | ✅ |
| 任务名映射 | `BD2-AUTO/.../config/task_names.json` | 用于 Pipeline `name` 字段（如 `get_guild` → "领取公会奖励"） | ✅ |

### 6.4 验证步骤

1. **资源导入**：5 张 PNG 已复制到 `resources/BrownDust-II/templates/`（见 §6.3 状态）
2. **Pipeline 注册**：`POST /api/v2/pipeline/pipelines/` 创建 Pipeline（`pipeline_data` 为 §6.2 JSON）。注意：pipeline 应用挂载在 `/api/v2/pipeline/` 前缀下（见 `backend/config/urls.py:25`），而非 `/api/v2/tasks/`。
3. **Agent 在线**：启动 GAF agent 进程（`cd GAF/agent && conda run -n gaf python -m src`），确认 `/api/v2/agents/` 的 `last_heartbeat` 是当前时间
4. **设备准备**：启动 BrownDust II 客户端，确认 `/api/v2/devices/?status=online` 列出 Windows 设备
5. **执行**：`POST /api/v2/pipeline/pipelines/<pk>/execute/`（body: `{"device_id": <id>, "agent_id": <id>}`，见 `backend/pipeline/views.py:198` 的 `execute` action）
6. **验证**：观察 Agent 日志 + `TaskExecution` 状态（`/api/v2/tasks/task-executions/<id>/`），确认每个节点 ✅ 或诚实失败

---

## 7. 校验工具

- **后端校验**：`POST /api/v2/pipeline/pipelines/validate/`（`PipelineValidateSerializer`，见 `backend/pipeline/urls.py:27`）。注意路径前缀为 `/api/v2/pipeline/`（pipeline 单数应用名），而非 `/api/v2/tasks/`。
- **Agent 校验**：`worker/src/engine/validator.py` 的 `PipelineValidator`（检查 `node_type` 合法性、`next_node_id` 引用完整性）
- **前端预览**：PipelineEditorPage 的 PreviewPanel（已支持全部 48 类节点，2026-08-26 解除限制）

---

## 8. 已知限制

1. **`monitor` 节点需要 MonitorManager**：Phase 1 起 monitor 节点接入 `PopupHandler.check_and_handle()`（commit `-` + `-`）。`context.monitor_manager` 缺失或 handler 抛异常时返回 `fail_result`（不静默 Mock 回退），因此生产环境必须确保 agent `__main__.py` 调用 `monitor_manager.start()`，否则含 monitor 节点的 Pipeline 会执行失败。详见 [monitor-design.md](../ops/monitor-design.md) §0。
2. **前端编辑器已支持全部 48 类节点**（2026-08-26 更新后解除；早期仅 Maa 协议/多指操作受限的历史限制）。
3. **`recording_converter.py` 仅产出 3 类节点**：录制转 Pipeline 只生成 `click` / `wait` / `key_press`，复杂逻辑需手写。
4. **`params` 作为 `config` 别名**：parser 已归一化（`params` → `config`），但作者应统一用 `config`。`task-execution-reality.md` 的示例用 `params`（BD2 风格），也能正常工作。
5. **`click_on_match` 已实现（仅 `template_match`）**：`template_match` 节点支持 `click_on_match: true`，匹配成功后自动点击中心点（BD2 `chain.click_template` 快捷方式）。`ocr` / `color_detect` 暂不支持，需后续 `click` 节点。
