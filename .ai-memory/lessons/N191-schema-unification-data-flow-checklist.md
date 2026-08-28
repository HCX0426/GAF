---
date: 2026-07-27
topic: [schema-unification, data-flow, refactoring, coordinate-system]
priority: high
cross_refs: [N182, N183, N190, N151]
status: active
created_by: AI
trigger: 执行路径归一化 (spec-2026-07-27-execution-path-unification) 完成后, 用户要求"继续检查数据流", 发现前端 Editor.tsx 仍输出 chain schema ({steps, action_type, next_step}), backend resource_views.py 仍校验 chain schema, agent_selector.py 不识别 pipeline canonical 的 node_type 字段。第二轮用户要求"从识图到匹配到点击等操作，这一路的数据流，类型也查下", 发现 OCR legacy ROI 路径 publish_match_pos 坐标偏移 bug (子图坐标未加 region 偏移)。
symptom: [schema-unification-incomplete, data-flow-breakpoint, output-end-missed, reader-end-missed, no-data-flow-checklist, coord-system-mismatch, roi-offset-missing]
solution: schema 归一化类重构必须跑"数据流全链路扫描" — 不只改执行引擎和数据迁移, 必须扫描所有 schema 输出端 (前端编辑器/API 写入) 和读取端 (后端校验/agent 推断), 用 5 个 grep 模式覆盖, 修复用 adapter 模式。节点间数据流必须验证坐标系统一致性 (logical/physical/sub-image) 和字段映射 (publish_match_pos 写入字段 vs resolve_target 读取字段)。
diff_keywords: [schema-unification, data-flow, chain-schema, coord-system, roi-offset]
related_files:
  - frontend/src/pages/Tasks/Editor.tsx
  - frontend/src/types/models/
  - frontend/src/pages/Tasks/index.tsx
  - backend/tasks/resource_views.py
  - backend/tasks/agent_selector.py
  - backend/tasks/migrations/0049_chain_to_pipeline_unification.py
  - backend/gaf_ai/tests/test_agent.py
  - agent/src/engine/parser.py
  - agent/src/engine/node.py
  - agent/src/engine/target.py
  - agent/src/engine/context.py
  - agent/src/engine/nodes/ocr.py
  - agent/src/engine/nodes/template_match.py
  - agent/src/engine/nodes/click.py
  - agent/src/platforms/windows/input.py
  - agent/src/core/result.py
  - agent/tests/test_ocr.py
  - docs/specs/archived/2026-07/2026-07-27-execution-path-unification.md
  - .ai-memory/lessons/N182-bug-investigation-three-dimensional-root-cause.md
---

# N191 — schema 归一化数据流全链路检查清单 (执行路径归一化残留)

> **家族**: schema-unification / data-flow (与 N182 链路归一化评估同族, 是其在"schema 归一化重构"场景的补全)
> **L1 分级**: L1-中 (新检查清单 + adapter 模式, 3 层分发: lesson + checklist + comment)
> **关联 spec**: spec-2026-07-27-execution-path-unification (执行路径归一化)
> **压缩注 (2026-08-15 治理 spec)**: 本文件由 874 行压缩而来。§10.8 (7 维评分) 已 superseded (被 §10.10 8 维 AI 可调试性评分覆盖, 明细表删除)。§10.9 G1-G7 保留 (L0 env-hardrules N191 段引用"§10.9 G1-G7 架构 review gate")。§5 / §10.5 / §10.9 / §10.11 / §10.12 检查清单原样保留 (L0 引用)。§10.13-§10.15 逐日修复日志压缩为结论。

## 1. 触发原话

> 用户: "继续检查，主要是数据流，类型对不对"
>
> 用户: "继续修，继续找，之前咋没检查这方面，以后都要检查，沉淀下"

## 2. 症状 (5 个文件 chain schema 残留)

执行路径归一化 (chain → pipeline) spec 完成后, 数据流仍存在 5 处 chain schema 残留, 导致前端创建的 task 在 agent 端解析失败 (node_type 为空):

| # | 文件 | 残留类型 | 具体 |
|---|------|---------|------|
| 1 | [frontend/src/pages/Tasks/Editor.tsx](file:///d:/code/GAF/frontend/src/pages/Tasks/Editor.tsx) | 输出端 | `task_definition: { steps: steps.map(...) }` 输出 chain schema, 用 `action_type` 而非 `node_type` |
| 2 | [frontend/src/types/models.ts](file:///d:/code/GAF/frontend/src/types/models.ts) | 类型定义 | `TaskStepConfig` 接口含 `action_type/retry_interval/fallback_action/next_step` 等 chain 字段, 无归一化注释 |
| 3 | [backend/tasks/resource_views.py](file:///d:/code/GAF/backend/tasks/resource_views.py) | 读取端/校验 | `validate()` 强制要求 `steps` + `action` 字段, 拒绝 pipeline schema 的 `nodes` + `node_type` |
| 4 | [backend/tasks/agent_selector.py](file:///d:/code/GAF/backend/tasks/agent_selector.py) | 读取端/推断 | `_get_required_capabilities()` 读 `step.get("type")`, 不识别 `node_type` |
| 5 | [backend/gaf_ai/tests/test_agent.py](file:///d:/code/GAF/backend/gaf_ai/tests/test_agent.py) | 测试数据 | `task_definition={'steps': [{'name': 'step1'}]}` 用 chain schema |

**数据流断点**: 前端输出 `{steps: [{action_type}]}` → backend 原样存储 → agent parser 读 steps, 但 `action_type` 不在归一化白名单 (`type`/`action`) → `node_type` 空 → `PipelineNode.create()` 报 "节点数据中缺少 'node_type' 字段" → 任务失败。

## 3. 根因 (3 维)

1. **spec 设计阶段未做数据流全链路扫描**: spec 把"schema 归一化"等同于"执行引擎归一化 + 数据迁移", 未识别 schema 是**全链路数据契约**, 任何一端不归一化都断流。
2. **N182 链路归一化评估未覆盖 schema 重构场景**: N182 触发条件是 bug 排查, 不是 schema 重构; N151 (§2.0.4) 5 步流程未明确包含数据流扫描。
3. **AI 思维链默认"完成 spec 阶段即完成"**: spec 5 阶段全部 ✅ 后默认任务完成, 不主动跑 grep 扫输出端残留。用户三次提示才完成全链路扫描。

## 4. 修复方案

### 4.1 Adapter 模式: UI flat 字段 → pipeline nested schema

[Editor.tsx](file:///d:/code/GAF/frontend/src/pages/Tasks/Editor.tsx) 新增 `stepToPipelineNode()` (L66-95): 把 flat 字段 (template_id/roi/condition/retry_count/retry_interval/fallback_action/next_step) 映射为 nested node (`node_type` = step.action_type, `retry: {max_retries, base_delay}`, `fallback: {action}`, `next_node_id`)。

**为什么 adapter 而非全量重构 UI**: 表单 Form.Item 用 flat 字段简单; UI 字段名是内部实现不影响契约; 转换函数集中一处, 映射显式可审。

### 4.2 反向 adapter: pipeline node → UI flat (JSON 导入兼容)

`pipelineNodeToStep()` (L101-124) 反向转换, 兼容新旧字段名 (`node_type`/`action`/`type`)。`handleImportJson()` 同时接受 `{nodes}` 和 `{steps}`。

### 4.3 后端读取端归一化

- `resource_views.py` `validate()`: 同时接受 `nodes` (pipeline) 和 `steps` (legacy), `node_type` 或 `action` 任一存在即可
- `agent_selector.py` `_get_required_capabilities()`: 优先读 `node_type`, 退回 `type`

### 4.4 测试数据归一化 + 新增覆盖

- `test_agent.py` 改用 `{'nodes': [{'node_type': 'click'}]}`
- `test_agent_selector.py` 新增 2 个测试: `test_nodes_with_canonical_node_type_field` + `test_node_type_takes_precedence_over_type`

## 5. 防错机制: schema 归一化数据流全链路检查清单

> 触发条件: 任何 schema 归一化类重构 (字段重命名 / 嵌套结构变更 / 字段合并 / schema 版本升级)

```text
□ 数据流全链路识别: 列出 schema 的所有输出端 (前端编辑器/API 写入/外部导入) 和所有读取端 (后端校验/agent 解析/工具推断/测试数据)
□ 输出端 grep 扫描: 用旧 schema 关键字段 (如 action_type/next_step/retry_interval) grep 全仓, 标记每处残留
□ 读取端 grep 扫描: 用旧 schema 关键字段 grep 后端 + agent, 标记每处残留
□ 类型定义审查: 前端 TS 接口 / 后端 serializer / agent dataclass 是否仍含旧字段
□ 测试数据审查: 测试 fixture 是否仍用旧 schema
□ 端到端验证: 用真实数据从前端编辑器跑到 agent 执行, 确认全链路无 schema mismatch
□ 兼容性策略: 旧 schema 是否需要继续支持 (向后兼容) / 何时移除 / migration 是否已转换历史数据
```

## 6. 5 个 grep 模式 (覆盖 schema 归一化扫描)

```bash
# 1. 旧字段名输出端 (前端)
rg "action_type|next_step|retry_interval|fallback_action" frontend/src

# 2. 旧 schema 顶层字段 (task_definition 输出)
rg "task_definition.*steps|params_config.*steps" --type-added py:*.py

# 3. 后端读取旧字段
rg "task_definition\[.steps.\]|task_definition\.get\(.steps." backend

# 4. agent 读取旧字段 (排查 node_type 别名是否覆盖全)
rg "step\.get\(.action.\)|step\.get\(.type.\)|step\.get\(.node_type.\)" agent

# 5. 测试 fixture 旧 schema
rg "task_definition.*steps.*action" --glob "*test*.py"
```

## 7. 验证

- 后端: `test_agent.py::GetTaskConfigTest` + `test_agent_selector.py` → 37 passed (含新增 2 个)
- agent: `test_parser_linear_mode.py` + `test_pipeline_graph.py` → 70 passed
- 前端: `npx tsc -b --noEmit` → Editor.tsx / models.ts / index.tsx 无新错误

## 8. 与现有 lesson 的关系

- **N182** (bug 排查链路归一化评估): N191 是其在"schema 重构"场景的补全
- **N183** (bug 修复三维根因评估): N191 维度 1 即代码层根因的"工作流层"对应物
- **N190** (L0 scope 不足): 同属"规则体系留白", 但 N191 不需要 L0 升级 — 检查清单加到 N151 即可
- **N151** (大修改架构视角): N191 检查清单应作为 N151 第 6 步"数据流验证"子项

## 9. 反思

1. **schema 重构 ≠ 代码重构**: 代码重构影响调用点, schema 重构影响数据流全链路, 必须做全链路扫描。
2. **spec 完成 ≠ 任务完成**: spec 阶段 ✅ 只表示"范围内代码改完", 必须跑端到端验证 (真实数据前端→agent)。
3. **AI 思维链反思纪律**: spec 阶段全部 ✅ 后主动问"数据流端到端可运行吗?", 不等用户提示。

---

## 10. 第二轮: 节点间数据流检查 (识别→匹配→点击)

### 10.1 触发

用户第二轮提示 "从识图到匹配到点击等操作，这一路的数据流，类型也查下"。第一轮只覆盖 schema 归一化, 未覆盖节点间运行时数据流 (publish_match_pos 写入 vs resolve_target 读取, 坐标系统一致性, ROI 偏移传递)。

### 10.2 发现的 bug: OCR legacy ROI 路径坐标偏移

**症状**: [ocr.py](file:///d:/code/GAF/agent/src/engine/nodes/ocr.py) legacy `_crop_region` 路径只裁剪图像, 不把 region 偏移传给 `roi_offset_phys`; `transformer is None` 分支 publish `bx + bw/2` 是子图坐标。下游 click 偏移 (偏移量 = region.x/y)。

**修复**: ① legacy 分支 `roi_offset_phys = (region.get('x',0), region.get('y',0))` ② legacy 分支 `best_center_x = int(bx + bw/2) + roi_offset_phys[0]`。

**回归测试**: `TestOCRNodeLegacyROIOffset` 2 个 (region={100,50} + box=[30,40,20,10] → `_last_match_pos=(140,95)` 而非 (40,45); 无 region 偏移为 0)。

### 10.3 节点间数据流类型契约 (验证后无问题)

| 链路 | 写入端 | 读取端 | 一致性 |
|------|--------|--------|----------|
| OCR → click | `publish_match_pos(x:int, y:int, extra={text})` | `resolve_target` → `device.click(x:int, y:int)` | ✅ |
| template_match → click | 同上 + extra={confidence} | 同上 | ✅ |
| click → `${var}` | `set_variable(f"{id}_click_result", {x, y, ...})` | `_extract_xy` | ✅ |
| OCR → `${var}` | `{texts, boxes, confidence, ...}` (无顶层 x/y) | `_extract_xy` 要求 dict 含 x/y 或 center.x/y | ⚠️ 只能经 `_last_match_pos` 消费 |
| template_match → `${var}` | `{x, y, confidence, ...}` | 同上 | ✅ |

### 10.4 坐标系统一致性 (验证后无问题)

legacy 路径 (无 coord_transformer) 默认 DPI=1.0, physical == logical。修复 OCR ROI 偏移后, 全链路在 DPI=1.0 或 transformer 模式下一致 (template_match legacy 仅在 DPI=1.0 一致)。

### 10.5 节点间数据流检查清单 (补充到 §5)

```text
□ publish_match_pos 写入字段 (x, y, source, extra) 与 resolve_target 读取字段一致 (期望 dict 含 x/y 或 center.x/y 或 list/tuple)
□ 坐标系统标注: 节点 result_data 是否含 coord_system 字段 ("logical" / "physical" / "sub-image")
□ 坐标系统传递: 写入端 logical → 读取端期望 logical (WindowsDevice.click) 或 physical (ADBDevice)
□ ROI 偏移传递: 节点内部 crop 子图后, publish 的坐标是否加回了 ROI 原点偏移
□ 变量引用契约: set_variable 写入的 dict 结构是否满足 _extract_xy 的解析要求 (含 x/y 或 center.x/y)
□ None 兜底: publish_match_pos 的 x/y 不能是 None (已强制 int(x), 但调用方需保证非 None)
```

### 10.6 系统性风险扩展 (2026-07-27 第二轮深度扫描)

| 风险维度 | 是否只在 OCR | 已修复 | 风险等级 |
|---------|:---:|:---:|:---:|
| legacy ROI offset bug | ✅ 是 | ✅ §10.2 | 低 |
| BaseDevice.click/swipe 坐标系契约未文档化 | ❌ 否 | ✅ §10.6.1 | 高→低 |
| 动作节点 target spec 覆盖不全 | ❌ 否 | ✅ §10.6.2 (long_press) | 中→低 |
| sort_select / AnchorNode 不走 transformer | ❌ 否 | ⚠️ 已知限制 | 中 |
| Windows vs ADB 跨设备契约模糊 | ❌ 否 | ✅ §10.6.1 | 高→低 |

**§10.6.1** `BaseDevice.click` docstring 新增坐标系契约段 (Windows 期望 logical / ADB 期望 physical + 跨设备矩阵 + 新 Device 实现要求)。

**§10.6.2** [long_press.py](file:///d:/code/GAF/agent/src/engine/nodes/long_press.py) 新增 `target`/`target_offset` config, 与 ClickNode 对齐 (target 优先于字面量, 支持 `_last_match_pos`/`_anchor_pos`/`${var}`/dict)。`direct_hit`/`multi_swipe`/`multi_touch`/`swipe_until` 保持字面量优先 (多指手势必须显式指定触点, 不适合自动拾取)。

**§10.6.3** sort_select / AnchorNode 是"契约消费者", 假定上游已归一化, 风险在契约未强制校验 (未来可在 publish_match_pos 加 coord_system 标注 + resolve_target 校验)。

### 10.7 第三轮: 架构层归一化深度分析 (12 维度矩阵)

**触发**: 用户第三轮提示 "归一化还得考虑清楚，坐标系的不同设备的，底层和抽象层，图片和ocr，roi，缩放，点击等，架构层" + "选方案要从架构最优来弄，不是有多维度评分吗，咋不用了"。

**根因反思 (AI 工作流缺陷)**: ① spec 阶段缺架构决策矩阵 (writing-plans 不强制列跨设备契约决策点) ② 写完代码只有"跑通"gate 无架构 review ③ lesson 沉淀的是字段反模式不是架构反模式 ④ 归一化完成判定无跨维度覆盖度指标。

**12 维度架构归一化矩阵** (每维 ✅/⚠️/❌): ① 坐标系定义层 ⚠️ (SUB-IMAGE 靠 roi_offset_phys 隐式) ② 设备维度 ⚠️ (BaseDevice 无 click_coord_system 属性) ③ 底层 vs 抽象层 ⚠️ (靠字符串耦合) ④ 识别节点输出层 ⚠️ (box 无 box_coord_system) ⑤ ROI 处理层 ⚠️ (4 节点重复实现) ⑥ 缩放维度 ⚠️ (2 节点重复) ⑦ 点击/动作层 ❌ (click 不读 coord_system) ⑧ 变量/上下文层 ⚠️ ⑨ 日志/可观测层 ⚠️ ⑩ 配置/数据契约层 ⚠️ ⑪ 错误处理/退化层 ❌ (静默退化) ⑫ 测试/验证层 ❌ (无 cross-resolution/ADB/ROI 单测)。

**杠杆点排序**: P0 click 不读 coord_system + box 无 box_coord_system; P1 ROI 下沉基类 + SUB-IMAGE 显式化; P2 BaseDevice 声明 click_coord_system + 退化日志; P3 cross-resolution 测试。

### 10.8 多维度评分法做架构选型 (7 维评分) — ⚠️ SUPERSEDED

> **superseded_by §10.10 (2026-07-27 第四轮)**: §10.8 从「架构纯度」评分 (唯一不变量/显式契约/fail fast/抽象层不泄漏), 忽略 GAF 是 AI 主导项目 — 架构纯度再高, AI 调不了也是死路。§10.10 用 8 维评分 (D1-D4 AI 可调试性权重 > D5-D8 架构纯度) 重评全部决策点并增强。历史评分明细表已删除, 结论见 §10.10 决策点总结表。

### 10.9 写完代码后架构归一化 review gate (保留 G1-G7, L0 引用)

**触发条件** (任一即触发): 任务涉及坐标系 / 设备抽象 / 跨设备契约 / ROI / 缩放 / 点击 / 识别节点输出 / 任何 "归一化" / "统一" / "下沉" / "抽象" 关键词。

**review gate 7 项检查** (写完代码后必跑, 与 §5 字段级 + §10.5 节点级叠加):

```text
□ G1. 跨设备契约矩阵: 列出所有 Device 实现 × 所有动作 (click/swipe/capture), 标注每对期望坐标系, 验证 publish 端写入坐标系与 device 期望对齐
□ G2. 抽象层不泄漏检查: publish_match_pos / resolve_target 等核心接口是否无状态、不依赖 device 类型; 节点代码是否避免 if windows/adb
□ G3. 子图坐标系显式化: 节点内部 crop 后的子图坐标是否走显式 SUB_IMAGE→full 转换, 不靠隐式 roi_offset 回加
□ G4. 唯一不变量验证: _last_match_pos.coord_system 是否在所有 publish 路径下都是同一个值 (logical), 不因 device/transformer/legacy 切换
□ G5. 退化策略检查: transformer 缺失/失败时是 fail fast 还是静默退化; 退化路径是否日志标记 legacy_mode=true
□ G6. 重复逻辑下沉: ROI 裁剪/模板缩放/坐标转换等在多节点重复的逻辑是否下沉到基类或 transformer
□ G7. 跨维度覆盖度矩阵: 12 维度归一化矩阵 (§10.7) 每维状态是否全部 ✅, ⚠️/❌ 是否有显式 known-issue 文档化
```

**三层检查清单体系** (§10.11 最终版表格见该节): §5 字段级 / §10.5 节点级 / §10.9 架构级 / §10.11 AI 可调试级。

### 10.10 第四轮: AI 可调试性优先的全坐标系归一化重评 (覆盖 §10.8 选型)

**触发**: 用户第四轮提示 "ai主导的项目，要是ai无法调试，那肯定不行啊，重新评估全坐标系的架构归一化"。

**§10.8 选型的根本缺陷**: 从架构纯度出发, 没从「AI 主导 + AI 必须能调试」出发。例如: 决策点 2 选 A (ADB 内部转) 是转换黑盒 (AI 看 `device.click(960,540)` 以为是 logical 实际点 physical, 无日志); 决策点 4 选 B (直接报错) 是 4 种根因一种报错。

**AI 调试黄金标准 (4 条, 所有方案必须满足)**: ① 每次坐标转换必记 trace (raw+converted+formula+transformer_id) ② 报错必带 4 类归因字段 (root_cause_category: config/code/data/device + missing_field + task_id + device_id) ③ 跨设备日志 schema 统一 (Windows/ADB log_node_event 字段完全一致) ④ bug 现场可重建 (日志带 device_type + coord_system + raw + converted + transformer_id, 不重跑可算点击位置)。

**新评分维度 (8 维, D1-D4 AI 可调试性权重 > D5-D8)**: D1 转换链路可观测 / D2 错误归因粒度 / D3 跨设备对比 / D4 bug 现场重建 (高权重); D5 类型安全 / D6 设备无关性 / D7 错误防护 / D8 实现成本 (中权重)。

**6 个决策点选型总结 (覆盖 §10.8)**:

| 决策点 | §10.8 | §10.10 重评选型 | 关键增强 |
|-------|------|--------------|---------|
| 1. box 坐标系 | A 统一 logical | **A 统一 logical** | publish 内部转换必记 trace |
| 2. ADB publish | A 永远 logical + device 内部转 | **A+ 永远 logical + device 内部转 + 必记 trace** | 堵黑盒 |
| 3. SUB-IMAGE | A CoordType.SUB_IMAGE | **A CoordType.SUB_IMAGE + 必记 trace** | 强化 trace |
| 4. 退化策略 | B 直接报错 | **C 直接报错 + 4 类归因字段** | 报错必归因 |
| 5. trace 日志 | (未列) | **A 统一 CoordTraceEvent schema (JSONL 一行一转换)** | 新增 |
| 6. 跨设备 schema | (未列) | **A log_node_event 强制 device_type + coord_system + transformer_id** | 新增 |

**4 条 AI 可调试性总原则 (替代 §10.8 架构层总原则)**: ① 转换必观测 ② 报错必归因 ③ 跨设备 schema 统一 ④ bug 现场可重建。§10.8 的 4 条架构纯度原则降级为次要 (前提是先满足 AI 可调试性 4 条)。

### 10.11 AI 可调试性 review gate (D1-D7, 替代 §10.9 的架构归一化 review gate)

**触发条件** (任一即触发): 任务涉及坐标转换 / 设备抽象 / 跨设备契约 / 任何 publish→resolve_target→device 动作链路 / AI 主导开发 + 需要后续 AI 调试的代码。

**AI 可调试性 review gate 7 项检查 (D1-D7)**:

```text
□ D1. 转换链路可观测: 每次坐标转换是否记 CoordTraceEvent (raw+converted+formula+transformer_id); grep "coord_transform" 能否看到完整链路
□ D2. 报错归因粒度: transformer 缺失/失败报错是否带 root_cause_category (config/code/data/device) + missing_field + task_id + device_id; 禁止「4 种根因一种报错」
□ D3. 跨设备 schema 统一: log_node_event 是否强制 device_type + coord_system + transformer_id 三字段; Windows/ADB 字段完全一致; AI 一套解析逻辑通用
□ D4. bug 现场可重建: 日志是否带 device_type + coord_system + raw + converted + transformer_id; AI 不重跑能否算出点击位置
□ D5. 转换黑盒检查: ADBDevice.click / WindowsDevice.click / publish_match_pos / resolve_target 等核心接口内部转换是否记 trace; 禁止转换黑盒
□ D6. AI 反推能力: 从一段日志能否反推出「输入坐标系→转换公式→输出坐标系」完整链路; 不需要看代码
□ D7. 跨设备对比能力: 同任务跑 Windows/ADB, 日志能否并排对比坐标语义差异; diff 命令能否直接看出差异
```

**三层检查清单体系 (最终版)**:

| 检查清单 | 层级 | 关注点 | 触发时机 |
|---------|------|-------|---------|
| §5 (原 7 项) | 字段级 | schema 字段残留 / 类型映射 / publish 调用 | schema 重构类任务 |
| §10.5 节点间数据流 | 节点级 | publish→resolve_target 字段契约 / ROI 偏移传递 | 节点链路修改 |
| §10.9 架构 review gate (G1-G7) | 架构级 | 跨设备契约 / 抽象层泄漏 / 唯一不变量 / 退化策略 | 任何归一化/抽象类任务 |
| §10.11 AI 可调试性 review gate (D1-D7) | AI 可调试级 | 转换链路可观测 / 报错归因 / 跨设备 schema / bug 现场重建 | 任何坐标/设备/动作链路修改 |

**多维度评分法使用时机**: spec 阶段识别架构决策点必用 8 维评分法 (D1-D4 AI 可调试性权重 > D5-D8), D1-D4 不可删减, 选型必写「AI 可调试性总原则」。

### 10.12 P2 完成: CoordType.SUB_IMAGE + sub_image_to_full trace (2026-07-27)

**决策点 3 落地** (D1+D4+D5 同时满足):

| 改动 | 文件 | 行为 |
|-----|------|-----|
| `CoordType.SUB_IMAGE` 入 enum | `agent/src/utils/coord_transformer.py` | 显式标注子图坐标系 |
| `_CoordTypeStub.SUB_IMAGE` | `agent/src/utils/adb_coord_transformer.py` | ADB 接口对齐 |
| `sub_image_to_full()` 方法 | 两个 coord_transformer.py | 语义化别名 = apply_roi_offset_to_subcoord, 转换显式化 |
| 4 识别节点替换 + emit_coord_trace | ocr/template_match/feature_match/color_detect.py | 替换调用 + 转换后 emit_coord_trace |

**AI 调试链路**: `grep "coord_transform" run.log | jq 'select(.node_id=="ocr_1")'` → 看到 publish_match_pos → sub_image_to_full → device_click 全链路, raw=sub_coord / converted=phys / roi_offset_phys, 判断偏移是否加对, 不重跑。

**防错机制 (mock_context fixture 漏设字段) — 强制规则**:

- 节点加 `getattr(context, '<新字段>', None)` 后, **必须**同步更新所有 mock_context fixture 显式设该字段为 None (MagicMock 默认 truthy 会误走 transformer 路径, unpack 失败)
- orchestrator 加 `hasattr(device, "<新方法>")` 后, **必须**同步更新所有 mock device fixture 设 return_value (MagicMock 默认有任意属性)
- 本次 3 文件 59 tests 预先失败 (test_engine_nodes_input 47 + test_engine_nodes_basic 11 + test_orchestrator 1), 根因全是 fixture 漏设 `coord_transformer=None` / `device.get_resolution.return_value=(1920,1080)`

**验证**: 15 个相关测试文件 → **629 passed, 0 failed**。P2 后 §10.11 D1-D7 全部 ✅。

### 10.13 继续检查: D5 全动作节点 trace 覆盖 + Windows/ADB 路径误判修复 (2026-07-27)

**触发**: 用户 "继续检查" → D1-D7 发现 D5 转换黑盒仍有遗漏。

**遗漏点 1 — 7 个动作节点漏记 trace**: swipe / long_press / direct_hit / wheel / multi_touch / multi_swipe / multi_scroll / roi_resolver 调用 device.<action> 前加 emit_coord_trace (direct_hit 用 step=`device_click` 让 AI 跨节点 grep 一次抓到所有 device.click)。

**遗漏点 2 — Windows hwnd 失效误走 ADB 路径**: WindowsDevice 也有 get_resolution。hwnd 失效时误走 ADB 路径, coord_system 错标 physical。修复: `is_windows_device = getattr(device, "hwnd", None) is not None`; Windows fail fast (CoordTransformerError, root_cause="device"), 仅非 Windows 才走 ADB 路径。

**遗漏点 3 — 3 个识别节点 result_data 漏标 coord_system**: ocr/feature_match/color_detect result_data 加 `"coord_system": getattr(context, "coord_system", "") or "legacy"`。

**关键反思 — "继续检查" 的杠杆价值**: review gate 的"全部 ✅"必须基于**逐节点扫描**不是抽样 (动作 8 + 识别 4 + 辅助 1 = 13 个, 每个 grep "device." 看主调用前是否有 emit_coord_trace)。

**验证**: 629 passed, 0 failed (17 文件)。

### 10.14 继续循环检查: OCR boxes 坐标系混合 + ADB 截图校验遗漏 (2026-07-27)

**触发**: 用户 "继续循环检查" → 换扫描维度 (OCR 内部数据流 / ADB transformer 边界 / capture 路径)。

**遗漏点 4 — OCR result_data boxes 坐标系混合**: boxes 是子图内坐标 (SUB_IMAGE), best_box 是全图 PHYSICAL, 混在同一 dict。修复: 新增 `boxes_full_image` (走 sub_image_to_full / legacy 加 roi_offset) + `boxes_sub_image` (原始) + `box_coord_system` 标注。

**遗漏点 5 — OCR/feature_match/color_detect 漏调 validate_capture_resolution**: 之前只有 template_match 校验 ADB 截图分辨率。3 节点截图后加同样校验 (非阻断, 仅 warning)。

**编辑器使用反思**: edit 工具在 try-except 链中插入代码易断开 except 链 (2 次实错)。**防错规则**: 插入点选在 `except Exception` 块结束后 (整个 try-except 之后)。

**验证**: 629 passed, 0 failed (17 文件)。

### 10.15 收尾: 文档归一化 + sub_image_to_full 双路径验证 (2026-07-27)

**触发**: 用户继续 "继续"。发现 docs/business/devices/dpi-coordinate.md 仍停留在 4 层坐标模型, 未提及 SUB_IMAGE / ADB / sub_image_to_full / CoordTraceEvent 等新概念。

**子任务**: ① `_temp_sub_image_verify.py` 5 个 smoke test 验证 Windows/ADB 双路径 + 与 apply_roi_offset_to_subcoord 等价 + PaddleOCR 4-point ② dpi-coordinate.md 归一化 (4→5 层坐标模型 + §8.3 Windows vs ADB 双路径 + §9.5 coord_system/box_coord_system + §9.6 截图分辨率校验 + §11 AI 可调试性设计) ③ architecture/overview.md (utils/ 目录树 + 5 层坐标变换) ④ troubleshooting.md §4.6 坐标系混淆排查。

**验证**: 5/5 smoke + test_orchestrator 44/44 + 识别节点组 156/156 + logger 组 77/77。

**反思**: 代码层归一化完成 ≠ 任务完成。schema 归一化硬约束 §6 (文档/资源审查) 要求 docs/business/ 文档同步归一化, 但 AI 完成代码后默认任务结束。**改进建议**: schema 重构类任务完成前在 §6 文档审查清单显式列出 dpi-coordinate.md / architecture/overview.md / troubleshooting.md 三个坐标相关文档。