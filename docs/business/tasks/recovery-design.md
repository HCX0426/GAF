# 界面恢复机制设计 (Interface Recovery)

> **状态**: 设计草案 v13,待用户审查
> **实现对照(2026-08-28)**: interface_recovery.py 已实现且核心 API 一致；但 (a) engine 已按 N202 拆分为 pipeline_engine.py+pipeline_execution/lifecycle/recovery.py，文中 engine.py 全部行号失效； (b) PipelineResult.recovery_archive、PipelineContext.recovery_manager/max_recovery_retries 字段未按文档落地（现为 engine 实例属性）；恢复管理器现用 _recovery_attempts_per_node/_build_previous_node_chain，无 step_index 回滚
> **日期**: 2026-07-23 (v2: 2026-07-24 补充 state_machine 边界 + 10 处实现细节完善;v3: 2026-07-24 加 §13 Python 代码任务节点;v4: 2026-07-24 评估修复 — OCR 推断规则 + 链式回溯一致性 + transient 重试;v5: 2026-07-24 二次评估修复 — device.capture_screen + color_detect 归类 + 链方向矛盾 + 签名一致性;v6: 2026-07-24 三次评估修复 — 重大架构错误:engine 主循环是图遍历非 for 循环 + orchestrator 变量名 + recovery_manager 注入路径;v7: 2026-07-24 四次评估修复 — 事实核查:_execute_node_step 方法名 + 主界面引用数 16 非 30 + state_machine 行号 + pipeline_name 未设置问题;v8: 2026-07-24 五次评估修复 — 节点类型数 40 非 39 + §13.5 索引不前进措辞;v9: 2026-07-24 六次评估修复 — importlib 行号 + .gitignore 现有规则覆盖;v10: 2026-07-24 七次评估修复 — 重大缺陷:python_call 函数签名移除 image_processor,engine 层无此实例;v11: 2026-07-24 八次评估修复 — 行号精确化:from_dict→restore/load()范围/PipelineResult范围/_execute_pipeline_inner范围/state_machine触发逻辑范围/swipe duration 默认值不一致;逻辑闭环修复:continue 副作用说明+step_index 回滚+_previous_node_chain 含 node_id+execution_context 补全 node_type/retry_count/previous_node_id/expected_state_source+§10.6 recovery 期间取消信号+§10.7 step_index 一致性;重大缺陷修复:template 路径解析缺失 — _execute_recovery_action 和 identify_state 都需经 resolve_resource_path 解析路径,find_template 不做路径解析;v12: 2026-07-24 九次评估修复 — 严重错误:_max_iterations 默认值 10000 非 1000+路径推断规则状态名矛盾(email_menu→email_state 统一命名);中等问题:PATH_STATE_MAPPING 实现位置说明+max_recovery_retries 归属明确(AgentConfig 字段,engine 读取)+custom_tasks .gitkeep 描述统一;轻微问题:color_detect 字段补全+recovery_manager 字段位置说明+stuck_threshold 默认值 3 补充;v13: 2026-07-24 十次评估修复 — 最终一致性扫描:5 处轻微文档精确性优化(popup_handler 路径精确化+custom_tasks_base_dir 默认值描述+serialize/restore 无需修改说明+recovery_manager re-injection 模式差异说明+iteration 配额措辞 "< 0.03%"→"约 0.03%")
> **来源**: 用户提案 — "卡住后识别当前界面 → 推理回退路径 → 回到任务或存档" + "Python 方法当作 pipeline 任务" + "OCR 也能当标注节点,匹配不到一般是点击失效/网络卡顿"
> **范围**: BD2 (BrownDust-II) 为首个落地场景,架构可复用到其他游戏

---

## 1. 背景与问题

### 1.1 现状

GAF 的 BD2 任务执行链路:

```
后端 WS pipeline.execute → agent handler → TaskOrchestrator → PipelineEngine → 节点顺序执行
```

节点失败时的现有处理 ([pipeline_engine.py:472-484](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py)):

- 默认 `continue_on_error=False` → 立即终止 pipeline,返回 FAILED
- `continue_on_error=True` → 跳过该节点继续
- debug 模式下: auto-heal (切截图方法) + LLM 诊断根因

**缺口**: pipeline 引擎层没有"识别当前界面后跳回某节点"的能力。"回到主界面"完全依赖 pipeline 作者的契约 — 末尾用 `key_press(esc) + wait(主界面.png)` 组合,共 16 处引用 `templates/public/主界面.png` (15 处 template + 1 处 comment,跨 12 个 pipeline; 资源路径约定 `resources/<Game>/templates/...`,目录为运行时数据)。

### 1.2 任务加载机制与 Python 代码任务支持现状

GAF 任务编排器 ([orchestrator.py](file:///d:/code/GAF/agent/src/core/orchestrator.py)) 支持三种执行模式,Python 代码任务的支持情况如下:

| 模式 | 入口 | Python 代码支持 | 与本方案关系 |
|------|------|----------------|-------------|
| **chain 模式** | `_execute_chain` (orchestrator.py:160) | ❌ action_map 硬编码 6 种 (click/swipe/key_press/text_input/screenshot/wait) | 不适用 |
| **pipeline 模式** | `execute_pipeline` (orchestrator.py:634) | ❌ 40 个节点类型中无 `python`/`script` 类型 (实际注册数见 [nodes/__init__.py](file:///d:/code/GAF/agent/src/engine/nodes/__init__.py) + [@register_node](file:///d:/code/GAF/agent/src/engine/node.py#L18) 装饰器) | **本方案适用范围** |
| **state_machine 模式** | `_execute_state_machine` (orchestrator.py:206) | ✅ 通过 `importlib.import_module(task_definition["module"])` 加载 Python 模块的 `build_state_machine()` 工厂函数 | 不在本方案范围 |

**关键结论**:
- pipeline 模式下,`PipelineParser.parse_dict` ([parser.py:257-262](file:///d:/code/GAF/agent/src/engine/parser.py)) 严格校验节点类型,未注册类型直接抛 `ValueError`,**无法在 pipeline JSON 中插入任意 Python 代码节点**
- state_machine 模式通过 Python 模块工厂函数实现任务级 Python 代码,且**自带卡顿检测机制**(`stuck_threshold` + `on_stuck` 回调,见 [state_machine.py:52-53](file:///d:/code/GAF/agent/src/core/state_machine.py#L52-L53) 字段定义 + [state_machine.py:176-194](file:///d:/code/GAF/agent/src/core/state_machine.py#L176-L194) 触发逻辑,含阈值检查 / on_stuck 调用 / except 块 / 计数器重置;`DEFAULT_STUCK_THRESHOLD = 3` 见 [state_machine.py:22](file:///d:/code/GAF/agent/src/core/state_machine.py#L22)),无需本方案介入
- 本方案聚焦 pipeline 模式,因为:(1) BD2 现有 12 个任务全是 pipeline 模式;(2) pipeline 模式无内置卡顿检测;(3) state_machine 模式已有自己的恢复路径

**Pipeline 节点类型清单**(共 40 类,本方案识别/动作相关的关键类型):

| 类别 | 节点类型 | 用途 |
|------|---------|------|
| 画面识别 | `template_match` / `template_match_any` / `ocr` / `color_detect` / `feature_match` / `neural_network` / `nn_classifier` / `nn_regressor` | 界面状态识别的数据源 |
| 复合匹配 | `and_match` / `or_match` / `custom_match` (eval 受限表达式) | 多条件组合识别 |
| 输入操作 | `click` / `direct_hit` / `key_press` / `long_press` / `swipe` / `swipe_until` / `multi_swipe` / `multi_scroll` / `multi_touch` / `text_input` / `wheel` | transitions.action 执行器复用 |
| 控制流 | `branch` / `goto` / `loop` / `sub_pipeline` / `wait` / `sort_select` | 节点级流程控制 |
| Maa 协议 | `jump_back` / `wait_freezes` / `next` / `stop` / `anchor` | Maa 兼容动作 |
| 应用生命周期 | `start_app` / `stop_app` / `device_control` / `random_delay` / `monitor` | 设备/应用级 |
| 其他 | `notify` / `roi_resolver` | 通知与辅助 |

---

## 1.3 问题场景

**场景 1: 节点失败后界面漂移**

`daily_missions` pipeline 执行到第 5 步失败,此时游戏可能停在:
- 某个任务子界面 (非主界面)
- 某个未知弹窗背后
- 某个加载界面

当前: 直接 FAILED,用户无法快速定位"现在到底在哪个界面"。

**场景 2: 跨任务状态污染**

`daily_missions` 失败后界面没回到主界面,`get_email` 任务从错误界面启动 → 第一步 template_match 就失败。

当前: 依赖 routine.json 的 `on_failure: abort` 止损,但无法自动恢复。

**场景 3: 未知界面无兜底**

遇到没见过的界面 (新版本更新加了新弹窗/新界面),系统不知道怎么处理。

当前: 没有存档机制,失败后无法事后分析,只能用户实时盯日志。

---

## 2. 设计目标

### 2.1 核心目标

1. **界面状态识别** — 节点失败后自动识别"当前在哪个界面"
2. **回退路径推理** — 从当前界面推理到期望界面的点击路径
3. **未知界面存档** — 识别失败时保存截图+上下文,供人工/LLM 补充
4. **渐进式扩展** — 状态图人工维护,LLM 接入后辅助补充

### 2.2 非目标 (明确排除)

- ❌ 不处理临时弹窗 (广告/奖励弹窗) — 继续由 `popup_handler.yaml`（资源包目录 `resources/<Game>/monitors/`，运行时数据）负责
- ❌ 不替代 retry.py / recovery.py 的设备/应用级恢复
- ❌ 不自动修改 pipeline JSON — 只在运行时回退,不持久化
- ❌ 不处理 state_machine 模式任务 — 仅针对 pipeline 模式

### 2.3 成功标准

| # | 标准 | 验证方式 |
|---|------|---------|
| S1 | 节点失败后能识别当前是否在已知界面 | 单元测试 mock 截图匹配 |
| S2 | 已知界面间能推理出回退路径 | BFS 算法测试 |
| S3 | 回退成功后 pipeline 能从当前节点 resume | 集成测试 |
| S4 | 未知界面生成存档文件 (截图+json) | 存档目录结构检查 |
| S5 | 现有 12 个 BD2 pipeline 零改动 | tsc + vitest 无 regression |

---

## 3. 架构设计

### 3.1 模块定位

新增独立模块,与现有恢复模块平级:

```
agent/src/core/
├── orchestrator.py        ← 任务编排 (调用方)
├── engine/
│   └── pipeline_engine.py  ← PipelineEngine (失败时调用 Manager)
├── recovery.py            ← 5 层恢复 (设备/应用级,已存在)
├── retry.py               ← 重试装饰器 (已存在)
├── safe_point.py          ← 取消安全点 (已存在)
└── interface_recovery.py  ← 【新增】界面恢复 Manager
```

### 3.2 调用时序

```
PipelineEngine.execute() 主循环 (while self._current_node_id + _resolve_next_node 图遍历,详见 §5.2)
  │
  ├─ 节点执行成功 → _resolve_next_node 返回下一节点 ID → 继续
  │
  └─ 节点执行失败 (engine.py:472)
      │
      ├─ continue_on_error=True → 跳过,继续下一节点
      │
      └─ continue_on_error=False (默认)
          │
          ├─ 【新增】调用 InterfaceRecoveryManager.recover()
          │   │
          │   ├─ 1. 截图当前界面
          │   ├─ 2. 跑 popup_handler 关临时弹窗 (复用现有)
          │   ├─ 3. 重新截图,识别底层界面
          │   │   ├─ 匹配 interface_states.yaml 的 detect_templates
          │   │   ├─ 命中已知状态 → 进入步骤 3a
          │   │   └─ 未命中 → **transient 重试**: 短暂等待 (1.5s) 后重新截图重试识别 (最多 2 次)
          │   │       ├─ 重试期间命中已知状态 → 进入步骤 3a (transient 状态已恢复,如 loading 消散/网络恢复)
          │   │       └─ 重试 2 次仍未命中 → 进入步骤 6 (真未知界面)
          │   ├─ 3a. 判断 current_state == expected_state?
          │   │   ├─ 是 → 返回 ALREADY_THERE (跳过回退,直接重试节点)
          │   │   └─ 否 → 进入步骤 4
          │   ├─ 4. BFS 推理: current_state → expected_state 的最短路径
          │   ├─ 5. 执行回退动作序列 (点返回键/导航按钮)
          │   │   ├─ 每步后重新截图验证 (识别到的状态 != expected_state 即"未到达")
          │   │   ├─ 到达 expected_state → 返回 RECOVERED
          │   │   └─ 连续 2 步未到达 expected_state → 进入步骤 6 (与 §10.1 一致)
          │   └─ 6. 未知界面兜底
          │       ├─ 保存截图到 debug/unknown_states/
          │       ├─ 保存上下文 json (pipeline名+节点ID+期望状态+时间戳)
          │       └─ 返回 NEEDS_HUMAN
          │
          ├─ 返回 RECOVERED / ALREADY_THERE → engine 重试当前节点 (不更新 _current_node_id,while 循环重新进入同一 node)
          │
          └─ 返回 NEEDS_HUMAN / RECOVERY_FAILED → engine 返回 FAILED + 暂停任务
              (用户/LLM 事后查存档,补充 interface_states.yaml)
```

### 3.3 expected_state 来源 (3 级优先级)

期望界面按以下优先级确定 (高 → 低):

**优先级 1: 手动标注 (可选,最准)**

节点 config 中可加 `expected_state` 字段,显式标注期望界面:

```json
{
  "id": "step5_click_mission",
  "node_type": "template_match",
  "config": {
    "template": "...",
    "expected_state": "daily_missions_menu"
  }
}
```

> 注: parser 支持用 `type` 或 `node_type` 作为节点类型字段 (parser.py:222-225 会将 `type` 规范化为 `node_type`),本 spec 统一用 `node_type`。

手动标注为可选项,不加则走自动推断。适合自动推断不准的关键节点 (如 click/wait 节点期望在特定界面)。

**优先级 2: 自动推断 (默认)**

未手动标注时,从节点 config 自动推断。**模板类识别节点**(template_match/template_match_any/feature_match)可从 config.template 路径推断;**OCR/color_detect/neural_network 等非模板识别节点**和**非识别类节点**(click/wait/python_call/...)走递归回溯,沿成功节点链找最近的模板类识别节点或手动标注节点,复用其 expected_state。

| 节点类别 | 节点类型 | config 字段 | 推断规则 | 示例 |
|---------|---------|------------|---------|------|
| 画面识别(模板类) | `template_match` / `template_match_any` | config.template | 路径含 `public/主界面` → `main_menu` | `templates/public/主界面.png` → `main_menu` |
| 画面识别(模板类) | `template_match` / `template_match_any` | config.template | 路径含 `public/地图标识` → `map_view` | `templates/public/地图标识.png` → `map_view` |
| 画面识别(模板类) | `template_match` / `template_match_any` | config.template | 路径含 `<task>/` → `<task>_state` | `templates/get_email/邮箱.png` → `get_email_state` |
| 画面识别(模板类) | `feature_match` | config.template | 同上路径推断规则 (feature_match 有 template 字段) | `templates/get_pvp/竞技场标识.png` → `get_pvp_state` |
| 画面识别(非模板类) | `color_detect` | config.lower / upper / roi / min_area / max_results / click_on_match / roi_coord_type | **路径推断不适用** — color_detect 用 HSV 颜色范围检测,无模板路径。**强烈推荐手动标注**;未标注走递归回溯 | — |
| 画面识别(非模板类) | `neural_network` / `nn_classifier` / `nn_regressor` | config.model / config.weights 等 | **路径推断不适用** — 神经网络节点用模型文件,语义与界面状态无直接映射。**强烈推荐手动标注**;未标注走递归回溯 | — |
| 画面识别(文字类) | `ocr` | config.expected_text / config.region | **路径推断不适用** — OCR 识别文字内容无模板路径。**强烈推荐手动标注 `expected_state`**;若未标注,走递归回溯(见下方) | OCR 节点 `expected_text: "邮箱"` → 建议手动标注 `expected_state: email_state` |
| 非识别类 | `click` / `key_press` / `swipe` / `wait` / `branch` / `python_call` 等 | — | **递归回溯**: 沿成功节点链往回找最近的模板类识别节点或手动标注节点,复用其 expected_state | click 节点失败 → 往回找 → 命中上一 template_match 节点推断的 `daily_missions_state` |

**递归回溯逻辑** (针对非识别类节点,以及未手动标注的 OCR/color_detect/neural_network 节点):
1. 从当前失败节点往回遍历成功节点链 (`_previous_node_chain`,末尾 = 最近成功节点,从末尾往头遍历)
2. 找到第一个: 模板类识别节点(用其路径推断结果) 或 手动标注 `expected_state` 的节点(用其标注值)
3. 全链回溯无果 → 降级到优先级 3 (safe_state)

**路径推断规则的实现与命名一致性** (关键):

路径推断规则硬编码在 `infer_expected_state` 方法内,以两层结构实现:

1. **精确匹配层** (常量字典 `PATH_STATE_MAPPING`):
   ```python
   PATH_STATE_MAPPING = {
       "public/主界面": "main_menu",
       "public/地图标识": "map_view",
       # 人工补充更多精确映射
   }
   ```
   - 键: template 路径片段 (相对路径,不含扩展名)
   - 值: 对应 `interface_states.yaml` 中的状态名

2. **通配 fallback 层** (`<task>_state` 规则):
   - 精确匹配未命中时,从 template 路径提取 `<task>` 名
   - **路径解析步骤**: 先经 `resolve_resource_path` 解析为绝对路径,然后取 `templates/` 之后的第一级目录作为 `<task>` 名
   - 示例: `BrownDust-II/templates/get_email/邮箱.png` → 提取 `get_email` → 推断状态名 `get_email_state`
   - 示例: `public/主界面.png` → 不含 `templates/`,取相对路径第一级目录 `public` → 但已在精确匹配层命中 `main_menu`,不会走到 fallback

**⚠️ 命名一致性要求**:
- `interface_states.yaml` 中状态名必须与推断结果一致,否则会导致 `expected_state != current_state` 误触发回退
- 示例: 模板 `get_email/邮箱.png` 的自动推断结果是 `get_email_state`,因此 `interface_states.yaml` 中该界面的状态名必须用 `get_email_state` (而非 `email_menu` 等自定义名)
- 若需用自定义状态名 (如 `email_menu`),必须在节点 config 中显式标注 `expected_state: email_menu`,跳过自动推断
- 未来 (Phase 2 之后) 可把 `PATH_STATE_MAPPING` 迁移到 `interface_states.yaml` 中配置化,实现"路径片段 → 状态名"映射的外部维护

**场景合理性**: 非识别类节点(如 click)失败通常是点击失效/点击被吞/网络卡顿 — 界面状态未变,沿用上一识别节点的 expected_state 仍然有效,回退到该状态后重试 click 大概率成功。

**优先级 3: 降级到安全状态 (兜底)**

自动推断失败 (如节点是 click 类型且无上一成功节点) 时,降级到 `interface_states.yaml` 中任意 `is_safe_state: true` 的状态 (通常是 `main_menu`)。回退到安全状态后由 routine chain 决定是否重试整个 pipeline。

**覆盖率预估**: 手动标注 0% (初始) + 自动推断 70-80% + 降级兜底 20-30% = 100% 覆盖。手动标注随关键节点逐步补充后覆盖率提升。

---

## 4. 数据结构

### 4.1 interface_states.yaml (人工维护的状态图)

路径: `resources/BrownDust-II/interface_states.yaml`

```yaml
# 界面状态定义 + 转移图
# 人工维护,LLM 接入后辅助补充 (需人工审核)
#
# detect_templates 匹配逻辑: OR — 任一模板命中 (score >= threshold) 即识别为该状态
# 多模板用于同一界面的多种外观 (如日间/夜间、不同分辨率)
#
# template 路径格式 (与 pipeline JSON 一致,由 resource_resolver.py 解析):
#   - 短路径: "public/主界面.png" → 自动搜索 <resources>/<game>/templates/public/主界面.png
#   - 全路径: "BrownDust-II/templates/public/主界面.png" → 相对 resources/ 目录
#   - 绝对路径: "D:/code/GAF/resources/BrownDust-II/templates/public/主界面.png" → 直接使用
# 路径解析在 orchestrator 注入 template_match_fn 时包装 (见 §5.3 Step 4),
# Manager 内部 identify_state 调用时已是绝对路径,无需再解析

states:
  main_menu:
    description: 主界面
    detect_templates:
      - template: public/主界面.png
        threshold: 0.8
        roi: [1720, 20, 120, 70]  # 右上角主界面标识区域
    is_safe_state: true  # 安全状态,回退到这里不会丢进度

  map_view:
    description: 地图界面
    detect_templates:
      - template: public/地图标识.png
        threshold: 0.8

  email_state:
    description: 邮箱界面
    detect_templates:
      - template: get_email/邮箱.png
        threshold: 0.8

  # ... 其他状态

transitions:
  # 从 email_state 点返回键 → main_menu
  - from: email_state
    to: main_menu
    action:
      type: template_match  # 动作类型 (见下方 action 类型清单)
      template: public/返回键1.png
      click_on_match: true
    description: 邮箱界面点返回键回主界面

  - from: map_view
    to: main_menu
    action:
      type: key_press
      key: esc
    description: 地图界面按 ESC 回主界面

  - from: main_menu
    to: email_state
    action:
      type: template_match
      template: get_email/邮箱入口.png
      click_on_match: true
    description: 主界面点邮箱入口进邮箱

  # ... 其他转移
```

**transitions.action 支持的类型清单** (复用现有 pipeline 节点的输入操作语义,不引入新类型):

| `type` 值 | 必填字段 | 可选字段 | 执行语义 |
|-----------|---------|---------|---------|
| `template_match` | `template` | `threshold` (默认 0.8) / `roi` / `click_on_match` (默认 true) | 模板匹配命中后点击匹配位置 (若 `click_on_match=true`);仅识别不点击设 `click_on_match: false` |
| `key_press` | `key` | — | 按下键盘键 (如 `esc` / `enter` / `space`) |
| `click` | `x`, `y` | — | 点击指定坐标 |
| `swipe` | `x1`, `y1`, `x2`, `y2` | `duration` (默认 500ms,与 BaseDevice.swipe 原生默认 300ms 不同 — recovery action 层显式传 500ms 适配过渡动画) | 滑动 |
| `wait` | `duration` | — | 等待指定毫秒数 (用于过渡动画) |

**设计原则**: action 类型与 pipeline 节点 type 解耦 — transitions.action 用极简子集覆盖回退路径需求 (90% 场景是点返回键 + 等待)。完整节点语义仍由 pipeline 节点承担。新增 action 类型需同步更新 `action_executor_fn` 实现。

**YAML 加载校验**:
- `from` / `to` 必须在 `states` 中已定义,否则加载时抛 `ValueError`
- `action.type` 必须在上述清单中,否则加载时抛 `ValueError`
- 显式自环 (`from == to`) 拒绝加载 (§10.3)

### 4.2 未知界面存档格式

路径: `debug/unknown_states/{pipeline_name}_{node_id}_{timestamp}/`

```
debug/unknown_states/daily_missions_step5_20260723_143022/
├── screenshot.png          # 失败时截图
├── screenshot_after_popup.png  # popup_handler 处理后截图 (若有)
└── context.json            # 执行上下文
```

`context.json`:

```json
{
  "pipeline_name": "daily_missions",
  "node_id": "step5_click_mission",
  "node_type": "template_match",
  "node_config": {
    "template": "BrownDust-II/templates/daily_missions/任务入口.png",
    "threshold": 0.8,
    "roi": [100, 200, 300, 400]
  },
  "expected_state": "main_menu",
  "expected_state_source": "auto_inferred",
  "matched_states": [],
  "best_match_score": 0.42,
  "best_match_state": null,
  "timestamp": "2026-07-23T14:30:22+08:00",
  "device_id": "emulator-5554",
  "execution_id": "exec_abc123",
  "recovery_attempt": 2,
  "retry_count": 2,
  "previous_node_id": "step4_wait_load",
  "previous_node_result": "success",
  "recovery_path_attempted": null,
  "recovery_actions_executed": null
}
```

**字段说明**:

| 字段 | 类型 | 来源 | 说明 |
|------|------|------|------|
| `pipeline_name` | str | engine 从 `self._context.pipeline_name` 传给 recover() | pipeline 名称 (load() 时从 pipeline_json["name"] 设置) |
| `node_id` | str | engine 从 `node.id` 传给 recover() | 失败节点 ID |
| `node_type` | str | engine 从 `node.node_type` 传 (在 execution_context 中) | 失败节点类型 (PipelineNode 字段,不在 config 中) |
| `node_config` | str | engine 从 `node.config` 传给 recover() | 失败节点配置 |
| `expected_state` | str | engine 从 `infer_expected_state()` 返回值传 | 期望界面状态名 |
| `expected_state_source` | str | engine 从 `infer_expected_state()` 返回的 source 传 (在 execution_context 中) | 推断来源: manual / auto_inferred / previous_node_chain / safe_fallback |
| `matched_states` | list | Manager 内部 `identify_state()` 产生 | 命中的状态列表 (通常为空,因未知界面) |
| `best_match_score` | float | Manager 内部 `identify_state()` 产生 | 最高匹配置信度 |
| `best_match_state` | str \| null | Manager 内部 `identify_state()` 产生 | 最高分状态名 (未命中为 null) |
| `timestamp` | str | Manager archive 时生成 | ISO 8601 时间戳 |
| `device_id` | str | engine 从 `context.device.device_id` 传 (在 execution_context 中) | 设备 ID |
| `execution_id` | str | engine 从 `self._execution_id` 传 (在 execution_context 中) | 执行 ID |
| `recovery_attempt` | int | engine 从 `_node_recovery_counts[node.id] + 1` 传 (在 execution_context 中) | 当前节点的第几次恢复尝试 (1-based) |
| `retry_count` | int | engine 从 `result.retry_count` 传 (在 execution_context 中,AutoResult 字段) | 节点自身的重试次数 |
| `previous_node_id` | str \| null | engine 从 `_previous_node_chain[-1]["id"]` 传 (在 execution_context 中) | 上一成功节点 ID (无成功节点时为 null) |
| `previous_node_result` | str \| null | engine 固定传 "success" (在 execution_context 中) | 上一节点结果 (chain 只存成功节点,故固定 "success") |
| `recovery_path_attempted` | list[str] \| null | Manager 内部 `execute_path()` 产生 | 若尝试过回退路径,记录路径状态名列表;未识别到状态则为 null |
| `recovery_actions_executed` | list[dict] \| null | Manager 内部 `execute_path()` 产生 | 若执行过回退动作,记录每步动作 + 是否成功 + 截图路径;未执行则为 null |

**存档完整性约束**:
- `recovery_attempt > 0` 时,`recovery_path_attempted` 和 `recovery_actions_executed` 至少有一个非 null (除非节点首次失败直接未命中状态,此时两者均可为 null,如上方示例)
- 若识别命中状态但回退失败: `recovery_path_attempted=["state_A","state_B",...]` + `recovery_actions_executed=[{type, success, screenshot}, ...]`

### 4.3 InterfaceRecoveryResult (Manager 返回值)

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

class RecoveryOutcome(Enum):
    RECOVERED = "recovered"          # 成功回退到期望界面
    NEEDS_HUMAN = "needs_human"      # 未知界面,已存档
    ALREADY_THERE = "already_there"  # 当前就在期望界面,无需回退
    RECOVERY_FAILED = "failed"       # 回退路径执行失败 (如返回键没反应)

@dataclass
class InterfaceRecoveryResult:
    outcome: RecoveryOutcome
    current_state: Optional[str] = None                       # 识别到的当前界面状态名
    expected_state: Optional[str] = None                      # 期望界面状态名
    path_taken: Optional[list[str]] = None                    # 实际执行的回退路径 (状态名列表)
    actions_executed: Optional[list[dict]] = None             # 实际执行的动作序列
    archive_path: Optional[str] = None                        # 未知界面存档路径 (NEEDS_HUMAN 时)
    error_msg: Optional[str] = None                           # 失败原因 (RECOVERY_FAILED 时)
    screenshots: Optional[list[str]] = None                   # 回退过程中的截图路径 (调试用)
    # 注: 不用 field(default_factory=list) — None 表示"未执行",空列表表示"执行了但路径为空"
```

**字段语义约定**:
- `path_taken=None` + `actions_executed=None` → 未尝试回退 (ALREADY_THERE 或 识别未命中)
- `path_taken=["A","B","C"]` + `actions_executed=[...]` → 尝试了回退但可能未到达 (RECOVERY_FAILED)
- `screenshots` 只在 debug_mode=true 时填充,生产环境保持 None 避免磁盘占用

---

## 5. 核心模块设计

### 5.1 InterfaceRecoveryManager

路径: `agent/src/core/interface_recovery.py`

```python
class InterfaceRecoveryManager:
    """界面恢复管理器 — 节点失败后识别界面 + 回退到期望状态。

    职责:
    1. 识别当前界面 (匹配 interface_states.yaml)
    2. BFS 推理回退路径
    3. 执行回退动作序列
    4. 未知界面存档

    不职责:
    - 不处理临时弹窗 (popup_handler 负责)
    - 不做设备/应用级恢复 (recovery.py 负责)
    - 不修改 pipeline JSON
    """

    def __init__(
        self,
        states_config_path: str,      # interface_states.yaml 路径
        screenshot_fn: Callable,       # 截图函数 (注入,便于测试;实际传入 device.capture_screen)
        template_match_fn: Callable,   # 模板匹配函数 (注入)
        action_executor_fn: Callable,  # 动作执行函数 (注入,点返回键等)
        popup_handler: Optional[Any] = None,  # 复用现有弹窗处理
        archive_dir: str = "debug/unknown_states",
        max_recovery_steps: int = 5,   # 回退最多 5 步,防无限循环
        archive_dedupe_window: int = 10,  # 存档去重窗口秒数 (§10.4)
    ):
        # 加载 yaml 后缓存: self._states, self._transitions, self.safe_states (list[str],供 engine 读取)
        # transient 重试参数硬编码: self._transient_wait_s = 1.5, self._transient_max_retries = 2
        ...
        self.safe_states: list[str] = [...]  # 从 yaml 加载 is_safe_state=true 的状态名,暴露给 engine

    def recover(
        self,
        expected_state: str,
        pipeline_name: str,
        node_id: str,
        node_config: dict,
        execution_context: dict,       # device_id, execution_id, node_type, recovery_attempt, retry_count, previous_node_id, previous_node_result, expected_state_source
    ) -> InterfaceRecoveryResult:
        """主入口: 节点失败后调用,尝试回退到 expected_state。

        execution_context 字段说明 (engine 传入,供 archive context.json 用):
        - device_id: 设备 ID (从 context.device.device_id 取)
        - execution_id: 执行 ID (从 engine._execution_id 取)
        - node_type: 节点类型 (从 node.node_type 取,PipelineNode 字段不在 config 中)
        - recovery_attempt: 当前节点的第几次恢复尝试 (1-based,从 _node_recovery_counts 取)
        - retry_count: 节点自身的重试次数 (从 result.retry_count 取,AutoResult 字段)
        - previous_node_id: 上一成功节点 ID (从 _previous_node_chain[-1]["id"] 取)
        - previous_node_result: 上一节点结果 (固定 "success",因 chain 只存成功节点)
        - expected_state_source: 推断来源 (从 infer_expected_state() 返回的 source 取)
        """
        ...

    def identify_state(self, screenshot) -> tuple[Optional[str], float]:
        """识别当前界面状态。

        Returns:
            (state_name, score) — 命中返回 (状态名, 置信度)
                                  未命中返回 (None, 最高匹配置信度)
        """
        ...

    def find_path(self, from_state: str, to_state: str) -> Optional[list[str]]:
        """BFS 找最短回退路径。

        Returns:
            状态名列表 [from, intermediate1, intermediate2, ..., to]
            无路径返回 None
        """
        ...

    def execute_path(
        self,
        path: list[str],
        expected_state: str,
    ) -> InterfaceRecoveryResult:
        """执行回退路径,每步后截图验证。"""
        ...

    def archive_unknown_state(
        self,
        screenshot,
        context: dict,
    ) -> str:
        """未知界面存档,返回存档目录路径。"""
        ...

    @staticmethod
    def infer_expected_state(
        node_config: dict,
        previous_node_chain: Optional[list[dict]] = None,  # 成功节点链,元素: {"id": str, "config": dict}
        safe_states: Optional[list[str]] = None,
    ) -> tuple[str, str]:
        """确定期望界面状态 (3 级优先级,详见 §3.3)。

        优先级:
        1. 手动标注: node_config["expected_state"] (可选字段)
        2. 自动推断:
           - 模板类识别节点 (template_match/template_match_any/feature_match): 从 config.template 路径推断
           - 非模板识别节点 (OCR/color_detect/neural_network): 路径推断不适用,走递归回溯 (推荐手动标注)
           - 非识别类节点 (click/wait/python_call/...): 递归回溯 previous_node_chain,
             找最近的模板类识别节点或手动标注节点,复用其 expected_state
        3. 降级兜底: safe_states[0] (通常是 main_menu)

        Args:
            previous_node_chain: 成功节点信息列表,元素结构 {"id": node_id, "config": node_config}。
                                 index 0 = 最早成功节点,末尾 = 最近成功节点。
                                 由 engine 维护 (§5.2 的 _previous_node_chain,append 到末尾,超 _max_chain_length 截断老节点)。
                                 递归回溯时从末尾往头遍历 (最近 → 最早),取元素 ["config"] 做推断。

        Returns:
            (state_name, source) — source 取值:
                - "manual": 优先级 1,来自 node_config["expected_state"] 显式标注
                - "auto_inferred": 优先级 2,直接从节点 config 路径推断 (模板类识别节点)
                - "previous_node_chain": 优先级 2,递归回溯命中成功节点链中的识别/标注节点 (非识别类节点 + OCR 节点)
                - "safe_fallback": 优先级 3,降级到 safe_states[0]
            存档 context.json 的 expected_state_source 字段用此值,便于事后分析推断质量
        """
        ...
```

### 5.2 与 PipelineEngine 集成

[engine.py:328-530](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py) 的主循环已是 `while self._current_node_id and iteration < self._max_iterations` + `_resolve_next_node()` 图遍历结构 (非 `for i, node in enumerate(nodes)` 顺序遍历),本方案在其失败路径插入恢复逻辑,**不改变循环结构**。

**失败路径改造** (原 [engine.py:472-484](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L472-L484) 的 `if not continue_on_error: return FAILED` 块):

```python
# engine.py execute() 主循环 (现有结构,仅在失败路径插入恢复逻辑)
# while self._current_node_id and iteration < self._max_iterations:  ← 不变
#     node = self._graph.get_node(self._current_node_id)              ← 不变 (engine.py:361)
#     # 现有节点执行: ThreadPoolExecutor + _execute_node_step (engine.py:389-392)
#     # executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
#     # future = executor.submit(self._execute_node_step, node)        ← 单参数方法 (engine.py:564)
#     # result = future.result(timeout=step_timeout)                   ← 不变
#     # executor.shutdown(wait=False)                                   ← 不变 (engine.py:412)

#     if result.success:                                              ← 不变
#         # 【新增】记录成功节点 (id + config) 到链 (供后续失败节点回溯用)
#         # 注: chain 元素是 {"id": node.id, "config": node.config} 而非裸 config,
#         #     因为 archive 时需要 previous_node_id (见 §4.2 context.json)
#         self._previous_node_chain.append({"id": node.id, "config": node.config})
#         if len(self._previous_node_chain) > self._max_chain_length:
#             self._previous_node_chain = self._previous_node_chain[-self._max_chain_length:]
#         self._node_recovery_counts.pop(node.id, None)  # 清零恢复计数
#         # ... 现有成功路径逻辑 (current_step_index += 1, 取消信号检查, Stop 检查)
#         next_id = self._resolve_next_node(node, result)              ← 不变 (engine.py:518)
#         self._current_node_id = next_id or ""                        ← 不变 (engine.py:519)
#         continue

#     # 节点失败路径 (原 engine.py:472-484)
#     continue_on_error = node.config.get("continue_on_error", False)
#     if not continue_on_error:
#         # 【新增】尝试界面恢复 (最多 max_recovery_retries=2 次)
#         node_recovery_count = self._node_recovery_counts.get(node.id, 0)
#         if self._recovery_manager and node_recovery_count < self._max_recovery_retries:
#             self._node_recovery_counts[node.id] = node_recovery_count + 1
#             expected_state, source = InterfaceRecoveryManager.infer_expected_state(
#                 node.config, self._previous_node_chain, self._safe_states
#             )
#             # 提取 previous_node 信息 (供 archive context.json 用,见 §4.2)
#             prev_node_info = self._previous_node_chain[-1] if self._previous_node_chain else None
#             prev_node_id = prev_node_info["id"] if prev_node_info else None
#             # previous_node_result 从最近一条 step_results 获取 (成功才会进 chain,所以 chain 末尾一定是 success)
#             prev_node_result = "success" if prev_node_info else None
#             recovery_result = self._recovery_manager.recover(
#                 expected_state=expected_state,
#                 pipeline_name=self._context.pipeline_name,
#                 node_id=node.id,
#                 node_config=node.config,
#                 execution_context={
#                     "device_id": getattr(self._context.device, "device_id", None),
#                     "execution_id": self._execution_id,
#                     "node_type": node.node_type,  # 供 archive context.json 的 node_type 字段用 (PipelineNode 字段,不在 config 中)
#                     "recovery_attempt": node_recovery_count + 1,
#                     "retry_count": getattr(result, "retry_count", 0),
#                     "previous_node_id": prev_node_id,
#                     "previous_node_result": prev_node_result,
#                     "expected_state_source": source,
#                 },
#             )

#             if recovery_result.outcome in (RecoveryOutcome.RECOVERED, RecoveryOutcome.ALREADY_THERE):
#                 # 回退成功,重试当前节点 — 不更新 _current_node_id,while 循环重新进入同一 node
#                 # ⚠️ 关键: 回滚 current_step_index (见上方"continue 重试的副作用与处理"表)
#                 # engine.py:470 已对失败节点执行 +1,此处 -1 抵消,保证重试时 step_index 不变
#                 self._context.current_step_index -= 1
#                 logger.info("界面恢复成功 (%s),重试节点 %s (第 %d 次)",
#                             recovery_result.outcome.value, node.id, node_recovery_count + 1)
#                 continue  # _current_node_id 保持不变,重新执行同一 node
#             else:
#                 # NEEDS_HUMAN 或 RECOVERY_FAILED,终止 pipeline (走原有 FAILED 返回路径)
#                 logger.warning("界面恢复失败: %s", recovery_result.error_msg or "需要人工介入")
#                 self._state = PipelineState.FAILED
#                 return PipelineResult(
#                     success=False,
#                     state=PipelineState.FAILED,
#                     data=self._step_results,
#                     error_msg=f"节点 {node.id} 失败,界面恢复: {recovery_result.outcome.value}",
#                     elapsed_time=time.monotonic() - start_time,
#                     step_results=list(self._step_results),
#                     recovery_archive=recovery_result.archive_path,  # 【新增字段】供 backend 展示存档路径
#                 )

#         # 恢复次数耗尽或无 recovery_manager,走原有 FAILED 返回 (engine.py:476-484)
#         if node_recovery_count >= self._max_recovery_retries:
#             logger.warning("节点 %s 恢复重试次数耗尽 (%d 次),终止", node.id, self._max_recovery_retries)
#         self._state = PipelineState.FAILED
#         return PipelineResult(
#             success=False,
#             state=PipelineState.FAILED,
#             data=self._step_results,
#             error_msg=f"节点 {node.id} 执行失败: {result.error_msg}",
#             elapsed_time=time.monotonic() - start_time,
#             step_results=list(self._step_results),
#         )

#     # continue_on_error=True — 失败但跳过,清零恢复计数 (跳过即翻篇,不累积)
#     self._node_recovery_counts.pop(node.id, None)
#     # ... 原有 continue_on_error 路径 (走 _resolve_next_node 到下一节点)
```

**关键点 (与 v4 伪代码的差异)**:
- **循环结构不变** — 现有 `while self._current_node_id` 图遍历已是正确结构,无需"for 改 while"
- **节点执行机制不变** — 现有 `ThreadPoolExecutor.submit(self._execute_node_step, node)` + `future.result(timeout)` 结构([engine.py:389-392](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L389-L392))不变,`_execute_node_step` 是单参数方法([engine.py:564](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L564))
- **重试机制** — 不更新 `_current_node_id` 即可重试当前节点 (图遍历天然支持,无需索引控制)
- **成功路径插入点** — 在 `if result.success:` 分支内、`_resolve_next_node` 调用前,append 成功节点 (id + config) 到链
- **失败路径插入点** — 在 `if not continue_on_error:` 块内、原 `return FAILED` 前,插入恢复逻辑
- **PipelineResult 新增字段** — `recovery_archive: Optional[str]` 供 backend 展示存档路径 (NEEDS_HUMAN 时)

**⚠️ continue 重试的副作用与处理** (v11 关键修复):

engine.py 主循环的现有结构在循环体内有以下"每次循环都会执行"的副作用 (位于 `if not result.success:` 之前):

| 副作用 | 行号 | continue 重试影响 | 处理方案 |
|--------|------|------------------|---------|
| `iteration += 1` | [engine.py:329](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L329) | 每次恢复重试消耗 1 次 iteration 配额 | **接受** — `_max_iterations` 默认 10000 ([engine.py:94](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L94)),单节点最多 2 次恢复 = 最多消耗 3 次 iteration,约 0.03% |
| `self._step_results.append(result)` | [engine.py:419](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L419) | 失败结果 + 重试结果都会记录,产生 2 条 step_results | **接受** — 便于事后审计,失败记录 + 成功记录都能看到;backend 已支持多条 step_results 展示 |
| `record_step()` 调用 | [engine.py:458](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L458) | step_states 也会多一条 FAILED 记录 | **接受** — 同上,审计价值 > 一致性损失 |
| `structured_logger.log_node_event()` | [engine.py:439](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L439) | JSONL 日志多一条失败事件 | **接受** — LLM 诊断需要失败上下文,多记录反而有用 |
| `current_step_index += 1` | [engine.py:470](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L470) | **会导致 step_index 偏移** — 失败节点 +1,重试又 +1,后续节点 step_index 全部 +1 偏移 | **回滚** — continue 前执行 `self._context.current_step_index -= 1` 抵消本次循环的增量,保证重试节点 step_index 不变 |

**current_step_index 回滚的必要性**:
- `current_step_index` 被用于 step_results 索引、UI 步骤展示、sub_pipeline 嵌套层级追踪
- 若不回滚:节点 A (step_index=5) 失败 → 恢复重试 → 重试时 step_index=6 → 后续节点 B 的 step_index 从 7 开始(应为 6)→ UI 展示错位
- 回滚方案:在 recovery 成功后的 `continue` 前,显式 `self._context.current_step_index -= 1`

**iteration 配额边界**:
- `_max_iterations` 默认 10000 ([engine.py:94](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L94))
- 最坏情况:50 个节点,每个节点失败 2 次恢复 = 150 次 iteration (含正常执行 50 + 恢复重试 100),远低于 10000 配额
- 若 pipeline 节点数 > 3000 且频繁触发恢复,需调高 `_max_iterations` 配置 (在 AgentConfig 中暴露,不在 MVP 范围)

**engine 新增成员变量初始化** (在 `PipelineEngine.__init__` 或 `execute()` 开头,`self._context` 就绪后):

```python
# engine.py __init__ 或 execute() 开头新增 (self._context 已由 load() 创建)
self._recovery_manager: Optional[InterfaceRecoveryManager] = getattr(self._context, "recovery_manager", None)
# max_recovery_retries 从 PipelineContext 读取 (orchestrator 在 engine.load() 时从 AgentConfig 注入到 context)
# 与 §5.3 Step 1 的 PipelineContext.max_recovery_retries 字段 + §5.3 Step 3 的 AgentConfig.max_recovery_retries 字段对应
self._max_recovery_retries: int = self._context.max_recovery_retries if self._recovery_manager else 0
self._node_recovery_counts: dict[str, int] = {}                        # 按节点 ID 计数
self._previous_node_chain: list[dict] = []                             # 成功节点 (id+config) 链 (末尾 = 最近)
self._max_chain_length: int = 10                                       # 链最大长度,超出截断老节点
self._safe_states: list[str] = self._recovery_manager.safe_states if self._recovery_manager else []
# self._execution_id 已在 execute() 现有逻辑中初始化 (engine.py:315)
# ⚠️ self._context.pipeline_name 当前在正常执行路径中从未被设置 (只有反序列化 restore() 时填,见 context.py:230)
#    实现时需在 engine.load() 或 execute() 中从 pipeline_json["name"] 或 metadata 中设置,
#    否则 recover() 的 pipeline_name 参数会得到空字符串。详见 §5.3 Step 2 补充。
```

**关键约束**:
- `_max_recovery_retries` — 每个节点最多恢复重试次数,**默认 2** (从 AgentConfig.max_recovery_retries 读取,见 §5.3 Step 3)。防止"恢复成功→重试失败→恢复成功"无限循环
- `_node_recovery_counts: dict[str, int]` — 按节点 ID 计数,**节点成功后清零** (`pop(node.id, None)`,避免跨节点累积);`continue_on_error=True` 跳过的失败节点也清零(跳过即翻篇)
- `_previous_node_chain: list[dict]` — 每次节点成功后 append `{"id": node.id, "config": node.config}` 到链 (v11 修复:含 id 字段,供 archive context.json 的 previous_node_id 字段用)。供下一失败节点的 expected_state 递归回溯用 (§3.3 优先级 2)。链长度超 `_max_chain_length=10` 时截断老节点
- `_safe_states` — 从 `recovery_manager.safe_states` 获取 (Manager 启动时从 `interface_states.yaml` 加载所有 `is_safe_state: true` 的状态名,缓存暴露为属性)
- 恢复次数耗尽 → 直接 FAILED,不再尝试
- **current_step_index 回滚** — recovery 成功后 `continue` 前,执行 `self._context.current_step_index -= 1` 抵消本次循环的增量 (engine.py:470 已对失败节点 +1),保证重试时 step_index 不变 (详见上方"continue 重试的副作用与处理")
- **无 breaking change** — 不改循环结构,仅在失败路径插入恢复逻辑,现有 `goto`/`loop`/`sub_pipeline`/`jump_back` 等控制流节点语义不受影响 (回归测试仍覆盖)

### 5.3 依赖注入

Manager 的依赖通过 `PipelineContext` 注入 (便于测试和替换)。注入路径需扩展 `engine.load()` 参数 + `PipelineContext` 字段 + `AgentConfig` 字段。

**Step 1 — PipelineContext 新增字段** ([context.py:82-132](file:///d:/code/GAF/agent/src/engine/context.py#L82-L132)):

```python
# context.py 新增字段 (与 monitor_manager / llm_client 同级,Runtime-only 不序列化)
@dataclass
class PipelineContext:
    # ... 现有字段顺序:
    #   device / display_context / coord_transformer /  # 设备与显示
    #   monitor_manager / llm_client /                  # 运行时注入组件 (recovery_manager 加这里)
    #   debug_mode / debug_dir /                        # 调试配置
    #   pipeline_name / current_step_index / step_states /  # 序列化字段
    #   variables / pipeline_snapshot / execution_history
    #
    # 【新增】recovery_manager 加在 llm_client 之后、debug_mode 之前,
    #        与 monitor_manager / llm_client 同区域 (Runtime-only 字段聚集)
    recovery_manager: Any | None = None  # Runtime-only,不参与序列化 (restore 后为 None,需调用方重新注入)
    max_recovery_retries: int = 2        # Runtime-only,engine 读取此值控制每节点恢复次数 (由 orchestrator 从 AgentConfig.max_recovery_retries 注入)
```

**注 1**: 现有 `serialize()` / `restore()` 方法是**显式字段枚举**(非 dataclass 自动序列化),现有 Runtime-only 字段(`monitor_manager` / `llm_client` / `debug_mode` / `debug_dir`)均不在其中。新增的 `recovery_manager` 和 `max_recovery_retries` 同样**无需修改这两个方法**,自然不参与序列化。

**注 2** (re-injection 模式差异): 现有 `monitor_manager` / `llm_client` 在 `engine.execute()` 中有 re-injection 逻辑(从 `self._monitor_manager` 缓存恢复到 context)。`recovery_manager` **不采用此模式** — restore 后保持 None,需调用方(orchestrator)显式重新注入。原因:`recovery_manager` 初始化依赖 `interface_states.yaml` 路径 + device + image_processor,自动恢复可能用到过期的 device 引用,不安全。`max_recovery_retries` 作为简单 int,restore 后用默认值 2 即可(engine 会在 `self._recovery_manager is None` 时将 `_max_recovery_retries` 设为 0,禁用恢复)。

**Step 2 — engine.load() 扩展参数** ([engine.py:172-229](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L172-L229)):

```python
# engine.py load() 签名新增 recovery_manager + max_recovery_retries 参数
def load(self, pipeline_json: dict, device=None,
         display_context=None, coord_transformer=None,
         monitor_manager=None,
         debug_mode: bool = False, debug_dir: str = "./debug",
         llm_client=None,
         recovery_manager=None,                     # 【新增】InterfaceRecoveryManager 实例
         max_recovery_retries: int = 2) -> None:    # 【新增】每节点最多恢复次数 (从 AgentConfig 传入)
    # ...
    # 【新增】从 pipeline_json 提取 pipeline_name (现有代码未设置此字段,只有反序列化 restore() 时填)
    # 优先级: pipeline_json["name"] > pipeline_json["metadata"]["name"] > ""
    pipeline_name = pipeline_json.get("name") or (pipeline_json.get("metadata") or {}).get("name", "")
    self._context = PipelineContext(
        device=device,
        display_context=display_context,
        coord_transformer=coord_transformer,
        monitor_manager=monitor_manager,
        debug_mode=debug_mode,
        debug_dir=debug_dir,
        pipeline_snapshot=pipeline_json,
        llm_client=llm_client,
        recovery_manager=recovery_manager,  # 【新增】
        max_recovery_retries=max_recovery_retries,  # 【新增】从 AgentConfig 透传到 context,供 engine 读取
        pipeline_name=pipeline_name,  # 【新增】修复 pipeline_name 未设置问题
    )
    # 缓存用于 execute() 中的 re-injection (与 _monitor_manager / _llm_client 同级)
    self._recovery_manager = recovery_manager
```

> 注: 现有 `PipelineContext` 已有 `pipeline_name` 字段([context.py:127](file:///d:/code/GAF/agent/src/engine/context.py#L127)),但 `engine.load()` 从未设置它(只有 `restore()` 反序列化时填,见 [context.py:230](file:///d:/code/GAF/agent/src/engine/context.py#L230);注意是 `PipelineContext.restore()` 类方法,非 `StepSnapshot.from_dict()`)。本方案需在 `load()` 中显式设置,否则 `recover()` 的 `pipeline_name` 参数会得到空字符串,影响存档目录命名。

**Step 3 — AgentConfig 新增字段**:

```python
# config.py AgentConfig dataclass 新增字段 (全部可选,缺省不启用恢复)
interface_states_path: str | None = None
unknown_state_archive_dir: str = "debug/unknown_states"
max_recovery_steps: int = 5           # Manager 层: 单次 recovery 最多执行几步回退动作
max_recovery_retries: int = 2         # engine 层: 每节点最多恢复重试次数 (与 §5.2 _max_recovery_retries 对应)
archive_dedupe_window: int = 10
custom_tasks_base_dir: str = "."  # python_call 用,Phase 2
```

**Step 4 — orchestrator.execute_pipeline() 初始化 Manager** ([orchestrator.py:634](file:///d:/code/GAF/agent/src/core/orchestrator.py#L634) `execute_pipeline` 入口 + [orchestrator.py:710-954](file:///d:/code/GAF/agent/src/core/orchestrator.py#L710-L954) `_execute_pipeline_inner` 方法;`engine.load()` 调用位于 [orchestrator.py:804-813](file:///d:/code/GAF/agent/src/core/orchestrator.py#L804-L813)):

```python
# orchestrator.py _execute_pipeline_inner() 新增 (在 engine.load() 调用前)
# 注意: 此作用域内可用变量 — self._config (AgentConfig), self._image_processor,
#        self._monitor_manager, device (已解析)
recovery_manager = None
states_config_path = self._config.interface_states_path  # 从 AgentConfig 读取
if states_config_path and Path(states_config_path).is_file():
    # ⚠️ 关键: template_match_fn 需包装 resolve_resource_path
    # interface_states.yaml 的 detect_templates.template 路径格式与 pipeline JSON 一致
    # (如 "public/主界面.png" 或 "BrownDust-II/templates/public/主界面.png"),
    # 但 find_template 内部 _load_template 用 os.path.isfile 直接检查,不做路径解析。
    # 若不包装,identify_state 调用 find_template 时会找不到模板文件。
    # 包装层先 resolve_resource_path 转绝对路径,再调 find_template。
    from engine.resource_resolver import resolve_resource_path
    def _resolved_find_template(screenshot, template, roi=None, threshold=0.8):
        resolved = resolve_resource_path(template)
        if resolved is None:
            logger.warning("interface_states template 路径解析失败: %s", template)
            return None
        return self._image_processor.find_template(
            screenshot, resolved, roi=roi, threshold=threshold
        )

    recovery_manager = InterfaceRecoveryManager(
        states_config_path=states_config_path,
        screenshot_fn=device.capture_screen,  # BaseDevice.capture_screen (devices/base.py:77)
        template_match_fn=_resolved_find_template,  # 包装了 resolve_resource_path 的 find_template
        action_executor_fn=lambda action: self._execute_recovery_action(device, action),
        popup_handler=self._monitor_manager.popup_handler if self._monitor_manager else None,  # monitor/manager.py:173
        archive_dir=self._config.unknown_state_archive_dir,
        max_recovery_steps=self._config.max_recovery_steps,
        archive_dedupe_window=self._config.archive_dedupe_window,
    )

# engine.load() 调用新增 recovery_manager + max_recovery_retries 参数
# max_recovery_retries 从 AgentConfig 读取,由 engine.load() 写入 PipelineContext
engine.load(
    pipeline_json,
    device=device,
    display_context=display_context,
    coord_transformer=coord_transformer,
    monitor_manager=self._monitor_manager,
    debug_mode=effective_debug_mode,
    debug_dir=effective_debug_dir,
    llm_client=llm_client,
    recovery_manager=recovery_manager,  # 【新增】
    max_recovery_retries=self._config.max_recovery_retries if recovery_manager else 0,  # 【新增】
)
```

**Step 5 — orchestrator 新增辅助方法**:

```python
# orchestrator.py 新增辅助方法 (transitions.action 执行器)
# 注: 需 import resolve_resource_path (engine.resource_resolver) —
#     interface_states.yaml 的 template 路径格式与 pipeline JSON 一致
#     (如 "public/主界面.png" 或 "BrownDust-II/templates/public/主界面.png"),
#     find_template 不做路径解析,必须先经 resolve_resource_path 转绝对路径
from engine.resource_resolver import resolve_resource_path

def _execute_recovery_action(self, device, action: dict) -> bool:
    """执行 transitions.action (template_match / key_press / click / swipe / wait)。

    Returns:
        True — 动作执行成功 (不代表界面已变化,由调用方截图验证)
        False — 动作执行失败 (如 template_match 未命中)
    """
    action_type = action.get("type")
    if action_type == "template_match":
        template = action["template"]
        threshold = action.get("threshold", 0.8)
        roi = action.get("roi")
        # ImageProcessor.find_template (processor.py:61) 签名:
        #   find_template(screenshot, template, roi: dict|None, threshold) -> dict|None
        #   roi 格式: {"x":, "y":, "w":, "h":} (非列表)
        #   返回: {"x", "y", "w", "h", "confidence"} 或 None
        # 注意: interface_states.yaml 的 roi 是 [x, y, w, h] 列表格式 (§4.1),
        #       调用前需转换为 dict 格式: {"x": roi[0], "y": roi[1], "w": roi[2], "h": roi[3]}
        roi_dict = None
        if roi and isinstance(roi, list) and len(roi) == 4:
            roi_dict = {"x": roi[0], "y": roi[1], "w": roi[2], "h": roi[3]}
        # ⚠️ 关键: 必须先经 resolve_resource_path 解析模板路径
        # interface_states.yaml 的 template 路径格式与 pipeline JSON 一致
        # (支持 "public/主界面.png" 短路径和 "BrownDust-II/templates/public/主界面.png" 全路径)
        # find_template 内部 _load_template 用 os.path.isfile(path) 直接检查,
        # 不做路径解析,传入相对路径会找不到文件
        resolved_template = resolve_resource_path(template)
        if resolved_template is None:
            logger.warning("recovery action template 路径解析失败: %s", template)
            return False
        match_result = self._image_processor.find_template(
            device.capture_screen(), resolved_template, roi=roi_dict, threshold=threshold
        )
        if match_result and action.get("click_on_match", True):
            device.click(match_result["x"], match_result["y"])
        return match_result is not None
    elif action_type == "key_press":
        device.key_press(action["key"])
        return True
    elif action_type == "click":
        device.click(action["x"], action["y"])
        return True
    elif action_type == "swipe":
        device.swipe(
            action["x1"], action["y1"], action["x2"], action["y2"],
            duration=action.get("duration", 500),
        )
        return True
    elif action_type == "wait":
        time.sleep(action["duration"] / 1000.0)
        return True
    else:
        logger.warning("未知 recovery action 类型: %s", action_type)
        return False
```

**配置项** (AgentConfig 字段,全部可选,缺省时不启用恢复机制):

> 注: 除上述 5 步外,还需扩展 `PipelineResult` ([engine.py:46-71](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L46-L71)) 新增 `recovery_archive: str = ""` 字段,供 engine 在恢复失败时传递存档路径给 backend (NEEDS_HUMAN 时非空,供前端展示"查看存档"入口)。现有字段含 `success / state / data / error_msg / elapsed_time / step_results / structured_log_path`,需追加在 `structured_log_path` 之后。

| 配置键 | 类型 | 默认值 | 说明 | 适用 Phase |
|--------|------|--------|------|-----------|
| `interface_states_path` | str | None | `interface_states.yaml` 路径;None 或文件不存在 → 不启用恢复 | Phase 1 |
| `unknown_state_archive_dir` | str | `"debug/unknown_states"` | 未知界面存档目录 | Phase 1 |
| `max_recovery_steps` | int | 5 | 单次回退最多步数 | Phase 1 |
| `max_recovery_retries` | int | 2 | 每节点最多恢复尝试次数 (engine 层,非 Manager 层) | Phase 1 |
| `archive_dedupe_window` | int | 10 | 存档去重窗口秒数 (§10.4 第二层防护),同一 (pipeline,node) 在窗口内不重复存档 | Phase 1 |
| `custom_tasks_base_dir` | str | `"."` (当前工作目录,假定 agent 从项目根目录启动) | python_call 节点的 module_path 相对此目录解析;路径校验也基于此 | Phase 2 |

**硬编码常量 (MVP 不暴露为配置)**:
- transient 重试等待 1.5s + 最多 2 次 (§3.2 步骤 3) — 硬编码在 Manager
- `_max_chain_length = 10` (engine 内部链长度上限) — 硬编码在 engine

---

## 6. 未知界面处理流程

### 6.1 人工通道 (MVP 实现)

1. 用户发现任务失败 → 查 `debug/unknown_states/` 最新存档
2. 打开 `screenshot.png` 看是什么界面
3. 查 `context.json` 了解: 哪个 pipeline 哪个节点失败、期望在哪个界面
4. 编辑 `interface_states.yaml`:
   - 新增 states 条目 (用截图里的特征定义 detect_templates)
   - 新增 transitions 条目 (从这个界面到已知界面的回退动作)
5. 重新跑任务 → Manager 识别新状态 → 走回退路径

**存档生命周期管理**:
- `debug/unknown_states/` 已被现有 `/debug/` `.gitignore` 规则覆盖 (根目录锚定),只需加 `!debug/unknown_states/.gitkeep` 例外保留占位文件 (避免大量截图污染仓库)
- 存档不自动清理 — 用户补充 `interface_states.yaml` 后,旧存档保留作历史参考资料,可手工删除
- 建议每月清理一次超过 30 天的存档 (用户手工,不在 MVP 自动化)

### 6.2 LLM 通道 (预留,不在 MVP 实现)

> **⚠️ 本节为未来设计预留,MVP 不实现。等用户主动启动后再开始。**

未来接入时的设计方向 (供参考):

1. Manager 存档后,可选触发 LLM 分析:
   - 输入: 截图 (base64) + context.json + 当前 interface_states.yaml
   - 输出: 推荐的 state 定义 + transition 定义
2. LLM 推荐写入 `debug/unknown_states/{id}/llm_suggestion.yaml` (不直接改主配置)
3. 人工审核 llm_suggestion.yaml → 合并到 `interface_states.yaml`
4. 重新跑任务验证

**关键约束**: LLM 只写建议文件,不直接修改主配置,需人工审核。

### 6.3 渐进式完善

初始状态 `interface_states.yaml` 可以只有 `main_menu` 一个状态 (安全状态),transitions 为空。

运行中积累未知界面存档 → 人工逐步补充 → 状态图越来越完善 → 回退成功率提升。

---

## 7. 与现有模块的边界

| 模块 | 职责 | 与本方案关系 |
|------|------|-------------|
| `popup_handler.yaml`（资源包 `resources/<Game>/monitors/`，运行时数据） | 临时弹窗 (广告/奖励) | Manager 在识别界面前先让 popup_handler 跑一遍,关掉临时弹窗 |
| [recovery.py](file:///d:/code/GAF/agent/src/core/recovery.py) | 5 层恢复 (步骤→任务→应用→设备→人工) | 互补: recovery.py 管设备级故障,Manager 管界面级漂移 |
| [retry.py](file:///d:/code/GAF/agent/src/core/retry.py) | 重试装饰器 (截图/输入/网络) | 互补: retry.py 管瞬时失败,Manager 管界面状态错误 |
| [state_machine.py](file:///d:/code/GAF/agent/src/core/state_machine.py) | state_machine 模式任务执行 | 不交互: 本方案仅针对 pipeline 模式 |
| [pipeline_engine.py](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py) | Pipeline 执行 | 集成点: engine 失败路径调用 Manager |

---

## 8. 测试策略

### 8.1 单元测试 (Manager 独立测试)

- `test_identify_state`: mock 截图 + mock template_match → 验证状态识别
- `test_identify_state_transient_retry`: 识别未命中 → 等 1.5s 重试 2 次 → 第 2 次命中 (mock loading 消散场景)
- `test_find_path`: 构造状态图 → 验证 BFS 最短路径
- `test_execute_path`: mock 动作执行 → 验证逐步回退
- `test_archive_unknown_state`: 验证存档目录+文件结构
- `test_archive_dedupe`: 同一 (pipeline,node) 在 archive_dedupe_window 内不重复存档
- `test_infer_expected_state`: 各节点类型 → 验证推断规则
- `test_infer_expected_state_ocr`: OCR 节点未标注 → 走递归回溯 (验证 OCR 不走路径推断)
- `test_infer_expected_state_chain_backtrack`: click 节点失败 → 回溯命中链中第 2 个 template_match 节点
- `test_template_path_resolution`: interface_states.yaml 中短路径 "public/主界面.png" → 经 resolve_resource_path 解析 → find_template 能加载模板 (验证 §5.3 Step 4 的 _resolved_find_template 包装)
- `test_recovery_action_template_path_resolution`: transitions.action 的 template 路径 → 经 resolve_resource_path 解析 → 动作执行成功 (验证 §5.3 Step 5 的路径解析)

### 8.2 集成测试 (与 engine 集成)

- `test_engine_recovery_recovered`: 节点失败 → Manager 回退成功 → 节点重试成功
- `test_engine_recovery_needs_human`: 节点失败 → 未知界面 → 存档 + FAILED
- `test_engine_recovery_already_there`: 节点失败但当前就在期望界面 → 直接重试 (跳过回退)
- `test_engine_recovery_max_retries_exhausted`: 同一节点连续失败 2 次 → 第 3 次直接 FAILED,不再调用 Manager
- `test_engine_recovery_count_reset_on_success`: 节点 A 失败恢复 1 次后成功 → 节点 A 的 `_node_recovery_counts` 清零;节点 A 再次失败时从 0 开始计数
- `test_engine_recovery_failed`: Manager 返回 RECOVERY_FAILED (回退动作执行失败) → engine 返回 FAILED + 暂停
- `test_engine_control_flow_compatible`: 验证主循环插入恢复逻辑后,现有 `goto`/`loop`/`sub_pipeline`/`jump_back`/`stop` 节点语义无 regression
- `test_engine_recovery_step_index_consistency`: 节点 A 失败 → recovery 成功 → 重试成功 → 验证节点 B 的 step_index 不偏移 (回滚机制生效)
- `test_engine_recovery_cancel_during_recovery`: recovery 执行期间设置 _cancel_event → recovery 跑完后 engine 下一轮循环检测到取消 → 返回 CANCELLED (验证 §10.6 设计)

### 8.3 回归测试

- 现有 12 个 BD2 pipeline 零改动 → vitest + tsc 无 regression
- 现有 agent 测试全通过

---

## 9. 实现范围

### 9.1 Phase 1 — 界面恢复 MVP

**包含**:
- [x] `interface_recovery.py` 核心模块 (识别 + BFS + 回退 + 存档)
- [x] `interface_states.yaml` 初始版本 (仅 main_menu 状态) — S2-2.7 (2026-08-17) 落地: `resources/BrownDust II/interface_states.yaml` (main_menu + map_view + ESC 回退转移)
- [x] engine.py 失败路径集成 (插入恢复逻辑 + load() 加 recovery_manager 参数 + pipeline_name 设置,无循环结构改造) — S2-2.7 (2026-08-17) 补齐 orchestrator 注入 (`_execute_pipeline_inner` + `_execute_recovery_action` + template 路径解析包装)
- [x] 未知界面存档机制
- [x] 单元测试 + 集成测试 (S2-2.7 新增 `agent/tests/test_s27_recovery_wiring.py`)

**不含 (后续迭代)**:
- LLM 自动分析未知界面 (需 LLM 接入)
- 状态图可视化编辑器 (前端)
- 状态图自动学习 (从历史存档自动归纳)
- state_machine 模式支持 (state_machine 自带卡顿检测,不在本方案范围)
- 多游戏复用 (先 BD2,架构预留)

### 9.2 Phase 2 — Python 代码任务节点

**包含** (详见 §13):
- [ ] `python_call` 节点实现 (文件路径加载 + 函数调用 + 超时 + 路径校验)
- [ ] `custom_tasks/` 目录复用 + README + 示例任务
- [ ] 单元测试
- [ ] pipeline-authoring-guide 文档更新

**不含**:
- ❌ 前端 Editor UI 支持 (手写 JSON)
- ❌ `exec()` 内嵌代码模式 (永久不开放)
- ❌ state_machine 模式三套表达统一 (独立技术债)

### 9.3 Phase 依赖关系

```
Phase 1 (界面恢复 MVP) ──┐
                         ├─→ Phase 1 完成后,Phase 2 集成测试
Phase 2 (python_call) ───┘
```

- Phase 2 依赖 Phase 1 的恢复机制 (python_call 失败走恢复路径)
- 两个 Phase 可并行开发
- Phase 2 可独立上线 (无 Phase 1 时 python_call 失败直接 FAILED,无恢复)

---

## 10. 开放问题

### 10.1 回退动作失败怎么办?

**问题**: 回退路径上某一步动作失败 (如返回键点了但界面没变)。

**方案**: 每步动作后验证,连续 2 次失败则终止回退,转存档 (NEEDS_HUMAN)。`max_recovery_steps=5` 防无限循环。

### 10.2 expected_state 推断不准怎么办?

**问题**: 自动推断的 expected_state 可能错 (如 template_match 节点的 template 不在 public/)。

**方案**: 推断失败时降级到 `main_menu` (安全状态),回退到主界面后由 routine chain 决定是否重试整个 pipeline。

### 10.3 状态图循环引用?

**问题**: transitions 可能构成环 (A→B→A)。

**方案**: BFS 天然处理环 (访问过的节点不再入队),不会无限循环。YAML 加载时校验显式自环 (A→A) 并拒绝。

### 10.4 瞬时状态 (transient) 导致误报与重复存档?

**问题**: 节点失败后识别界面时,可能遇到 transient 状态导致误判:
- **加载界面 (loading)**: 几秒后自动消失,识别为未知界面会误报
- **网络卡顿/点击被吞**: 界面短暂无响应或停留在过渡帧,识别为未知界面
- **点击失效**: 点击未生效,界面短暂停留在错误状态后自动恢复

若直接把 transient 状态当未知界面存档,会污染存档目录,且触发不必要的 NEEDS_HUMAN。

**方案** (两层防护):

**第一层 — 识别阶段 transient 重试** (§3.2 步骤 3 已定义):
- 识别未命中已知状态时,不立即存档,先等待 1.5s 重试识别(最多 2 次,共约 3s)
- 重试期间命中已知状态 → transient 已恢复,正常走回退路径
- 重试 2 次仍未命中 → 确认为真未知界面,才走步骤 6 存档
- 覆盖场景: loading 消散、网络恢复、点击延迟生效

**第二层 — 存档去重** (防止 transient 重试也未能识别的边界情况):
- 存档前检查: 同一 `(pipeline_name, node_id)` 组合在 `archive_dedupe_window` 秒内已有存档 → 跳过本次存档,仅记录日志
- 实现方式: Manager 维护内存缓存 `last_archive_time: dict[tuple[str, str], float]`,存档时检查时间差
- 窗口默认 10 秒 (BD2 loading 常持续 5-10s),可通过 agent config `archive_dedupe_window` 配置
- 进程重启失效可接受 — 重启后同一节点再失败会重新存档,不影响正确性

**长期方案** (不在 MVP): 把 loading 界面也加入 `interface_states.yaml` 作为已知状态,`is_safe_state: false`,transitions 中标记"等待 N 秒后重新识别"。

### 10.5 主循环兼容性?

**问题**: engine.py 主循环插入恢复逻辑后,是否影响现有控制流节点 (`goto`/`loop`/`sub_pipeline`/`jump_back`/`stop`) 的语义?

**事实核查**: engine.py 主循环 ([engine.py:328-530](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L328-L530)) 已是 `while self._current_node_id and iteration < self._max_iterations` + `_resolve_next_node()` 图遍历结构,**不是 `for` 顺序遍历**,因此:

**方案** (无循环结构改造,仅插入分支):
- 现有控制流节点通过 `_resolve_next_node` ([engine.py:667-768](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L667-L768)) 返回 next_node_id,engine 根据返回值更新 `_current_node_id` — 这部分逻辑与恢复插入点无关,完全不受影响
- `stop` 节点语义: 通过 `_stop_requested` context 变量 ([engine.py:501-515](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L501-L515)) 触发 `return PipelineResult(COMPLETED)`,不依赖循环结构
- `goto`/`loop`/`sub_pipeline`/`jump_back`: 通过 `_resolve_next_node` 返回跳转目标,恢复逻辑仅在 `if not continue_on_error:` 失败分支内,不影响成功路径的节点流转
- 恢复重试机制 (不更新 `_current_node_id` 重新执行同一节点) 是图遍历天然支持的 — `_current_node_id` 保持不变,while 循环重新 `get_node(self._current_node_id)` 获取同一节点
- 回归测试 `test_engine_control_flow_compatible` 覆盖所有控制流节点 + 恢复重试场景

### 10.6 recovery 期间收到取消信号怎么办?

**问题**: engine 主循环在每轮迭代开始时检查 `_cancel_event` ([engine.py:332-342](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L332-L342)),节点执行完成后也会再次检查 ([engine.py:487-497](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L487-L497))。但 `InterfaceRecoveryManager.recover()` 是同步阻塞调用,期间不检查 `_cancel_event` — 若用户在 recovery 执行中按下取消,recovery 会继续执行完所有回退动作 + 存档后才返回。

**方案** (MVP 接受现状,不额外处理):
- recovery 单次执行时间有界: 识别 (~0.5s) + popup 处理 (~1s) + BFS (<10ms) + 回退动作 (max 5 步 × ~1s = 5s) + 存档 (<0.5s) ≈ 最坏 7s
- recovery 返回后,engine 在下一轮循环开始时 ([engine.py:332](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L332)) 会立即检查到 `_cancel_event` 并返回 CANCELLED — 用户取消请求最多延迟 7s 生效,可接受
- **不在 recover() 内部检查 _cancel_event 的原因**:
  1. recover() 设计为 engine 无关的纯逻辑模块 (便于单元测试),不持有 engine 引用
  2. recovery 中途打断会导致界面处于"回退一半"的中间状态,比让 recovery 跑完更糟
  3. 若 recovery 已存档(NEEDS_HUMAN),取消后存档仍保留 — 用户可从存档看到取消时的界面状态
- **未来优化** (不在 MVP): 若需更快的取消响应,可在 recover() 内每步回退动作后检查 cancel_event,但需 Manager 持有 cancel_event 引用 (通过构造函数注入)。此改动会破坏 Manager 的 engine 无关性,需评估

### 10.7 continue 重试的副作用与 step_index 一致性?

**问题**: engine 主循环每次迭代都会执行 `iteration += 1` ([engine.py:329](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L329))、`_step_results.append(result)` ([engine.py:419](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L419))、`record_step()` ([engine.py:458](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L458))、`structured_logger.log_node_event()` ([engine.py:439](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L439))、`current_step_index += 1` ([engine.py:470](file:///d:/code/GAF/agent/src/engine/pipeline_engine.py#L470)) — 这些副作用位于 `if not result.success:` 之前,失败节点和恢复重试都会触发。

**方案** (详见 §5.2 "continue 重试的副作用与处理" 表):
- **iteration / step_results / record_step / structured_logger**: 接受副作用 — 多记录失败信息对审计和 LLM 诊断有价值,且 iteration 配额消耗约 0.03% (3/10000) 可忽略
- **current_step_index**: 回滚 — recovery 成功后 `continue` 前执行 `self._context.current_step_index -= 1` 抵消本次循环的增量,保证重试节点 step_index 不变,后续节点 step_index 不偏移
- **回归测试** `test_engine_recovery_step_index_consistency`: 节点 A (step_index=5) 失败 → recovery 成功 → 重试成功 → 节点 B 的 step_index 应为 6 (非 7)

---

## 11. 关键文件清单

### 11.1 界面恢复 MVP (Phase 1)

| 文件 | 操作 | 说明 |
|------|------|------|
| `agent/src/core/interface_recovery.py` | 新增 | 核心模块 |
| `resources/BrownDust-II/interface_states.yaml` | 新增 | 状态图配置 |
| `agent/src/engine/pipeline_engine.py` | 修改 | 失败路径插入恢复逻辑 + load() 加 recovery_manager + max_recovery_retries 参数 + PipelineResult 加 recovery_archive 字段 (约 80 行,无循环结构改造) |
| `agent/src/engine/context.py` | 修改 | 加 recovery_manager + max_recovery_retries 字段 (Runtime-only,不序列化) |
| `agent/src/core/orchestrator.py` | 修改 | `_execute_pipeline_inner` 初始化 Manager + template_match_fn 包装 resolve_resource_path + 注入 engine.load + 新增 `_execute_recovery_action` 方法 (含 template 路径解析) |
| `agent/src/core/config.py` | 修改 | AgentConfig 新增 6 个字段 (interface_states_path / unknown_state_archive_dir / max_recovery_steps / max_recovery_retries / archive_dedupe_window / custom_tasks_base_dir) |
| `agent/tests/test_interface_recovery.py` | 新增 | 单元测试 |
| `agent/tests/test_s27_recovery_wiring.py` | 新增 | 集成测试 |
| `debug/unknown_states/.gitkeep` | 新增 | 存档目录占位 |
| `.gitignore` | 修改 | 现有 `/debug/` 规则已覆盖存档目录(根目录锚定),只需加 `!debug/unknown_states/.gitkeep` 例外保留占位文件 |

### 11.2 Python 代码任务节点 (Phase 2)

| 文件 | 操作 | 说明 |
|------|------|------|
| `agent/src/engine/nodes/python_call.py` | 新增 | `python_call` 节点实现 (约 120 行) |
| `agent/src/engine/nodes/__init__.py` | 修改 | 加 `python_call` 到 import 列表 (1 行) |
| `resources/BrownDust-II/custom_tasks/README.md` | 新增 | 函数签名契约 + 示例说明 (目录已存在,无需 .gitkeep) |
| `agent/tests/engine/nodes/test_python_call.py` | 新增 | 单元测试 (约 100 行) |
| `docs/business/tasks/pipeline-authoring-guide.md` | 修改 | §2 节点目录加 `python_call` + §2.8 契约表 + §8 安全说明 |

---

## 12. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 界面识别误判 (模板匹配假阳性) | 中 | 回退到错误界面 | threshold ≥ 0.8 + ROI 限定 + 多模板 OR 逻辑 |
| 回退路径执行中游戏状态变化 | 中 | 回退失败 | 每步验证 + max_steps 限制 + 失败转存档 |
| expected_state 推断覆盖率不足 | 低 | 降级到 main_menu | 可接受,安全兜底 |
| 状态图维护成本 | 中 | 人工负担 | 渐进式 + LLM 辅助 (未来) |
| engine.py 改动引入 regression | 中 | pipeline 执行异常 | 集成测试 + feature flag (可通过 config 关闭 Manager) |
| python_call 节点死循环/资源耗尽 | 低 | agent 卡死 | `config.timeout` 字段 + 子线程执行 + 超时强制终止 |
| python_call 模块加载失败 | 中 | 节点执行失败 | 模块路径校验 + 清晰错误信息 + 失败走界面恢复路径 |
| custom_tasks/ 目录 .py 文件被误当 JSON 加载 | 低 | 加载错误 | 加载器按文件扩展名分流 (.py → spec_from_file_location, .json → 现有 chain 模板) |

---

## 13. Python 代码任务节点扩展 (Phase 2)

> **状态**: 设计预留,不在界面恢复 MVP 内实现。界面恢复 Phase 1 完成后启动。

### 13.1 背景与动机

pipeline 模式下 40 个节点类型覆盖了画面识别/输入操作/控制流等通用能力,但**不支持在 pipeline 中途执行任意 Python 代码**。某些场景需要 Python 代码:

- **复杂计算**: 根据多个 OCR 结果计算下一目标坐标 (超出 `custom_match` 表达式能力)
- **外部集成**: 调用外部 API (如游戏 wiki 数据查询)、解析复杂 JSON 响应
- **自定义校验**: 多步骤状态联合校验 (比 `custom_verify` 更灵活,且能在 pipeline 中途执行)
- **复用现有 Python 库**: 如用 `numpy` 做图像分析、`pandas` 处理表格数据

**设计目标**: 让 Python 代码作为 pipeline 的一个节点 (`python_call`),天然纳入 pipeline 编排 + 界面恢复机制,无需额外的任务加载层。

### 13.2 节点定义

新增 `python_call` 节点类型,通过 `importlib.util.spec_from_file_location` 按文件路径加载 Python 模块,调用指定函数。

**JSON 用法示例**:

```json
{
  "id": "calc_next_position",
  "node_type": "python_call",
  "config": {
    "module_path": "resources/BrownDust-II/custom_tasks/position_calc.py",
    "function": "compute_offset",
    "args": {
      "prev_x_var": "match.x",
      "prev_y_var": "match.y",
      "stage": "hard_7"
    },
    "output": "calc_result",
    "timeout": 5.0,
    "expected_state": "map_view"
  },
  "next_node_id": "click_target"
}
```

**config 字段说明**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `module_path` | str | ✅ | Python 文件相对路径 (相对 agent 配置的 `custom_tasks_base_dir`,见 §5.3),如 `resources/BrownDust-II/custom_tasks/position_calc.py` |
| `function` | str | ✅ | 模块中要调用的函数名 |
| `args` | dict | ❌ | 传给函数的关键字参数 (值可以是字面量,也可以是 `${var_name}` 引用 context 变量) |
| `output` | str | ❌ | 函数返回值存入 context 的变量名 (不填则不存储) |
| `timeout` | float | ❌ | 执行超时秒数,默认 5.0;超时则节点失败 |
| `expected_state` | str | ❌ | 手动标注期望界面状态 (供 §3.3 三级优先级推断用) |

### 13.3 文件路径加载机制

**为什么不用 `importlib.import_module` (dotted path)**:
- dotted path 要求模块在 `sys.path` 中,需额外注入 `resources/<game>/custom_tasks/` 到 sys.path
- 多游戏共存时包名冲突 (如 BrownDust-II 和 default 都有 `login.py`)
- 需要按 active game_profile 动态切换 sys.path,复杂且易错

**采用 `importlib.util.spec_from_file_location` (文件路径加载)**:

```python
# python_call.py 核心加载逻辑
import importlib.util
from pathlib import Path

def _load_module(module_path: str, base_dir: str):
    """按文件路径加载 Python 模块。
    
    Args:
        module_path: 相对路径 (相对 base_dir)
        base_dir: agent 配置的 custom_tasks_base_dir,如项目根目录
    """
    # 显式 join base_dir,不依赖 os.getcwd()
    abs_path = (Path(base_dir) / module_path).resolve()
    if not abs_path.is_file():
        raise FileNotFoundError(f"Python 任务模块不存在: {abs_path}")
    
    spec = importlib.util.spec_from_file_location(
        f"custom_task_{abs_path.stem}",  # 模块名(避免冲突)
        abs_path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块: {abs_path}")
    
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # 执行模块代码
    return module
```

**优势**:
- ✅ 无 sys.path 污染
- ✅ 多游戏天然隔离 (不同游戏用不同绝对路径)
- ✅ module_path 在 JSON 中显式可见,审计清晰
- ✅ 模块名用 `custom_task_{stem}` 前缀避免与标准库冲突

### 13.4 函数签名契约

`python_call` 节点调用的 Python 函数必须遵循以下签名:

```python
def my_function(
    device,              # BaseDevice 实例 (截图/点击/按键)
    context,             # PipelineContext 实例 (变量读写/历史记录)
    **kwargs,            # config.args 传递的业务参数
) -> dict:
    """
    Python 代码任务函数签名契约

    Args:
        device: 设备操作接口,同 pipeline 节点用的 context.device (截图 device.capture_screen() / 点击 device.click() 等)
        context: 完整 pipeline 上下文,可读写变量 (context.get_variable / context.set_variable)
        **kwargs: config.args 的所有键值对,值已解析 ${var_name} 引用

    Returns:
        dict: 返回值会存入 config.output 指定的 context 变量

    Raises:
        任何异常都会被节点捕获,转为 fail_result,触发界面恢复机制

    注:
        - 不注入 image_processor (PipelineContext 无此字段,engine 层不持有 ImageProcessor 实例)
        - 若需图像处理能力,用户在函数内自行 import (如 from utils.image_processor import ...),
          或通过 device.capture_screen() 获取截图后用 cv2/numpy 自行处理
        - 这与 pipeline 内置节点 (template_match 等) 的实现路径不同 — 内置节点通过
          orchestrator 注入的 image_processor 工作,但 python_call 作为用户代码入口,
          保持签名简洁,不暴露内部 ImageProcessor 实例
    """
    # 业务逻辑
    prev_x = kwargs["prev_x"]  # 从 config.args 传入
    stage = kwargs["stage"]

    # 可访问 device
    screenshot = device.capture_screen()

    # 计算结果
    result = {"x": prev_x + 100, "y": 200}

    return result  # 存入 context.variables["calc_result"]
```

**参数解析规则** (config.args 值的转换):

| config.args 值 | 解析为 | 示例 |
|----------------|--------|------|
| 字面量 (str/int/float/bool) | 原样传入 | `"hard_7"` → `"hard_7"` |
| `"${var_name}"` | `context.get_variable("var_name")` | `"${match.x}"` → context 变量 match.x 的值 |
| dict / list | 递归解析内部 `"${...}"` | `{"offset": "${offset_var}"}` → 内部引用解析 |

### 13.5 与界面恢复的集成

`python_call` 节点天然纳入界面恢复机制:

```
pipeline 执行 → python_call 节点失败 (函数抛异常/超时)
    │
    ├─ continue_on_error=True → 跳过,继续下一节点
    │
    └─ continue_on_error=False (默认)
        │
        ├─ 调用 InterfaceRecoveryManager.recover()
        │   ├─ expected_state 推断:
        │   │   ├─ 优先级 1: config.expected_state (手动标注,python_call 节点推荐用)
        │   │   ├─ 优先级 2: 递归回溯 previous_node_chain (python_call 属非识别类,走 §3.3 回溯逻辑,找最近的模板类识别节点或手动标注节点)
        │   │   └─ 优先级 3: 降级到 safe_states[0]
        │   ├─ 识别当前界面 → BFS 推理回退路径 → 执行回退
        │   └─ 返回 RECOVERED / NEEDS_HUMAN
        │
        ├─ RECOVERED → 重试 python_call 节点 (不更新 _current_node_id,while 循环重新进入同一 node)
        └─ NEEDS_HUMAN → FAILED + 存档
```

**关键点**:
- `python_call` 节点**强烈推荐手动标注 `expected_state`** — 因为 python_call 无 template 字段,直接路径推断不适用;虽有递归回溯兜底,但回溯到的节点可能距离较远,准确性下降
- python_call 节点的失败原因可能是代码 bug (而非界面漂移),但界面恢复机制仍会尝试 — 若恢复后重试仍失败 (max_retries=2 耗尽),会 NEEDS_HUMAN + 存档,用户可从存档判断是代码 bug 还是界面问题
- timeout 超时不视为界面漂移,但节点仍返回 fail_result,走标准失败路径

### 13.6 安全考虑

**威胁模型**:
- pipeline JSON 中的 `module_path` 指向 agent 机器上的 .py 文件
- 攻击面: 能写入 pipeline JSON 的人 → 指向任意 .py 文件 → 执行任意 Python 代码

**与 `exec()` 方案对比**:
- ✅ **代码来源可控**: .py 文件必须先部署到 agent 机器 (由 agent 管理员控制),JSON 不能注入新代码
- ✅ **审计清晰**: module_path 在 JSON 中显式可见,可扫描所有 pipeline 引用了哪些 .py 文件
- ✅ **与 state_machine / custom_verify 模式一致**: [orchestrator.py:220-252](file:///d:/code/GAF/agent/src/core/orchestrator.py#L220-L252) 已有 `importlib.import_module` 加载先例 (state_machine 模式的 build_state_machine 工厂函数)
- ⚠️ **仍可执行任意已部署代码**: 但代码来源由文件系统权限控制,比 `exec(JSON 字符串)` 安全得多

**安全约束**:
- `module_path` 必须在 `custom_tasks_base_dir` 目录下 (路径校验,防止 `../../etc/passwd` 逃逸)
- `timeout` 字段强制 (默认 5 秒),超时通过**协作式中断**(见下方)
- 加载日志记录每次调用的 module_path + function + args (脱敏) + 耗时 + 返回值摘要
- 不开放 `exec()` 内嵌代码模式 (JSON 中不能直接写 Python 代码,必须引用 .py 文件)

**超时处理 — 协作式中断** (Python 子线程无法强制终止,采用协作式):

```python
# python_call.py 超时处理逻辑 (伪代码)
import threading

def _execute_with_timeout(fn, args, timeout: float, context):
    """协作式超时: 主线程等 timeout 秒,超时设标志位,函数自行检查退出。"""
    cancel_event = threading.Event()
    
    def _run():
        try:
            # 把 cancel_event 注入 context,供用户函数检查
            context._python_call_cancel = cancel_event
            result = fn(**args)
            context._python_call_result = result
        except Exception as e:
            context._python_call_error = e
    
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout)
    
    if thread.is_alive():
        # 超时 — 设标志位,daemon 线程任其自然结束(无法强制终止)
        cancel_event.set()
        raise TimeoutError(f"python_call 执行超时 ({timeout}s),已请求中断")
    
    if hasattr(context, "_python_call_error"):
        raise context._python_call_error
    
    return getattr(context, "_python_call_result", None)
```

**用户函数契约补充** (协作式中断):
- 用户函数**应定期检查** `context._python_call_cancel.is_set()`,若为 True 则尽快 return 或 raise
- 长循环场景示例:
  ```python
  def my_long_task(device, context, **kwargs):
      for item in big_list:
          if context._python_call_cancel.is_set():
              raise TimeoutError("用户主动中断")
          process(item)  # 每次迭代检查
      return result
  ```
- **限制**: 若用户函数不检查标志位(如卡在 `time.sleep(100)` 或外部 API 阻塞),daemon 线程会泄漏直到进程结束。文档需明确告知用户配合
- **缓解措施**: 超时后记录 WARNING 日志 (含 module_path + function + thread_id),并在 context 上累计 `_leaked_thread_count`;若单次 pipeline 执行累计泄漏线程 > 5,后续 python_call 节点直接 fail (拒绝执行,避免线程无限累积)
- MVP 不实现进程级强制终止(multiprocessing 跨进程传 device/context 困难)

**路径校验逻辑**:

```python
def _validate_module_path(module_path: str, base_dir: str) -> Path:
    """校验 module_path 必须在 base_dir 目录下,防止路径逃逸"""
    # 显式 join base_dir,不依赖 cwd
    abs_path = (Path(base_dir) / module_path).resolve()
    allowed = Path(base_dir).resolve()

    # is_relative_to 需要 Python 3.9+;agent 要求 3.11+ (pyproject.toml:7),满足
    if not abs_path.is_relative_to(allowed):
        raise ValueError(
            f"module_path 必须在 {allowed} 下,当前: {abs_path}"
        )

    if abs_path.suffix != ".py":
        raise ValueError(f"module_path 必须是 .py 文件: {abs_path}")

    return abs_path
```

### 13.7 示例:BD2 自定义坐标计算任务

**文件结构**:

```
resources/BrownDust-II/custom_tasks/
├── template.json              # 现有 chain 模式模板 (保留)
├── README.md                  # 新增:函数签名契约说明
└── position_calc.py           # 新增:示例 Python 任务
```

**position_calc.py**:

```python
"""BD2 自定义坐标计算任务示例"""

from typing import Any


def compute_offset(
    device: Any,
    context: Any,
    **kwargs,  # 接收 config.args 的所有键值对 (与 §13.4 契约一致)
) -> dict:
    """根据上一匹配位置 + 关卡配置,计算下一点击坐标。

    Args (来自 config.args):
        prev_x_var: context 变量名,存上一匹配的 x 坐标
        prev_y_var: context 变量名,存上一匹配的 y 坐标
        stage: 关卡名 (如 "hard_7")

    Returns:
        {"x": int, "y": int, "confidence": float}
    """
    prev_x = context.get_variable(kwargs["prev_x_var"])
    prev_y = context.get_variable(kwargs["prev_y_var"])
    stage = kwargs["stage"]

    # 关卡偏移表 (可从外部 JSON 加载)
    stage_offsets = {
        "hard_7": {"dx": 100, "dy": 50},
        "hard_8": {"dx": 120, "dy": 60},
    }
    offset = stage_offsets.get(stage, {"dx": 0, "dy": 0})

    result = {
        "x": prev_x + offset["dx"],
        "y": prev_y + offset["dy"],
        "confidence": 0.95,
    }

    # 也可直接操作 device (如预截图分析)
    # screenshot = device.capture_screen()

    return result
```

**pipeline JSON 引用**:

```json
{
  "id": "calc_next_position",
  "node_type": "python_call",
  "config": {
    "module_path": "resources/BrownDust-II/custom_tasks/position_calc.py",
    "function": "compute_offset",
    "args": {
      "prev_x_var": "match_step4.x",
      "prev_y_var": "match_step4.y",
      "stage": "hard_7"
    },
    "output": "next_position",
    "timeout": 3.0,
    "expected_state": "map_view"
  },
  "next_node_id": "click_next_target"
}
```

### 13.8 实现范围 (Phase 2)

**Phase 2 包含**:
- [ ] `python_call.py` 节点实现 (加载 + 调用 + 超时 + 路径校验)
- [ ] `nodes/__init__.py` 注册
- [ ] `custom_tasks/README.md` 函数签名契约文档
- [ ] `position_calc.py` 示例任务
- [ ] 单元测试 (加载/调用/超时/路径校验/变量解析)
- [ ] `pipeline-authoring-guide.md` 文档更新

**Phase 2 不含**:
- ❌ 前端 Editor UI 支持 (python_call 节点初始只能手写 JSON)
- ❌ `exec()` 内嵌代码模式 (安全考虑,永久不开放)
- ❌ state_machine 模式的三套表达统一 (独立技术债,不在本 spec 范围)
- ❌ custom_tasks/ 的 sys.path 注入 (用文件路径加载替代,无此需求)

**与 Phase 1 的依赖关系**:
- Phase 2 **依赖** Phase 1 的界面恢复机制 — python_call 节点失败时走 Phase 1 的恢复路径
- Phase 2 可与 Phase 1 并行开发,但需在 Phase 1 完成后集成测试
- 若 Phase 1 延期,Phase 2 可独立上线 (python_call 节点失败时直接 FAILED,无恢复)
