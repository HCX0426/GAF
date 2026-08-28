# 双调试视角 + Schema 归一化跟进 spec

> **创建日期**: 2026-07-28
> **背景**: 2026-07-28 对 GAF 项目做 N192 双视角 + N191 架构归一化全量评估,发现 1 P0 + 7 P1 + 6 P2 共 14 个问题。按 N193 任务归属硬约束,纳入本 spec 并实现。
> **评估结果**: N191=9.0/10, N192-A=8.0/10, N192-B=7.6/10
> **目标**: 整体成熟度从 8.2 提升到 9.0+

---

## 问题清单

### P0 阻断 (1 项)

| ID | 问题 | 来源 | 修复任务 |
|----|------|------|---------|
| P0-1 | B7 无"重试单节点"功能,用户无法自行修复 | N192-B | Task 1.1 |

### P1 重要 (7 项)

| ID | 问题 | 来源 | 修复任务 |
|----|------|------|---------|
| P1-1 | 6 个节点 30+ 处 fail_result 缺 error_code | N192-A | Task 1.2 |
| P1-2 | 3 个识别节点失败路径无 result_data 诊断字段 | N192-A | Task 1.3 |
| P1-3 | pipeline-design.md §3-§6 chain schema 残留 | N191 | Task 2.1 |
| P1-4 | resource-pack-design.md §5.2 未标 deprecated | N191 | Task 2.2 |
| P1-5 | handler.py L188 兼容性注释模糊 | N191 | Task 2.3 |
| P1-6 | handleValidate 与 handleSave 校验割裂 + race condition | N192-B | Task 1.4 |
| P1-7 | 错误信息缺结构化上下文 + JSONL trace 不对用户可见 | N192-B | Task 2.4 |

### P2 次要 (6 项)

| ID | 问题 | 来源 | 修复任务 |
|----|------|------|---------|
| P2-1 | feature_match/color_detect 缺 coord_system | N192-A | Task 3.1 |
| P2-2 | pre_verify 用字符串而非 NodeErrorCode 枚举 | N192-A | Task 3.2 |
| P2-3 | templateId 留空只 warn 不 fail | N192-B | Task 3.3 |
| P2-4 | retry/fallback 内部字段不校验 | N192-B | Task 3.4 |
| P2-5 | 前端无本地 schema 校验库 | N192-B | Task 3.5 |
| P2-6 | NodeErrorCode 字符串枚举映射未使用 | N192-B | Task 3.6 |

---

## 阶段 1: P0+P1 高优先级 (Task 1.1-1.4)

### Task 1.1: B7 重试单节点功能 (P0-1)

**问题**: 用户拿到错误后无法自行修复,必须重新跑整个 pipeline。

**实现:**
- backend: 新增 `POST /tasks/task-executions/{id}/retry-from-step/` 端点
  - 接受 `step_index` 参数,从该步骤重新执行
  - 复用 PipelineEngine,加 `start_step_index` 参数跳过前面已成功的步骤
  - 返回新的 TaskExecution
- frontend: `ExecutionMonitorPanel.tsx` 在 StepProgressBar 失败节点旁加"重试此步"按钮
  - 点击后调用 retry-from-step 端点
  - 显示确认 Modal: "将从第 N 步重新执行,之前成功步骤的结果会保留"

**文件:**
- 新增/修改: `backend/tasks/views.py` (retry-from-step action)
- 新增/修改: `agent/src/core/orchestrator.py` (execute_pipeline 支持 start_step_index)
- 新增/修改: `agent/src/engine/engine.py` (execute 支持 start_step_index)
- 修改: `frontend/src/pages/Ops/Executions/ExecutionMonitorPanel.tsx`
- 修改: `frontend/src/api/tasks.ts` (retryFromStep 函数)
- 测试: `backend/tasks/tests/test_retry_from_step.py` + `agent/tests/test_pipeline_engine.py`

---

### Task 1.2: 节点 fail_result 补 error_code (P1-1)

**问题**: ocr/feature_match/color_detect/click/branch/app_control 6 个节点 30+ 处 fail_result 缺 error_code,全部归一为 UNKNOWN,AI 无法分类诊断。

**实现:**
为每个节点的 fail_result 调用按失败语义补 `error_code=NodeErrorCode.X`:

| 节点 | 失败场景 | error_code |
|------|---------|-----------|
| ocr.py L91 | 无图像 | DEVICE_ERROR |
| ocr.py L151 | OCR 空结果 | OCR_EMPTY |
| ocr.py L325 | expected_text 不匹配 | OCR_EMPTY |
| ocr.py L341 | OCR 异常 | UNKNOWN (显式) |
| feature_match.py L271 | 不支持的方法 | PARAM_INVALID |
| feature_match.py L280/L290/L296/L299 | device/screenshot 失败 | DEVICE_DISCONNECTED/DEVICE_ERROR |
| feature_match.py L344 | 模板加载失败 | PARAM_INVALID |
| feature_match.py L358/L375/L405 | 特征点/匹配点不足 | NO_MATCH/LOW_CONFIDENCE |
| feature_match.py L571/L574 | OpenCV/处理异常 | UNKNOWN (显式) |
| color_detect.py L159/L168/L174/L177 | device/screenshot 失败 | DEVICE_DISCONNECTED/DEVICE_ERROR |
| color_detect.py L234/L237/L406/L409 | OpenCV/处理异常 | UNKNOWN (显式) |
| color_detect.py L266 | 无轮廓 | COLOR_NOT_FOUND |
| click.py L121 | device=None | DEVICE_DISCONNECTED |
| click.py L145 | 坐标解析失败 | COORD_INVALID |
| click.py L156 | clicks < 1 | PARAM_INVALID |
| click.py L195/L201 | 点击失败 | DEVICE_ERROR |
| branch.py L52 | 变量名为空 | PARAM_INVALID |
| app_control.py L62/L75/L94/L108 | device/package/command/timeout | DEVICE_DISCONNECTED/PARAM_INVALID/TIMEOUT |

**实现策略**: 复用 template_match.py 的 `_build_fail_diagnostics` 模式,为每个节点建 fail-diagnostics helper。

**文件:**
- 修改: `agent/src/engine/nodes/ocr.py`
- 修改: `agent/src/engine/nodes/feature_match.py`
- 修改: `agent/src/engine/nodes/color_detect.py`
- 修改: `agent/src/engine/nodes/click.py`
- 修改: `agent/src/engine/nodes/branch.py`
- 修改: `agent/src/engine/nodes/app_control.py`
- 测试: `agent/tests/test_pipeline_engine.py` (新增 error_code 断言)

---

### Task 1.3: 节点失败路径补 result_data 诊断字段 (P1-2)

**问题**: ocr/feature_match/color_detect 设备/截图/异常失败路径无 result_data 诊断字段,AI 无法从 result_data 拿失败上下文。

**实现:**
为失败路径补 result_data,至少含:
- `coord_system`: `getattr(context, "coord_system", "") or "legacy"`
- 节点配置关键字段: ocr 的 `region/expected_text/engine`, feature_match 的 `method/min_matches/ratio_threshold`, color_detect 的 `lower/upper/min_area`
- 失败时的中间值: feature_match 的 `num_matches`, color_detect 的 `mask_nonzero_pixels`

**实现策略**: 在每个节点 execute() 顶部预先构造 config_snapshot,失败时附加到 fail_result(data=...)。

**文件:**
- 修改: `agent/src/engine/nodes/ocr.py`
- 修改: `agent/src/engine/nodes/feature_match.py`
- 修改: `agent/src/engine/nodes/color_detect.py`
- 测试: `agent/tests/test_pipeline_engine.py`

---

### Task 1.4: validate-payload 端点 + 统一校验口径 (P1-6)

**问题**: handleValidate 纯前端校验,handleSave 是 createTask 后 validate,两个口径不一致 + race condition。

**实现:**
- backend: 新增 `POST /tasks/validate-payload/` 端点
  - 接受 inline task_definition,不写库
  - 返回 CheckItem 列表
- frontend: `handleValidate` 和 `handleSave` 前都调用 validate-payload
  - handleValidate: 调用 validate-payload,展示错误
  - handleSave: 先 validate-payload,通过后再 createTask (避免 delete race condition)

**文件:**
- 修改: `backend/tasks/views.py` (validate-payload action)
- 修改: `backend/tasks/urls.py` (路由)
- 修改: `frontend/src/api/tasks.ts` (validatePayload 函数)
- 修改: `frontend/src/pages/Tasks/Editor.tsx` (handleValidate + handleSave)
- 测试: `backend/tasks/tests/test_validate_payload.py`

---

## 阶段 2: P1 文档+上下文 (Task 2.1-2.4)

### Task 2.1: pipeline-design.md chain schema 残留修复 (P1-3)

**问题**: §3.1/§3.2/§5/§6.1 共 4 处 chain schema 残留。

**实现:**
- §3.1 JSON Schema 示例: `"required": ["name", "execution_mode", "steps"]` → 替换为 pipeline schema (`nodes` + `node_type`)
- §3.2 校验器代码: `validate_chain_task()` + `task_def.get("steps", [])` → 替换为 pipeline 校验器
- §5 JSON 示例: `"steps": [{"name": "select_stage", "action": "find_and_click"}]` → 替换为 pipeline 示例
- §6.1 表格: "执行模式: chain / state_machine" → "执行模式: pipeline / state_machine"

**文件:**
- 修改: `docs/business/tasks/pipeline-design.md`

---

### Task 2.2: resource-pack-design.md §5.2 deprecated 标注 (P1-4)

**问题**: §5.2 "链式任务(JSON)" 未标 deprecated。

**实现:**
- §5.2 整段替换为 pipeline schema 示例 (用 `nodes` + `node_type`)
- 或在 §5.2 开头加 `> ⚠️ chain schema 已废弃,新资源包应使用 §7 的 pipeline schema` 提示框

**文件:**
- 修改: `docs/business/resources/resource-pack-design.md`

---

### Task 2.3: handler.py 注释清晰化 (P1-5)

**问题**: L188 兼容性注释模糊,"老 server 仍可能发 chain" 不明确。

**实现:**
```python
# N191 §4.3: execution_mode 字段值已归一化为 'pipeline' / 'state_machine'.
# 兼容历史: migration 0049 之前的 backend 可能发 'chain',agent 当作 'pipeline' 处理.
# TODO(N191-cleanup): 当 backend ≥ 0049 普及后,移除 'chain' 兼容分支.
```

**文件:**
- 修改: `agent/src/client/handler.py`

---

### Task 2.4: 节点详情抽屉 (P1-7)

**问题**: 错误信息缺结构化上下文,JSONL trace 不对用户可见。

**实现:**
- frontend: `ExecutionMonitorPanel.tsx` 加"节点详情抽屉"
  - 点击失败节点除了显示截图,还展示该节点的 config (JSON 视图) + 前驱 result_data 摘要
  - 数据来源: 新增 backend 端点 `GET /tasks/task-executions/{id}/node-trace/{step_index}/` 读取 JSONL
- backend: 新增 node-trace 端点
  - 读取 agent 的 JSONL trace 文件
  - 按 step_index 索引返回 input_config + result_data 摘要

**文件:**
- 新增: `backend/tasks/views.py` (node-trace action)
- 修改: `frontend/src/pages/Ops/Executions/ExecutionMonitorPanel.tsx`
- 新增: `frontend/src/components/Pipeline/NodeDetailDrawer.tsx`
- 修改: `frontend/src/api/tasks.ts`

---

## 阶段 3: P2 细节优化 (Task 3.1-3.6)

### Task 3.1: feature_match/color_detect 补 coord_system (P2-1)

**文件:** `agent/src/engine/nodes/feature_match.py` + `color_detect.py`

---

### Task 3.2: pre_verify error_code 改用 NodeErrorCode 枚举 (P2-2)

**文件:** `agent/src/engine/engine.py` + `agent/src/core/error_codes.py` (新增 PRE_VERIFY_FAILED)

---

### Task 3.3: templateId 留空升级为 fail (P2-3)

**文件:** `backend/pipeline/validators.py` + `resources/*/custom_tasks/template.json`

---

### Task 3.4: retry/fallback 内部字段校验 (P2-4)

**文件:** `backend/pipeline/schema.py`

---

### Task 3.5: 前端引入 ajv 本地 schema 校验 (P2-5)

**文件:** `frontend/package.json` + `frontend/src/utils/schemaValidator.ts` + `frontend/src/pages/Tasks/Editor.tsx`

---

### Task 3.6: NodeErrorCode 字符串枚举映射实际启用 (P2-6)

**文件:** `backend/tasks/signals.py` + `frontend/src/components/Pipeline/StepProgressBar.tsx`

---

## 阶段 4: 第二轮评估发现的新问题 (Task 4.1-4.11)

> **背景**: 2026-07-28 第二轮 N192 + N191 全量评估发现 4 P0 + 4 P1 + 5 P2 共 13 个新问题。
> 按 N193 任务归属硬约束, 纳入本 spec 并实现。
> **第二轮评分**: N192-A=7.9, N192-B=7.0, N191=8.5 (目标 9.0+/9.0+/9.5+)

### P0 阻断 (4 项, 阶段 4 新增)

| ID | 问题 | 来源 | 修复任务 |
|----|------|------|---------|
| P0-2 | 14 个动作类节点 ~63 处 fail_result 缺 error_code/node_id/node_type + result_data 缺 coord_system | N192-A1/A2 | Task 4.1 |
| P0-3 | templateId 字段名三方不一致 (template.json=templateId / Editor=template_id / agent=template / validator=templateId or template) | N192-B4 | Task 4.2 |

### P1 重要 (4 项, 阶段 4 新增)

| ID | 问题 | 来源 | 修复任务 |
|----|------|------|---------|
| P1-8 | templateId 占位符非空字符串导致 validator 误判 pass | N192-B4 | Task 4.3 |
| P1-9 | retry/fallback 事件 step_index 恒为 0 (engine 用局部变量 iteration 而非实例属性) | N192-A5 | Task 4.4 |
| P1-10 | TaskStepSerializer 缺 error_code 字段, 历史回看场景 error_code 丢失 | N192-B2 | Task 4.5 |
| P1-11 | pipeline-design.md §6.1 残留 "ChainManager 步骤" 引用未清理 | N191 | Task 4.6 |

### P2 次要 (5 项, 阶段 4 新增)

| ID | 问题 | 来源 | 修复任务 |
|----|------|------|---------|
| P2-7 | template.json 占位符示例 tpl_login_btn 与实际中文资源命名约定不一致 | N192-B4 | Task 4.7 |
| P2-8 | test_agent_selector.py / test_pipeline_engine.py 含旧 schema 用例未标注 backward-compat 性质 | N191 | Task 4.8 |
| P2-9 | validate 端点无 strict mode 拒绝旧 chain schema | N191 | Task 4.9 |
| P2-10 | post_verify 失败未写独立 JSONL 事件, 与 pre_verify 不对称 | N192-A7 | Task 4.10 |
| P2-11 | _truncate_result_data_priority 的 P0 字段集缺 num_matches/inlier_matches/matched | N192-A6 | Task 4.11 |

### Task 4.1: 14 个动作类节点 fail_result 补三要素 + result_data 补 coord_system (P0-2)

**问题**: long_press/swipe/key_press/text_input/wheel/multi_swipe/multi_touch/multi_scroll/wait/monitor/device_control/goto/direct_hit/nn_recognition 共 14 个节点 ~63 处 fail_result 缺 error_code/node_id/node_type; success result_data 缺 coord_system; fail 路径无诊断 data。

**实现策略**: 复用 template_match.py 的 `_build_fail_diagnostics(self, context, error_code, **kwargs)` 模式, 为每个节点建 helper, 机械补全三要素 + coord_system + 关键 config 字段。

**文件:**
- 修改: `agent/src/engine/nodes/long_press.py`
- 修改: `agent/src/engine/nodes/swipe.py`
- 修改: `agent/src/engine/nodes/key_press.py`
- 修改: `agent/src/engine/nodes/text_input.py`
- 修改: `agent/src/engine/nodes/wheel.py`
- 修改: `agent/src/engine/nodes/multi_swipe.py`
- 修改: `agent/src/engine/nodes/multi_touch.py`
- 修改: `agent/src/engine/nodes/multi_scroll.py`
- 修改: `agent/src/engine/nodes/wait.py`
- 修改: `agent/src/engine/nodes/monitor.py`
- 修改: `agent/src/engine/nodes/device_control.py`
- 修改: `agent/src/engine/nodes/goto.py`
- 修改: `agent/src/engine/nodes/direct_hit.py`
- 修改: `agent/src/engine/nodes/nn_recognition.py`
- 测试: `agent/tests/test_node_fail_diagnostics.py` (扩展)

### Task 4.2: templateId 字段名三方归一化 (P0-3)

**问题**: template.json 用 `templateId` (camelCase), Editor.tsx 保存用 `template_id` (snake_case), agent parser 读 `template` (无 Id 后缀), validator 兼容 `templateId`/`template` 但不接受 `template_id` — 三方不一致导致用户照着模板改无法跑通。

**实现策略**: 归一化为 `template_id` (snake_case, 与 Python/dataclass 习惯一致)。修改:
- template.json: `templateId` → `template_id`
- agent parser/node: `template` → `template_id` (兼容旧 `template` 字段)
- validator: `templateId`/`template` → `template_id` (兼容旧字段)
- Editor.tsx: 已是 `template_id`, 保持不变

**文件:**
- 修改: `resources/default/custom_tasks/template.json`
- 修改: `resources/BrownDust-II/custom_tasks/template.json`
- 修改: `agent/src/engine/nodes/template_match.py`
- 修改: `backend/pipeline/validators.py`
- 修改: `backend/pipeline/schema.py`
- 测试: `backend/pipeline/tests/test_validators.py`

### Task 4.3: templateId 占位符改 null/空串让 validator 拦截 (P1-8)

**问题**: 当前 `templateId` 占位符是字符串 `"<必填: 资源包中的模板 ID,如 tpl_login_btn>"`, 非空导致 validator `if template_id or template:` 判 pass, 用户忘替换占位符时 validator 通过但 agent 执行失败。

**实现策略**: 占位符改为 `null`, 让 validator 的 `if not template_id:` 拦截。同时占位符示例改为实际资源路径 `BrownDust-II/templates/login/开始游戏.png`。

**文件:**
- 修改: `resources/default/custom_tasks/template.json`
- 修改: `resources/BrownDust-II/custom_tasks/template.json`
- 修改: `backend/pipeline/validators.py` (校验逻辑不变, null 会被 `if not template_id:` 拦截)

### Task 4.4: retry/fallback 事件 step_index 修复 (P1-9)

**问题**: `engine.py` L1333/L1568 `step_index=getattr(self, "_current_step_index", 0)` — `_current_step_index` 不是 engine 实例属性 (engine 用 `iteration` 局部变量), retry/fallback 事件 step_index 恒为 0。

**实现策略**: 把 `iteration` 改为 `self._current_step_index` 实例属性, 或在 retry/fallback helper 中传入 iteration 参数。

**文件:**
- 修改: `agent/src/engine/engine.py`

### Task 4.5: TaskStepSerializer 补 error_code 字段 (P1-10)

**问题**: `backend/tasks/serializers.py` L40-44 `TaskStepSerializer.fields` 不含 `error_code`, REST /steps/ 端点不返回 error_code, 用户刷新页面查看历史执行时 error_code 丢失。

**实现策略**: 在 `TaskStepSerializer.fields` 加 `'error_code'` 字段 (需确认 TaskStep 模型有 error_code 字段, 若无则改用 ExecutionStep 序列化器或新增字段)。

**文件:**
- 修改: `backend/tasks/serializers.py`
- 修改: `backend/tasks/models.py` (若 TaskStep 缺字段则新增)
- 测试: `backend/tasks/tests/test_tasks.py`

### Task 4.6: pipeline-design.md §6.1 残留清理 (P1-11)

**问题**: `docs/business/tasks/pipeline-design.md` §6.1 表格仍含 "ChainManager 步骤" 引用, 文档已 deprecated 但残留未清理。

**实现策略**: 在 §6.1 表格行加 `[DEPRECATED]` 标记或删除该行, 引用 execution-reality.md 替代。

**文件:**
- 修改: `docs/business/tasks/pipeline-design.md`

### Task 4.7: template.json 占位符示例改实际资源路径 (P2-7)

**问题**: 当前示例 `tpl_login_btn` 是英文 ID 风格, 但实际资源目录用中文命名 (如 `login/开始游戏.png`), 用户照着改会困惑。

**实现策略**: 占位符示例改为 `BrownDust-II/templates/login/开始游戏.png` (实际存在的资源路径)。

**文件:**
- 修改: `resources/default/custom_tasks/template.json`
- 修改: `resources/BrownDust-II/custom_tasks/template.json`

### Task 4.8: 测试文件标注 backward-compat 性质 (P2-8)

**问题**: `test_agent_selector.py` / `test_pipeline_engine.py` 含旧 schema 用例 (验证 backward-compat), 但未在测试文件顶部加注释明确标注, 可能误导后续维护者。

**实现策略**: 在测试文件顶部加注释: "包含旧 schema 用例是为验证 backward-compat, 不是生产数据格式"。

**文件:**
- 修改: `backend/tasks/tests/test_agent_selector.py`
- 修改: `agent/tests/test_pipeline_engine.py`

### Task 4.9: validate 端点加 strict mode 参数 (P2-9)

**问题**: validate 端点 + parser 接受旧 chain schema 并静默归一化, 无选项让用户主动验证 schema 完全归一化。

**实现策略**: validate-payload 端点加 `?strict=true` 参数, strict 模式下若 task_definition 仍用 `steps` (而非 `nodes`) 或 `action`/`type` (而非 `node_type`) 则返回 warning。

**文件:**
- 修改: `backend/tasks/views.py`
- 修改: `backend/pipeline/validators.py`

### Task 4.10: post_verify 失败写独立 JSONL 事件 (P2-10)

**问题**: `engine.py` L1260-1285 `post_verify` 失败路径仅修改 result 字段, 未调 `_log_node_verify_event` 写 JSONL 事件, 与 pre_verify 不对称。

**实现策略**: 在 post_verify 失败路径补 `_log_node_verify_event(node, "node.execute.post_verify_failed", result)` 调用。

**文件:**
- 修改: `agent/src/engine/engine.py`

### Task 4.11: _truncate_result_data_priority P0 字段集扩展 (P2-11)

**问题**: `engine.py` L77-80 `_RESULT_DATA_P0_FIELDS` 缺 `num_matches / inlier_matches / matched`, 这些是 feature_match 关键诊断字段, 会落到 P3 被截断到 500 字符。

**实现策略**: 在 `_RESULT_DATA_P0_FIELDS` 加这三个字段。

**文件:**
- 修改: `agent/src/engine/engine.py`

---

## 阶段 5: 第三轮评估发现的新问题 (Task 4.12-4.23)

> **背景**: 2026-07-28 第三轮 N192 + N191 全量评估发现 5 P1 + 7 P2 共 12 个新问题。
> 按 N193 任务归属硬约束, 纳入本 spec 并实现。
> **第三轮评分**: N192-A=6.3, N192-B=6.8, N191=8.5 (目标 9.0+/9.0+/9.5+)

### P1 重要 (5 项, 阶段 5 新增)

| ID | 问题 | 来源 | 修复任务 |
|----|------|------|---------|
| P1-12 | 8 个节点 (app_control/swipe_until/sub_pipeline/python_call/loop/sort_select/notify/composite_match/maa_actions) 缺 _build_fail_diagnostics + 三要素 + coord_system | N192-A1/A2 | Task 4.12 |
| P1-13 | PRE_VERIFY_FAILED 错误码 i18n 映射缺失 (4 个 locale 段) | N192-B2 | Task 4.14 |
| P1-14 | NodePropertyPanel 8 类节点字段名与后端 validator 不匹配 (color_detect/feature_match/loop/random_delay/notify/monitor/sub_pipeline/goto) | N192-B3/B5 + N191 | Task 4.15 |
| P1-15 | sub_pipeline 节点 parameters JSON 解析错误静默吞掉 | N192-B5 | Task 4.16 |
| P1-16 | 历史执行步骤表格缺少 error_message 列 | N192-B6 | Task 4.17 |

### P2 次要 (7 项, 阶段 5 新增)

| ID | 问题 | 来源 | 修复任务 |
|----|------|------|---------|
| P2-12 | engine.py post_verify error_code 用裸字符串而非 NodeErrorCode 枚举 | N192-A1 | Task 4.13 |
| P2-13 | monitor/sub_pipeline 节点 options 硬编码空数组 | N192-B3 | Task 4.18 |
| P2-14 | NodePropertyPanel 表单无 schema 校验实时反馈 | N192-B3/B5 | Task 4.19 |
| P2-15 | expandedRowRender Steps 不展示 error_message | N192-B6 | Task 4.20 |
| P2-16 | NodeDetailDrawer fallback 文案为英文 'unknown error' | N192-B1/B7 | Task 4.21 |
| P2-17 | ExecutionMonitorPanel 5 个干预操作用通用 msg_action_failed | N192-B1/B6 | Task 4.22 |
| P2-18 | .ai-memory/meta/failure-modes.md 缺 N193 索引行 | N191 | Task 4.23 |

### Task 4.12: 8 个节点补 _build_fail_diagnostics + 三要素 + coord_system (P1-12)

**问题**: app_control/swipe_until/sub_pipeline/python_call/loop/sort_select/notify/composite_match/maa_actions 共 8 个节点 ~30+ 处 fail_result 缺 error_code/node_id/node_type, 缺 _build_fail_diagnostics, result_data 缺 coord_system。

**实现策略**: 复用 device_control.py 的 `_build_fail_diagnostics(self, context, error_code, **kwargs)` 模式, 为每个节点建 helper, 机械补全三要素 + coord_system + 关键 config 字段。

**文件:**
- 修改: `agent/src/engine/nodes/app_control.py`
- 修改: `agent/src/engine/nodes/swipe_until.py`
- 修改: `agent/src/engine/nodes/sub_pipeline.py`
- 修改: `agent/src/engine/nodes/python_call.py`
- 修改: `agent/src/engine/nodes/loop.py`
- 修改: `agent/src/engine/nodes/sort_select.py`
- 修改: `agent/src/engine/nodes/notify.py`
- 修改: `agent/src/engine/nodes/composite_match.py`
- 修改: `agent/src/engine/nodes/maa_actions.py`
- 测试: `agent/tests/test_node_fail_diagnostics.py` (扩展)

### Task 4.13: engine.py post_verify error_code 改用 NodeErrorCode 枚举 (P2-12)

**问题**: engine.py L1270/L1281 `result.error_code = "POST_VERIFY_FAILED"` 用裸字符串, 与 pre_verify 用 `NodeErrorCode.PRE_VERIFY_FAILED` 枚举不一致。

**文件:**
- 修改: `agent/src/engine/engine.py`

### Task 4.14: PRE_VERIFY_FAILED i18n 映射补全 (P1-13)

**问题**: `frontend/src/i18n/locales/common.ts` 4 个 locale 段 (zh-CN/en-US/ja-JP/ko-KR) 均无 `error.codes.PRE_VERIFY_FAILED` 条目, 前端 StepProgressBar 按 `error.codes.${error_code}` 查 i18n 时降级展示原始字符串。

**文件:**
- 修改: `frontend/src/i18n/locales/common.ts`

### Task 4.15: NodePropertyPanel 8 类节点字段名归一化 (P1-14)

**问题**: NodePropertyPanel 实际写入字段名与后端 PipelineValidator 必填字段不匹配:

| 节点 | 后端必填 | 前端实际写入 |
|------|---------|------------|
| color_detect | hueMin, hueMax | target_color, tolerance |
| feature_match | algorithm | template_id, min_match_count, ratio_threshold |
| loop | maxIterations | count |
| random_delay | minDelay, maxDelay | min_ms, max_ms |
| notify | channels (复数) | channel (单数) |
| monitor | ruleId | rule_id |
| sub_pipeline | pipelineId | pipeline_id |
| goto | targetLabel | target |

用户填完字段 → 保存 → validate-payload 报"缺少必填字段: hueMin, hueMax"等错误 → 用户困惑。

**实现策略**: 统一 NodePropertyPanel 字段名为后端 `node_required` dict 的字段名 (camelCase, 与 `nodes/*.tsx` Config 组件一致)。同时 i18n keys 同步归一化。

**文件:**
- 修改: `frontend/src/components/Pipeline/NodePropertyPanel.tsx`
- 修改: `frontend/src/i18n/locales/tasks.ts` (32 处 i18n key 归一化)
- 修改: `frontend/src/pages/Tasks/Editor.tsx` (表单字段名 action_type/retry_interval/fallback_action/next_step 归一化)
- 测试: `frontend/src/test/Editor.validate.test.tsx` (扩展)

### Task 4.16: sub_pipeline JSON 解析错误提示 (P1-15)

**问题**: `NodePropertyPanel.tsx:606-619` 的 sub_pipeline parameters JSON 解析 catch 块空实现, 用户输入无效 JSON 时无任何反馈。

**实现策略**: catch 块内 `setJsonError(e.message)` + 在 Form.Item 下方展示 `<Alert type="error" message={...} />`。

**文件:**
- 修改: `frontend/src/components/Pipeline/NodePropertyPanel.tsx`

### Task 4.17: 历史执行步骤表格加 error_message 列 (P1-16)

**问题**: `frontend/src/pages/Ops/Executions/index.tsx:314-338` stepColumns 缺 error_message 列, expandedRowRender 内 antd Steps 也不展示 error_message, 失败步骤只显示 status=failed Tag。

**实现策略**: stepColumns 加 error_message 列 (仅 failed 状态显示); expandedRowRender Steps 的 description 加 error_message。

**文件:**
- 修改: `frontend/src/pages/Ops/Executions/index.tsx`

### Task 4.18: monitor/sub_pipeline 节点 options 拉取 (P2-13)

**问题**: NodePropertyPanel.tsx:576/602 的 monitor rule_id options 和 sub_pipeline pipeline_id options 硬编码空数组, 用户无法在 UI 选择。

**实现策略**: 调用后端 API 拉取 monitor rules 和 pipelines 列表填充 options。

**文件:**
- 修改: `frontend/src/components/Pipeline/NodePropertyPanel.tsx`
- 修改: `frontend/src/api/tasks.ts` (新增 fetchMonitorRules / fetchPipelines 函数, 若不存在)

### Task 4.19: NodePropertyPanel 表单 schema 校验实时反馈 (P2-14)

**问题**: NodePropertyPanel 所有 Form.Item 均无 validateStatus / help 属性, 仅 required 标记。schemaValidator.ts 只在 Editor.tsx handleValidate 点击时调用, 不在属性面板层联动。

**实现策略**: 在 NodePropertyPanel 内集成 schemaValidator, 字段值变化时实时校验, Form.Item 加 validateStatus + help。

**文件:**
- 修改: `frontend/src/components/Pipeline/NodePropertyPanel.tsx`

### Task 4.20: expandedRowRender Steps 展示 error_message (P2-15)

**问题**: `frontend/src/pages/Ops/Executions/index.tsx:517-525` expandedRowRender 内 antd Steps 的 description 不含 error_message, 失败步骤鼠标悬停只看到 description 不看到失败原因。

**实现策略**: Steps 的 description 加 `${formatDuration} | ${error_message}` (仅 failed 状态)。

**文件:**
- 修改: `frontend/src/pages/Ops/Executions/index.tsx`

### Task 4.21: NodeDetailDrawer fallback 文案 i18n (P2-16)

**问题**: `NodeDetailDrawer.tsx:178-186` 拉取失败时 fallback 文案为英文 'unknown error', 未走 i18n。

**实现策略**: fallback 改为 `t('error.unknown')`。

**文件:**
- 修改: `frontend/src/components/Pipeline/NodeDetailDrawer.tsx`

### Task 4.22: ExecutionMonitorPanel 干预操作用 resolveErrorMessage (P2-17)

**问题**: ExecutionMonitorPanel.tsx:420-424 5 个干预操作 (pause/resume/skip/forceFail/cancel) catch 块用通用 `msg_action_failed`, 不区分具体操作失败原因。

**实现策略**: catch 块改为 `antMessage.error(resolveErrorMessage(error))`, 与 handleRetryConfirm 一致。

**文件:**
- 修改: `frontend/src/pages/Ops/Executions/ExecutionMonitorPanel.tsx`

### Task 4.23: .ai-memory/meta/failure-modes.md 补 N193 索引行 (P2-18)

**问题**: env-hardrules.md 标注 N193 索引行"待补", 但 .ai-memory/meta/failure-modes.md 当前无 N193 行, AI 按需加载时找不到 N193 lesson。

**文件:**
- 修改: `.ai-memory/meta/failure-modes.md`

---

## 阶段 6: 第四轮评估发现的新问题 (Task 4.24-4.35)

> **背景**: 2026-07-28 第四轮 N192 + N191 全量评估发现 4 P0 + 6 P1 + 3 P2 共 13 个新问题。
> 按 N193 任务归属硬约束, 纳入本 spec 并实现。
> **第四轮评分**: N192-A=7.5, N192-B=6.7, N191=7.5 (目标 9.0+/9.0+/9.5+)
>
> **关键发现**: 第三轮标记完成的 Task 4.9 (validate strict mode) / Task 4.14 (PRE_VERIFY_FAILED i18n) / Task 4.15 (字段名归一化) / Task 4.16 (jsonError state) / Task 4.18 (options 拉取) / Task 4.19 (实时 schema 校验) **实际未完成或仅部分完成**, 本阶段必须真正落地。

### P0 阻断 (4 项, 阶段 6 新增)

| ID | 问题 | 来源 | 修复任务 |
|----|------|------|---------|
| P0-4 | error.codes.PRE_VERIFY_FAILED 在 zh-CN/en-US/ja-JP 三个语言段缺失 (Task 4.14 仅补 ko-KR) | N192-B2 | Task 4.24 |
| P0-5 | NodePropertyPanel sub_pipeline JSON 解析 setJsonError 调用但 state 未声明, 运行时崩溃 (Task 4.16 代码缺失) | N192-B5 | Task 4.25 |
| P0-6 | validate-payload 端点未实现 strict mode (Task 4.9 标记完成但实际未做) | N191 | Task 4.26 |
| P0-7 | NodePropertyPanel 8 节点字段名与后端 validator 必填字段名不一致 (Task 4.15 未完成) | N192-B3 + N191 | Task 4.27 |

### P1 重要 (6 项, 阶段 6 新增)

| ID | 问题 | 来源 | 修复任务 |
|----|------|------|---------|
| P1-17 | 7 个节点 (branch/click/template_match_any/random_delay/roi_resolver/neural_network/_child_runner) 遗漏 _build_fail_diagnostics | N192-A1 | Task 4.28 |
| P1-18 | executions.col_error_message i18n key 仅在 en-US 定义, 其他 3 locale 缺失 | N192-B1 | Task 4.29 |
| P1-19 | monitor/sub_pipeline options 仍为空数组 (Task 4.18 未实现) | N192-B3 | Task 4.30 |
| P1-20 | convertStepsToStepInfo 不读 ts.error_code, 历史 REST 加载不展示 error_code Tag | N192-B6 | Task 4.31 |
| P1-21 | NodePropertyPanel 缺实时 schema 校验 (Task 4.19 未实现) | N192-B5 | Task 4.32 |
| P1-22 | click.py success path result_data 缺 coord_system (高频节点影响跨设备对比) | N192-A2 | Task 4.33 |

### P2 次要 (3 项, 阶段 6 新增)

| ID | 问题 | 来源 | 修复任务 |
|----|------|------|---------|
| P2-19 | 8 个 Pipeline/nodes/*Config.tsx 死代码文件 + resource-pack-design.md header 缺 status:deprecated | N191 | Task 4.34 |
| P2-20 | expandedRowRender Alert 用 title 而非 message 属性, 标题不渲染 | N192-B6 | Task 4.35 |
| P2-21 | NodePropertyPanel 完全未 i18n (40+ 硬编码中文 label) | N192-B1 | 已知限制 |

### Task 4.24: PRE_VERIFY_FAILED i18n 补全 4 locale (P0-4)

**问题**: `frontend/src/i18n/locales/common.ts` 中 `error.codes.PRE_VERIFY_FAILED` 仅在 ko-KR 段存在, zh-CN/en-US/ja-JP 三段缺失, 导致这三语言下 StepProgressBar 降级展示原始字符串 `PRE_VERIFY_FAILED`。

**文件:**
- 修改: `frontend/src/i18n/locales/common.ts` (zh-CN/en-US/ja-JP 三段补 `error.codes.PRE_VERIFY_FAILED`)

### Task 4.25: NodePropertyPanel jsonError state 声明 (P0-5)

**问题**: `NodePropertyPanel.tsx:609/610/620/623` 引用 `jsonError`/`setJsonError`, 但 state 声明段 (line 41-42) 未声明, 用户输入非法 JSON 时抛 `ReferenceError: setJsonError is not defined`, 组件崩溃。

**文件:**
- 修改: `frontend/src/components/Pipeline/NodePropertyPanel.tsx` (line 42 后加 `const [jsonError, setJsonError] = useState<string>('');`)

### Task 4.26: validate-payload 端点加 strict mode (P0-6)

**问题**: `backend/tasks/views.py:298-397` 的 `validate_payload` 端点无 `?strict=true` 查询参数, 宽松模式接受新旧字段共存, 可能掩盖 schema 漂移。

**实现:**
- `validate_payload` action 加 `strict = request.query_params.get("strict", "false").lower() == "true"`
- strict=true 时, 扫描 nodes[].config 中是否有 `templateId`/`action`/`type`/`next_step`/`retry_interval`/`fallback_action` 等旧字段, 有则返回 fail CheckItem (suggestion 提示归一化)
- `PipelineValidator.validate()` 加 `strict=False` 参数, strict 模式下追加 `_check_legacy_fields` 检查
- 前端 `handleSave` 可选调 `?strict=true` 模式 (默认宽松, 避免破坏存量)

**文件:**
- 修改: `backend/tasks/views.py`
- 修改: `backend/pipeline/validators.py` (新增 `_check_legacy_fields` 方法)
- 测试: `backend/tasks/tests/test_validate_payload.py` (新增 strict mode 用例)

### Task 4.27: NodePropertyPanel 8 节点字段名归一化 (P0-7)

**问题**: NodePropertyPanel 内嵌 case 的字段名 (snake_case) 与后端 validator 期望字段名 (camelCase) 不一致, 用户填完字段保存时后端报"缺少必填字段: hueMin/hueMax"等错误, 但前端 label 是"目标颜色/容差", 用户找不到对应字段。

**归一化策略 (推荐方案 — 后端改 snake_case)**:
- 后端 `validators.py` 的 `node_required` dict 改为 snake_case, 与前端 NodePropertyPanel 和 Python dataclass 习惯一致
- 兼容历史: 同一字段名多个变体时, validator 兼容读取 (如 `hueMin or hue_min or target_color`)

**字段映射表:**

| 节点 | 当前后端必填 (camelCase) | 当前前端写入 (snake_case) | 归一化为 |
|------|------------------------|-------------------------|---------|
| color_detect | hueMin, hueMax | target_color, tolerance | `target_color`, `tolerance` (前端已有) |
| feature_match | algorithm | template_id, min_match_count | `template_id`, `min_match_count` |
| loop | maxIterations | count | `count` |
| random_delay | minDelay, maxDelay | min_ms, max_ms | `min_ms`, `max_ms` |
| notify | channels | channel | `channel` |
| monitor | ruleId | rule_id | `rule_id` |
| sub_pipeline | pipelineId | pipeline_id | `pipeline_id` |
| goto | targetLabel | target | `target` |

**文件:**
- 修改: `backend/pipeline/validators.py` (`node_required` dict + `_check_required_fields` 兼容逻辑)
- 测试: `backend/pipeline/tests/test_validators.py`

### Task 4.28: 7 节点补 _build_fail_diagnostics (P1-17)

**问题**: branch/click/template_match_any/random_delay/roi_resolver/neural_network/_child_runner 共 7 个节点 ~18 处 fail_result 缺诊断 data, AI 跑 pipeline 报错时无法从 JSONL 看到失败上下文。

**实现策略**: 按其他 27 节点的 `_build_fail_diagnostics(self, context, error_code, **kwargs)` 模式机械补全。

**文件:**
- 修改: `agent/src/engine/nodes/branch.py`
- 修改: `agent/src/engine/nodes/click.py`
- 修改: `agent/src/engine/nodes/template_match_any.py`
- 修改: `agent/src/engine/nodes/random_delay.py`
- 修改: `agent/src/engine/nodes/roi_resolver.py`
- 修改: `agent/src/engine/nodes/neural_network.py`
- 修改: `agent/src/engine/nodes/_child_runner.py`
- 测试: `agent/tests/test_node_fail_diagnostics.py` (扩展)

### Task 4.29: col_error_message i18n 补全 4 locale (P1-18)

**问题**: `executions.col_error_message` i18n key 仅在 en-US 段存在, zh-CN/ja-JP/ko-KR 三段缺失, 导致这三语言下表格列头显示原始 key 字符串。

**文件:**
- 修改: `frontend/src/i18n/locales/executions.ts` (zh-CN/ja-JP/ko-KR 三段补 `executions.col_error_message`)

### Task 4.30: monitor/sub_pipeline options 拉取 (P1-19)

**问题**: `NodePropertyPanel.tsx:576/602` 的 monitor rule_id options 和 sub_pipeline pipeline_id options 硬编码空数组, 用户无法在 UI 选择。

**实现:**
- `frontend/src/api/tasks.ts` 新增 `fetchMonitorRules()` / `fetchPipelines()` 函数 (若不存在)
- NodePropertyPanel useEffect 拉取 options, 填入 Select

**文件:**
- 修改: `frontend/src/components/Pipeline/NodePropertyPanel.tsx`
- 修改: `frontend/src/api/tasks.ts`
- 测试: `frontend/src/test/NodePropertyPanel.test.tsx` (扩展)

### Task 4.31: convertStepsToStepInfo 读取 error_code (P1-20)

**问题**: `frontend/src/pages/Ops/Executions/index.tsx:235-259` 的 `convertStepsToStepInfo` 不读 `ts.error_code`, 历史 REST 加载的 step 不展示 error_code Tag (与 WS 实时事件不对称)。

**文件:**
- 修改: `frontend/src/pages/Ops/Executions/index.tsx` (line 250 后加 `error_code: ts.error_code,`)
- 修改: `frontend/src/components/Pipeline/StepProgressBar.tsx` (确认 StepInfo 接口已支持 error_code 字段)

### Task 4.32: NodePropertyPanel 实时 schema 校验 (P1-21)

**问题**: NodePropertyPanel 所有 Form.Item 仅用 Antd `rules=[{required: true}]` 做必填校验, 不调 `validatePipelineGraph` 做实时结构校验, 用户填完一个节点切换到下一节点时不会立即发现配置错误。

**实现:**
- 在 `updateConfig` 中加 `validatePipelineGraph` 调用 (节流, 避免 keystroke 触发)
- 把校验结果映射到对应 Form.Item 的 `validateStatus`/`help`

**文件:**
- 修改: `frontend/src/components/Pipeline/NodePropertyPanel.tsx`

### Task 4.33: click.py success path 补 coord_system (P1-22)

**问题**: `agent/src/engine/nodes/click.py:229-236` success path `result_data` 缺 `coord_system` 字段, click 是最高频动作节点, 影响跨设备对比。

**文件:**
- 修改: `agent/src/engine/nodes/click.py` (result_data 中补 `"coord_system": getattr(context, "coord_system", "") or "legacy"`)
- 测试: `agent/tests/test_node_fail_diagnostics.py` (扩展 click success 断言)

### Task 4.34: 删除死代码 *Config.tsx + 文档 deprecated 标注 (P2-19)

**问题 A**: `frontend/src/components/Pipeline/nodes/` 下 *Config.tsx 文件字段名仍用 camelCase, 但经全量 grep 验证无任何引用 (NodePropertyPanel 完全用内嵌 case), 是死代码。
- **N193 扩展**: 实施时发现不止 8 个文件死代码, 共 17 个 *Config.tsx 全部无外部引用 (ClickConfig/SwipeConfig/KeyPressConfig/.../SubPipelineConfig/GotoConfig), 一并清理。

**问题 B**: `docs/business/resources/resource-pack-design.md` header 只标 `last_updated: 2026-07-22`, 未整体标 `status: deprecated` (内容段已说明 chain schema 废弃)。

**文件:**
- 删除: `frontend/src/components/Pipeline/nodes/*Config.tsx` (17 个)
- 修改: `frontend/src/components/Pipeline/nodes/index.ts` (移除对应 export, 留注释说明)
- 修改: `docs/business/resources/resource-pack-design.md` (header 加 `status: deprecated` + `superseded_by`)

### Task 4.35: expandedRowRender Alert title 改为 message (P2-20)

**问题**: `frontend/src/pages/Ops/Executions/index.tsx:511-516` `<Alert title={...} description={failureReason} />`, Antd Alert 的标题属性是 `message` 不是 `title`, 当前不渲染标题。

**文件:**
- 修改: `frontend/src/pages/Ops/Executions/index.tsx` (line 511-516 把 `title=` 改为 `message=`)

---

## 阶段 7: 第五轮评估发现的新问题 (Task 4.36-4.51)

> **背景**: 2026-07-28 第五轮 N192 + N191 全量评估发现 4 P0 + 4 P1 + 12 P2 共 20 个新问题。
> 按 N193 任务归属硬约束, 纳入本 spec 并实现。
> **第五轮评分**: N192-A=9.4, N192-B=8.1, N191=8.8 (目标 9.0+/9.0+/9.5+)

### P0 阻断 (4 项, 阶段 7 新增)

| ID | 问题 | 来源 | 修复任务 |
|----|------|------|---------|
| P0-8 | ExecutionMonitorPanel 5 个干预操作引用 `resolveErrorMessage` 但未 import, 运行时 ReferenceError | N192-B1 + Task 4.22 回归 | Task 4.36 |
| P0-9 | `_check_pipeline_refs` 只读 legacy `pipelineId`, 前端写 `pipeline_id` 时校验失效 (Task 4.27 漏改) | N191 | Task 4.37 |
| P0-10 | PipelineEditorPage validate API 契约断裂: 前端期望 `{valid, errors}`, 后端返回 `{results}` | N192-B5 | Task 4.38 |
| P0-11 | NodePropertyPanel monitor/sub_pipeline Select `options={[]}` 硬编码, fetched options 未接入 (Task 4.30 漏改) | N192-B5 | Task 4.39 |

### P1 重要 (4 项, 阶段 7 新增)

| ID | 问题 | 来源 | 修复任务 |
|----|------|------|---------|
| P1-23 | en-US + ja-JP locale 缺 `error.codes.PRE_VERIFY_FAILED` (Task 4.24 漏改) | N192-B2 | Task 4.40 |
| P1-24 | PipelineEditorPage `handleValidate` 未调用 `validatePipelineGraph` 本地校验 (Task 3.5 漏改) | N192-B5 | Task 4.41 |
| P1-25 | `docs/business/resources/resource-pack-design.md:320` 示例残留 `templateId` | N191 | Task 4.42 |
| P1-26 | `docs/business/tasks/pipeline-design.md:422` 示例代码字段优先级与代码不一致 | N191 | Task 4.43 |

### P2 次要 (12 项, 阶段 7 新增)

| ID | 问题 | 来源 | 修复任务 |
|----|------|------|---------|
| P2-21 | `handler.py` task.result 失败消息体不传 error_code | N192-A | Task 4.44 |
| P2-22 | `handler.py` task.progress 失败步骤消息体不传 error_code | N192-A | Task 4.44 |
| P2-23 | NodePropertyPanel `nodeRequiredFields` 缺 4 节点类型 (login_account/switch_account/switch_resource/captcha_detect) | N192-B3 + N191 | Task 4.45 |
| P2-24 | PipelineEditorPage `handleValidate` catch 无 error 参数, 错误提示 generic | N192-B1 | Task 4.46 |
| P2-25 | notify.py success path result_data 缺 coord_system | N191 | Task 4.47 |
| P2-26 | sub_pipeline.py success path result_data 缺 coord_system | N191 | Task 4.47 |
| P2-27 | loop.py success path result_data 缺 coord_system (for + while 双路径) | N191 | Task 4.47 |
| P2-28 | branch.py success path result_data 缺 coord_system | N191 | Task 4.47 |
| P2-29 | roi_resolver.py result_data 用 `source_coord_type` 字段未与 `coord_system` 对齐 | N191 | Task 4.47 |
| P2-30 | sort_select.py success result_data 缺 coord_system | N191 | Task 4.47 |
| P2-31 | maa_actions.py AnchorNode success result_data 缺 coord_system | N191 | Task 4.47 |
| P2-32 | template_match_any.py success result_data 缺 coord_system | N191 | Task 4.47 |

---

### Task 4.36: ExecutionMonitorPanel resolveErrorMessage import 修复 (P0-8)

**问题**: `frontend/src/pages/Ops/Executions/ExecutionMonitorPanel.tsx` 在 5 个干预操作 (handlePause/handleResume/handleSkip/handleForceFail/handleCancel) 的 catch 块中调用 `resolveErrorMessage(error)`, 但 imports 段未导入该函数。一旦任意干预操作抛错, JS 引擎抛 `ReferenceError`, 用户看不到错误提示且按钮卡在 loading 状态。Task 4.22 (P2-17) 改动引入的回归。

**文件:**
- 修改: `frontend/src/pages/Ops/Executions/ExecutionMonitorPanel.tsx` (imports 段加 `import { resolveErrorMessage } from '@/utils/errorHandler';`)

---

### Task 4.37: _check_pipeline_refs 字段名归一化 (P0-9)

**问题**: `backend/pipeline/validators.py:247, 261` 的 `_check_pipeline_refs` 方法只读取 `data.get('pipelineId')` (legacy camelCase), 完全忽略 canonical `pipeline_id` (snake_case)。同一文件的 `_check_required_fields` (line 94) 已支持两种命名, 但 `_check_pipeline_refs` 漏改。前端 NodePropertyPanel 写入 `pipeline_id`, 导致用户配置后 `_check_required_fields` 通过但 `_check_pipeline_refs` 返回 "未选择 Pipeline" warning。

**实现:**
- `_check_pipeline_refs` 改为 `pipeline_id = data.get('pipeline_id') or data.get('pipelineId')`
- 同步更新 `backend/pipeline/tests/test_validators.py` 增加 `pipeline_id` canonical 用例

**文件:**
- 修改: `backend/pipeline/validators.py` (line 247, 261)
- 修改: `backend/pipeline/tests/test_validators.py` (增加 canonical 用例)

---

### Task 4.38: PipelineEditorPage validate API 契约对齐 (P0-10)

**问题**: 前端 `pipelineApi.validatePipeline(json)` 期望返回 `{valid: boolean, errors: string[]}`, 但后端 `PipelineValidateView.post` 返回 `{results: CheckItem[]}`。运行时 `res.valid` 永远 undefined, validate 按钮始终显示"验证未通过, 0 个错误"。

**实现 (方案 A — 前端适配后端):**
- `frontend/src/api/pipelines.ts` 的 `validatePipeline` 返回类型改为 `Promise<{ valid: boolean; results: ValidateResult[] }>`
- `frontend/src/pages/Tasks/PipelineEditor/PipelineEditorPage.tsx:629-643` 改为读 `res.results`, 过滤 `status === 'fail'` 的项作为 errors, `status === 'pass'` 全部 pass 时 valid=true

**文件:**
- 修改: `frontend/src/api/pipelines.ts` (validatePipeline 类型 + 解析)
- 修改: `frontend/src/pages/Tasks/PipelineEditor/PipelineEditorPage.tsx` (handleValidate 消费 results)

---

### Task 4.39: NodePropertyPanel monitor/sub_pipeline Select options 接入 (P0-11)

**问题**: `NodePropertyPanel.tsx:654-661` (monitor Select) 和 `:680-687` (sub_pipeline Select) 硬编码 `options={[]}`, 但 `monitorRuleOptions`/`pipelineOptions` state 通过 useEffect 拉取了数据却从未在 JSX 中使用。Task 4.30 (P1-19) 的实现遗漏 — 拉取了 options 但忘记在 Select 上绑定。

**文件:**
- 修改: `frontend/src/components/Pipeline/NodePropertyPanel.tsx` (monitor Select `options={monitorRuleOptions}`, sub_pipeline Select `options={pipelineOptions}`)

---

### Task 4.40: PRE_VERIFY_FAILED i18n 补 en-US + ja-JP (P1-23)

**问题**: `frontend/src/i18n/locales/common.ts` en-US (line 181-195) 和 ja-JP (line 277-291) 段缺 `error.codes.PRE_VERIFY_FAILED` 翻译键。Task 4.24 (P0-4) 只补了 zh-CN 和 ko-KR, 漏改 en-US 和 ja-JP。

**文件:**
- 修改: `frontend/src/i18n/locales/common.ts` (en-US 段加 `'error.codes.PRE_VERIFY_FAILED': 'Pre-execution verification failed'`, ja-JP 段加 `'error.codes.PRE_VERIFY_FAILED': '実行前検証に失敗しました'`)

---

### Task 4.41: PipelineEditorPage 接入 schemaValidator 本地校验 (P1-24)

**问题**: `schemaValidator.ts` (Task 3.5 产物) 已实现并接入 `Editor.tsx`, 但 `PipelineEditorPage.tsx` (同是 Pipeline 编辑器入口) 未引入 `validatePipelineGraph`, 直接调后端。两个入口校验口径不一致。

**实现:**
- PipelineEditorPage `handleValidate` 顶部加本地 ajv 校验: `const localErrors = validatePipelineGraph(json); if (localErrors.length > 0) { setValidateResults(localErrors); setValidateModalOpen(true); return; }`
- 与 `Editor.tsx:377-388` 对齐

**文件:**
- 修改: `frontend/src/pages/Tasks/PipelineEditor/PipelineEditorPage.tsx` (handleValidate + imports)

---

### Task 4.42: resource-pack-design.md templateId 归一化 (P1-25)

**问题**: `docs/business/resources/resource-pack-design.md:320` Pipeline 任务 JSON 示例的 `config` 字段仍使用 `templateId` (camelCase), 与 canonical `template_id` 不一致。

**文件:**
- 修改: `docs/business/resources/resource-pack-design.md` (line 320 把 `"templateId": "tpl_login_btn"` 改为 `"template_id": "tpl_login_btn"`)

---

### Task 4.43: pipeline-design.md 示例代码字段优先级对齐 (P1-26)

**问题**: `docs/business/tasks/pipeline-design.md:422` 示例代码 `template = config.get("template") or config.get("templateId")` 优先级与 `agent/src/engine/nodes/template_match.py:57` 实际实现 (优先 `template_id`) 不一致。

**文件:**
- 修改: `docs/business/tasks/pipeline-design.md` (line 422 改为 `template = config.get("template_id") or config.get("template") or config.get("templateId")`)

---

### Task 4.44: handler.py task.result + task.progress 透传 error_code (P2-21 + P2-22)

**问题**: `agent/src/client/handler.py` 失败消息体只传 `error_msg`, 不传 `error_code`, backend 无法按错误码分类, AI 调试时需 grep error_msg 字符串。

**实现:**
- `handle_task_assign` 失败路径 (line 355-366, 415-425, 503-515) 增加 `"error_code": getattr(result, "error_code", "")` 字段
- `on_step_progress` 回调 (line 310-315, 470-476) 失败步骤增加 `"error_code": step_result.error_code` 字段
- 设备解析失败路径用 `"error_code": NodeErrorCode.DEVICE_DISCONNECTED.value`

**文件:**
- 修改: `agent/src/client/handler.py` (5 处补 error_code)

---

### Task 4.45: NodePropertyPanel nodeRequiredFields 补 4 节点 (P2-23)

**问题**: `frontend/src/components/Pipeline/NodePropertyPanel.tsx:56-77` `nodeRequiredFields` dict 缺 4 个后端 node_required dict 中的节点类型: `login_account` / `switch_account` / `switch_resource` / `captcha_detect`。

**文件:**
- 修改: `frontend/src/components/Pipeline/NodePropertyPanel.tsx` (nodeRequiredFields 补 4 项: `login_account: [['account_id', 'accountId']]`, `switch_account: [['next_account_id', 'nextAccountId']]`, `switch_resource: [['resource_pack_id', 'resourcePackId']]`, `captcha_detect: [['targets', null]]`)

---

### Task 4.46: PipelineEditorPage handleValidate catch 加 error 参数 (P2-24)

**问题**: `frontend/src/pages/Tasks/PipelineEditor/PipelineEditorPage.tsx:645` `catch {` 无 error 参数, 只显示 generic `msg_validate_failed`, 用户看不到具体失败原因。

**文件:**
- 修改: `frontend/src/pages/Tasks/PipelineEditor/PipelineEditorPage.tsx` (handleValidate catch 改为 `catch (error) { message.error(resolveErrorMessage(error)); }`)

---

### Task 4.47: 8 节点 success path result_data 补 coord_system (P2-25 ~ P2-32)

**问题**: 8 个节点 success path 的 result_data 缺 `coord_system` 字段, 与 wait/goto/template_match 不一致。fail path 已通过 `_build_fail_diagnostics` 含 coord_system, success path 漏补。

**实现:** 在以下节点 success path 的 result_data 中添加 `"coord_system": getattr(context, "coord_system", "") or "legacy"`:

| 节点 | 文件:行号 | 子任务 ID |
|------|----------|----------|
| notify | `agent/src/engine/nodes/notify.py:153-159` | P2-25 |
| sub_pipeline | `agent/src/engine/nodes/sub_pipeline.py:125-133` | P2-26 |
| loop (for mode) | `agent/src/engine/nodes/loop.py:139-144` | P2-27 |
| loop (while mode) | `agent/src/engine/nodes/loop.py:156-163` | P2-27 |
| branch | `agent/src/engine/nodes/branch.py:91-98` | P2-28 |
| sort_select | `agent/src/engine/nodes/sort_select.py:255-263` | P2-30 |
| maa_actions AnchorNode | `agent/src/engine/nodes/maa_actions.py:584-592` | P2-31 |
| template_match_any | `agent/src/engine/nodes/template_match_any.py:187-189` | P2-32 |

**特殊处理 (P2-29 roi_resolver):** `agent/src/engine/nodes/roi_resolver.py:252-261` 用 `source_coord_type` 字段标识输入坐标系, 与 `coord_system` 字段名不一致。改为同时保留 `source_coord_type` (输入坐标系) + 新增 `coord_system: "logical"` (输出坐标系), 与 ocr.py 双字段模式一致。

**文件:**
- 修改: `agent/src/engine/nodes/notify.py`
- 修改: `agent/src/engine/nodes/sub_pipeline.py`
- 修改: `agent/src/engine/nodes/loop.py`
- 修改: `agent/src/engine/nodes/branch.py`
- 修改: `agent/src/engine/nodes/roi_resolver.py`
- 修改: `agent/src/engine/nodes/sort_select.py`
- 修改: `agent/src/engine/nodes/maa_actions.py`
- 修改: `agent/src/engine/nodes/template_match_any.py`

---

### Task 4.48: template_match_any fail path 补 count 字段 (回归修复)

**问题**: 第五轮评估跑测试时发现 `agent/tests/test_template_match_any.py::test_all_fail` 失败。根因: Task 4.28 (P1-17) 把 fail path 从直接传 `data={"children", "count", "matched"}` 改为 `_build_fail_diagnostics(**kwargs)` 时漏传 `count` 字段, 但测试期望 `result.data["count"] == 3`。

**修复**: 在 fail path 的 `_build_fail_diagnostics` kwargs 补 `count=len(results)`。

**文件:**
- 修改: `agent/src/engine/nodes/template_match_any.py` (line 208-219)

---

## 阶段 8: 第六轮评估发现的新问题 (Task 4.49-4.65)

> **背景**: 2026-07-28 第六轮 N192 + N191 全量评估发现 3 P0 + 13 P1 + 4 P2 共 20 个新问题。
> 按 N193 任务归属硬约束, 纳入本 spec 并实现。
> **第六轮评分**: N192-A=8.8, N192-B=7.86, N191=8.5 (目标 9.0+/9.0+/9.5+)

### P0 阻断 (3 项, 阶段 8 新增)

| ID | 问题 | 来源 | 修复任务 |
|----|------|------|---------|
| P0-12 | `backend/pipeline/tests/test_views.py:61` `_login` 函数 `resp.data['access']` 顶层取,但 API 实际返回 `{code,data:{access}}` 包装结构,导致 30+ backend 测试全失败 | N192-A (测试可调试性) | Task 4.49 |
| P0-13 | `resources/default/custom_tasks/template.json` `"template_id": null` 无注释,用户照着改但不知道必须替换 | N192-B4 | Task 4.50 |
| P0-14 | `resources/BrownDust-II/custom_tasks/template.json` 同上 | N192-B4 | Task 4.50 |

### P1 重要 (13 项, 阶段 8 新增)

| ID | 问题 | 来源 | 修复任务 |
|----|------|------|---------|
| P1-24 | `app_control.py:183` StartAppNode success path 缺 coord_system | N192-A2 | Task 4.51 |
| P1-25 | `app_control.py:331` StopAppNode success path 缺 coord_system | N192-A2 | Task 4.51 |
| P1-26 | `maa_actions.py:128` JumpBackNode success path 缺 coord_system | N192-A2 | Task 4.51 |
| P1-27 | `maa_actions.py:257` WaitFreezesNode success path 缺 coord_system | N192-A2 | Task 4.51 |
| P1-28 | `maa_actions.py:346` NextNode success path 缺 coord_system | N192-A2 | Task 4.51 |
| P1-29 | `maa_actions.py:398` StopNode success path 缺 coord_system | N192-A2 | Task 4.51 |
| P1-30 | `composite_match.py:126` ParallelMatchNode success path 缺 coord_system | N192-A2 | Task 4.51 |
| P1-31 | `composite_match.py:207` BestMatchNode success path 缺 coord_system | N192-A2 | Task 4.51 |
| P1-32 | `backend/pipeline/views.py:216,300,494,545` 4 处响应未走 unified_response | N192-B1/B2 | Task 4.52 |
| P1-33 | `backend/executions/views.py:62,95,99,110,138,143,154,165,206` 9 处响应未走 unified_response | N192-B1/B2 | Task 4.53 |
| P1-34 | `frontend/src/components/Pipeline/NodeDetailDrawer.tsx:319` error_code Tag 显示原始 code 未走 i18n | N192-B2 | Task 4.54 |
| P1-35 | `frontend/src/pages/Ops/Executions/index.tsx:530-538` antd Steps 不展示 error_code/error_message | N192-B3/B6 | Task 4.55 |
| P1-36 | `frontend/src/components/Pipeline/NodePropertyPanel.tsx:114` fetchMonitorRules 静默失败 | N192-B5 | Task 4.56 |
| P1-37 | `frontend/src/types/models.ts:746-757` TaskStepConfig 旧 chain schema 字段名 (UI-internal) | N191 | Task 4.57 |
| P1-38 | `resources/default/custom_tasks/` 缺 template_examples 多节点示例目录 | N192-B4 | Task 4.58 |
| P1-39 | `frontend/src/components/Pipeline/NodeDetailDrawer.tsx` 缺"复制诊断信息"按钮 | N192-B7 | Task 4.59 |

### Task 4.49: 修复 _login 函数取 token 路径 (P0-12)

**问题**: `backend/pipeline/tests/test_views.py:61` 的 `_login` 函数:
```python
assert isinstance(resp.data, dict) and 'access' in resp.data
token = resp.data['access']
```
但 API 实际返回 `{code: 0, data: {access: '...'}, message: 'ok'}` 包装结构 (unified_response),导致 30+ backend 测试在 setUp 阶段全失败。

**修复**: 优先取 `resp.data['data']['access']`,降级到 `resp.data['access']` 兼容旧裸响应。

**文件:**
- 修改: `backend/pipeline/tests/test_views.py` (`_login` 函数 line 55-64)
- 修改: `backend/pipeline/tests/test_chain_executor.py` (如有同样问题)
- 修改: `backend/pipeline/tests/test_routine_converter.py` (如有同样问题)

### Task 4.50: template.json 加 _comment 字段说明 (P0-13/14)

**问题**: `resources/default/custom_tasks/template.json` 和 `resources/BrownDust-II/custom_tasks/template.json` 的 `"template_id": null` 无注释说明,用户照着改但不知道必须替换为真实 template_id。

**修复**: 在 template.json 顶层加 `_comment` 字段说明:
- `template_id` 必须替换为资源包中真实 template_id
- `threshold` 范围 0-1
- `retry.max_retries` 含义
- `fallback.action` 可选值 (skip/stop/goto)

**文件:**
- 修改: `resources/default/custom_tasks/template.json`
- 修改: `resources/BrownDust-II/custom_tasks/template.json`

### Task 4.51: 8 个动作类节点 success path 补 coord_system (P1-24 ~ P1-31)

**问题**: 8 个动作类节点 success_result 的 data 字段缺 coord_system,与 26 个识别类节点不对齐 (识别类节点 success path 都已含 coord_system)。

**修复**: 在 8 个节点的 success_result data 字段补:
```python
"coord_system": getattr(context, "coord_system", "") or "legacy",
```

**文件:**
- 修改: `agent/src/engine/nodes/app_control.py` (StartAppNode line 183-186 + StopAppNode line 331-334)
- 修改: `agent/src/engine/nodes/maa_actions.py` (JumpBackNode 128-135 + WaitFreezesNode 257-260 + NextNode 346-353 + StopNode 398-405)
- 修改: `agent/src/engine/nodes/composite_match.py` (ParallelMatchNode 126-129 + BestMatchNode 207-215)

### Task 4.52: backend/pipeline/views.py 4 处响应改用 unified_response (P1-32)

**问题**: `backend/pipeline/views.py` 4 处错误响应返回 `{'error': '...'}` 裸 dict,无 error_code,前端 `resolveErrorMessage` 走不通 businessCode 分支。

**修复**: 改用 `unified_response(message=..., code=ErrorCode.X, status=...)`:
- `pipeline.execute` line 216-219 (没有在线 Agent)
- WS 发送失败 line 300-303 (`str(e)` 替换为友好文案)
- `TaskChain.execute` line 493-497
- `set_default` line 545-548

**文件:**
- 修改: `backend/pipeline/views.py`

### Task 4.53: backend/executions/views.py 9 处响应改用 unified_response (P1-33)

**问题**: `backend/executions/views.py` 9 处错误响应返回 `{'error': '...'}` 裸 dict。

**修复**: 全部改用 `unified_response(code=ErrorCode.INVALID_PARAMS/NOT_FOUND, ...)`:
- `execution_steps_view` line 62-65 (执行记录不存在)
- `execution_steps_view` line 95-103 (step_index 参数必须为整数)
- `execution_intervene_view` line 99/110/138/143/154/165/206 (7 处干预操作)

**文件:**
- 修改: `backend/executions/views.py`

### Task 4.54: NodeDetailDrawer error_code i18n 映射 (P1-34)

**问题**: `frontend/src/components/Pipeline/NodeDetailDrawer.tsx:319`:
```tsx
<Tag color="error">{trace.error_code}</Tag>
```
直接显示原始 code (如 "NO_MATCH"),未走 i18n 映射,与 `StepProgressBar.tsx:161` 不一致。

**修复**: 改为:
```tsx
const mapped = t(`error.codes.${trace.error_code}`);
<Tag color="error">{mapped !== `error.codes.${trace.error_code}` ? mapped : trace.error_code}</Tag>
```

**文件:**
- 修改: `frontend/src/components/Pipeline/NodeDetailDrawer.tsx`

### Task 4.55: executions list 替换 antd Steps 为 StepProgressBar (P1-35)

**问题**: `frontend/src/pages/Ops/Executions/index.tsx:530-538` 用 antd 原生 `<Steps>` 组件,只显示 step 名 + status,不展示 error_code/error_message,与 monitor tab 的 `StepProgressBar` 不一致。

**修复**: 替换为 `<StepProgressBar steps={convertStepsToStepInfo(stepList)} onStepClick={...} />`。

**文件:**
- 修改: `frontend/src/pages/Ops/Executions/index.tsx`

### Task 4.56: NodePropertyPanel fetchMonitorRules 错误提示 (P1-36)

**问题**: `frontend/src/components/Pipeline/NodePropertyPanel.tsx:114`:
```tsx
fetchMonitorRules().catch(() => { /* 静默失败, 不阻塞 UI; 用户仍可手填 ID */ })
```
无错误提示,用户不知道是网络问题还是无规则。

**修复**: 改为 `.catch((err) => setMonitorRuleError(resolveErrorMessage(err)))`,顶部 Alert 显示。同时检查 `listPipelines()` 调用是否同样静默失败。

**文件:**
- 修改: `frontend/src/components/Pipeline/NodePropertyPanel.tsx`

### Task 4.57: TaskStepConfig 重命名为 TaskStepConfigLegacy + @deprecated (P1-37)

**问题**: `frontend/src/types/models.ts:746-757` `TaskStepConfig` interface 字段名仍用旧 chain schema (`action_type` / `retry_count` / `retry_interval` / `fallback_action` / `next_step`),虽有注释说明这是 UI-internal flat representation,但字段名增加新人理解成本。

**修复**: 改名为 `TaskStepConfigLegacy` 并添加 `@deprecated` JSDoc 标注,说明新代码应使用 PipelineNode schema。

**文件:**
- 修改: `frontend/src/types/models.ts` (line 730-757)
- 修改: `frontend/src/pages/Tasks/Editor.tsx` (引用处)

### Task 4.58: 新增 template_examples 多节点示例目录 (P1-38)

**问题**: `resources/default/custom_tasks/` 仅 1 个 template.json (单节点 template_match 示例),用户照着改其他节点类型无参考。

**修复**: 新增 `resources/default/custom_tasks/template_examples/` 目录,含:
- `click.json` - click 节点示例
- `swipe.json` - swipe 节点示例
- `ocr.json` - ocr 节点示例
- `branch.json` - branch 节点示例
- `loop.json` - loop 节点示例
- `sub_pipeline.json` - sub_pipeline 节点示例

每个示例含 `_comment` 字段说明字段含义。

**文件:**
- 新增: `resources/default/custom_tasks/template_examples/click.json`
- 新增: `resources/default/custom_tasks/template_examples/swipe.json`
- 新增: `resources/default/custom_tasks/template_examples/ocr.json`
- 新增: `resources/default/custom_tasks/template_examples/branch.json`
- 新增: `resources/default/custom_tasks/template_examples/loop.json`
- 新增: `resources/default/custom_tasks/template_examples/sub_pipeline.json`

### Task 4.59: NodeDetailDrawer 加"复制诊断信息"按钮 (P1-39)

**问题**: `NodeDetailDrawer` 显示 error_code/error_msg/input_config/confidence/threshold,但用户无法一键复制完整诊断信息用于反馈给开发。

**修复**: 在 NodeDetailDrawer 顶部加"复制诊断信息"按钮,一键复制为 markdown 格式:
```
## 节点诊断信息
- step_index: 3
- node_id: tma1
- node_type: template_match_any
- error_code: NO_MATCH
- error_msg: template_match_any: all 3 templates failed
- confidence: 0.72
- threshold: 0.8
- coord_system: physical
- input_config: {...}
```

**文件:**
- 修改: `frontend/src/components/Pipeline/NodeDetailDrawer.tsx`

---

## 阶段 9: get_email pipeline 实机测试发现的新问题 (Task 4.66-4.69)

> **背景**: 2026-07-28 用户要求"打开 gaf 界面测试 get_email pipeline", 实机跑 `scripts/test_get_email_real.py` 发现 1 P0 + 2 P1 + 1 P2 共 4 个新问题。
> 按 N193 任务归属硬约束, 纳入本 spec 并实现。
> **测试环境**: Windows + LDPlayer + BrownDust II 游戏窗口 (hwnd=1640096)
> **测试结果**: open_mailbox ✅ (confidence=0.9364, coord_system=logical 已生效), wait_regular_email ❌ (OCR 找到 "公会\n好友" 而非 "普通邮箱", ROI 配置或游戏状态问题, 非代码 bug)

### P0 阻断 (1 项, 阶段 9 新增)

| ID | 问题 | 来源 | 修复任务 |
|----|------|------|---------|
| P0-15 | backend validator 与 agent parser schema 不一致: backend 要求 `node_type`/`template_id`/`timeout`/`condition`/`engine`+`language`, agent 接受 `type`/`template`/`max_wait`/`condition_variable`+`condition_operator`+`condition_value`/不强制 engine+language → UI 无法创建/校验 get_email 任务 (validate-payload 端点返回 valid=false, 10 个 required_fields 错误 + 11 个 legacy_fields 错误), 但 agent 能直接跑 (parser.py:239-242 已做 type→node_type 归一化, :152-160 已做 next_node_id→edges 推断) | 实机测试 (N191 schema 不一致) | Task 4.66 |

### P1 重要 (2 项, 阶段 9 新增)

| ID | 问题 | 来源 | 修复任务 |
|----|------|------|---------|
| P1-40 | `agent/src/utils/debug_image_saver.py:495` `_draw_bbox` 调用 `cv2.rectangle(img, (x,y), (x+w,y+h), ...)` 失败: `OpenCV(4.13.0) error: (-5:Bad argument) Can't parse 'pt1'. Sequence item with index 0 has a wrong type` — 原因是 box 元素是 numpy.int32 而非 Python int, OpenCV 4.13 不接受 → OCR debug image 保存失败 (N192-A2 中间结果落盘部分失效, 主流程不阻断) | 实机测试 (N192-A2) | Task 4.67 |
| P1-41 | `agent/src/ai/llm_client.py` 调用 backend `/api/v2/ai/chat/` 时未携带 Authorization token, 返回 HTTP 401 `{'code': 2001, 'message': '身份认证信息未提供。'}` → LLM 自动诊断功能失效 (N192-A5 retry/fallback trace 失效, diagnose_failure 返回 no diagnosis) | 实机测试 (N192-A5) | Task 4.68 |

### P2 次要 (1 项, 阶段 9 新增)

| ID | 问题 | 来源 | 修复任务 |
|----|------|------|---------|
| P2-7 | `core.orchestrator` 执行 pipeline 后未生成 exec-* 目录, `scripts/test_get_email_real.py` 报 "No exec-* directories found under D:\code\GAF\debug\agent" → N192-A2 中间结果落盘路径不一致, JSONL structured log 找不到 | 实机测试 (N192-A2) | Task 4.69 |

### Task 4.66: 统一 backend validator 与 agent parser schema (P0-15)

**问题**: `backend/pipeline/validators.py` 与 `agent/src/engine/parser.py` 对 pipeline schema 的字段要求不一致:

| 字段语义 | backend 要求 | agent 接受 | get_email.json 现状 |
|---------|------------|----------|------------------|
| 节点类型 | `node_type` (必填) | `node_type` 或 `type` 或 `action` (归一化到 node_type) | `type` (旧 schema) |
| 模板引用 | `template_id` (数字 ID, 必填) | `template` (字符串路径) | `template` (字符串路径) |
| 等待超时 | `timeout` (必填) | `max_wait` 或 `timeout` | `max_wait` |
| 分支条件 | `condition` (必填) | `condition_variable`+`condition_operator`+`condition_value` | 后者 (3 字段) |
| OCR 引擎 | `engine`+`language` (必填) | 不强制 | 未配置 |
| 节点连接 | `edges` 列表 | `edges` 或 `next_node_id` (推断 edges) 或线性顺序 | `next_node_id` |

**影响**:
- UI 走 backend `/api/v2/tasks/validate-payload/` 校验时, get_email.json 返回 valid=false (10 required_fields 错误 + 11 legacy_fields 错误), 用户无法在 UI 上创建/保存此任务
- 但 agent parser 能直接解析并执行 (parser.py:239-242 已做 type→node_type 归一化, :152-160 已做 next_node_id→edges 推断)
- 这种"backend 比 agent 严格"的不一致违反 N191 schema 归一化要求

**实现方案 (双向归一化, 选 A — backend 兼容旧字段)**:
- **理由**: agent parser 已实现归一化逻辑且稳定运行, 资源文件 (resources/*/pipelines/*.json) 全用旧 schema, 改 backend 兼容比改资源文件 + agent 风险低
- backend `pipeline/validators.py`:
  - `required_fields` 检查: 接受 `type`/`action` 作为 `node_type` 别名; `template` 字符串路径与 `template_id` 数字 ID 二选一; `max_wait` 与 `timeout` 二选一; `condition_variable`+`condition_operator`+`condition_value` 三件套与 `condition` 二选一; OCR `engine`+`language` 改为可选 (有默认值)
  - `legacy_fields` 检查: strict 模式仍 fail (主动验证归一化), 非 strict 模式 warn (兼容历史)
  - `connectivity` 检查: 接受 `next_node_id` 作为连接证据, 不强制要求 `edges` 列表
- 测试: `backend/pipeline/tests/test_validate_payload.py` 新增用例 — 旧 schema pipeline (用 get_email.json 作为 fixture) 在非 strict 模式下 valid=true, strict 模式下 valid=false 且 errors 含 legacy_fields

**文件:**
- 修改: `backend/pipeline/validators.py`
- 修改: `backend/pipeline/tests/test_validate_payload.py`
- 新增 fixture: `backend/pipeline/tests/fixtures/get_email_legacy_schema.json` (复制自 resources/BrownDust-II/pipelines/get_email.json)

---

### Task 4.67: 修复 debug_image_saver _draw_bbox numpy.int32 类型错误 (P1-40)

**问题**: `agent/src/utils/debug_image_saver.py:495`:
```python
def _draw_bbox(self, img, box, color):
    x, y, w, h = box  # box 来自 OCR 返回, 元素是 numpy.int32
    cv2.rectangle(img, (x, y), (x + w, y + h), color, 2, cv2.LINE_AA)
    # OpenCV 4.13 报错: Can't parse 'pt1'. Sequence item with index 0 has a wrong type
```

**根因**: OCR 返回的 bbox 是 numpy.ndarray, 解包后 x/y/w/h 是 numpy.int32 而非 Python int。OpenCV 4.13.0 的 `cv2.rectangle` 类型检查变严, 拒绝 numpy 标量。

**实现**:
```python
def _draw_bbox(self, img, box, color):
    x, y, w, h = box
    # 显式转 Python int, 兼容 numpy.int32 / numpy.int64 输入 (OpenCV 4.13+ 严格类型检查)
    x, y, w, h = int(x), int(y), int(w), int(h)
    cv2.rectangle(img, (x, y), (x + w, y + h), color, 2, cv2.LINE_AA)
```

**影响范围**: 检查 `_draw_bbox` 的所有调用点 (save_ocr_debug / save_template_match_debug / save_feature_match_debug 等), 确认 box 解包后都显式 int() 转换。

**文件:**
- 修改: `agent/src/utils/debug_image_saver.py` (`_draw_bbox` 函数及类似解包点)

---

### Task 4.68: agent LLM client 调 backend 时补 token (P1-41)

**问题**: `agent/src/ai/llm_client.py` 调用 `http://127.0.0.1:8000/api/v2/ai/chat/` 时未携带 Authorization header, backend 返回 401。

**根因**: agent 作为 backend 的内部服务, 应该有一个 service token 或长期 token 用于调 backend API。当前 AgentConfig 没有配置 backend token, llm_client 直接发裸请求。

**实现方案**:
- 方案 A (推荐): agent 启动时用 service account 凭据向 backend 换取长期 token, 缓存到 AgentConfig, llm_client 读取后加到 header
- 方案 B: backend 为 agent 内部调用提供免鉴权通道 (通过 IP 白名单或共享 secret header)
- 选 A: 在 `AgentConfig` 加 `backend_service_token` 字段, `llm_client` 读取后 `headers['Authorization'] = f'Bearer {token}'`
- service token 获取: agent 启动时调 `POST /api/v2/accounts/auth/login/` (用 service account 凭据, 从 .env 读取), 拿到 access token 后缓存, 失效时自动刷新

**文件:**
- 修改: `agent/src/core/config.py` (AgentConfig 加 backend_service_token 字段)
- 修改: `agent/src/ai/llm_client.py` (调用时补 Authorization header)
- 新增: `agent/src/core/auth.py` (service token 获取 + 刷新逻辑)
- 修改: `.env.example` (新增 GAF_SERVICE_USERNAME / GAF_SERVICE_PASSWORD)

---

### Task 4.69: 修复 orchestrator 不生成 exec-* 目录 (P2-7)

**问题**: `scripts/test_get_email_real.py` 执行后, `D:\code\GAF\debug\agent\` 下没有 exec-* 目录, 导致脚本找不到 JSONL structured log。

**根因排查方向**:
- `core/orchestrator.py` 的 `execute_pipeline` 在 debug_mode=True 时应该创建 `<DEBUG_DIR>/<YYYY-MM-DD>/<pipeline_name>/<HHMMSS>_<exec_id>/structured/` 目录
- 检查 `exec_id` 生成逻辑是否失败 (可能依赖 time.strftime 或 uuid)
- 检查 `structured_logger.py` 是否在写入前就 raise 了异常 (被吞掉)
- 检查 `debug_dir` 路径是否传错 (AgentConfig.debug_dir vs execute_pipeline 参数)

**实现**:
- 加日志: orchestrator.execute_pipeline 入口处打印 debug_dir 实际值 + exec_id
- 修复: 确保 `<DEBUG_DIR>/<date>/<pipeline_name>/<HHMMSS>_<exec_id>/structured/` 目录被创建并写入 JSONL
- 测试: 跑 `scripts/test_get_email_real.py` 后确认 exec-* 目录存在且 JSONL 文件非空

**文件:**
- 修改: `agent/src/core/orchestrator.py` (debug_dir + exec_id 创建逻辑)
- 修改: `agent/src/utils/structured_logger.py` (确保目录存在再写入)

---

## 阶段 10: 已知限制全部解决 (Task 5.1-5.4)

> **背景**: 2026-07-29 用户要求"已知限制这个也解决他啊", 按 N193 任务归属硬约束,
> 把原"已知限制"段 4 项全部纳入本 spec 并实现 (而非抛给用户作为后续工作).
> **结果**: 4 项全部 ✅ 已修复, spec 的"已知限制"段清空.

### Task 5.1: NodePropertyPanel 全量 i18n (P3, 原 P2-21)

**问题**: `frontend/src/components/Pipeline/NodePropertyPanel.tsx` 完全未使用 i18n (40+ 硬编码中文 label), conditional 节点 4 个 label 仍是英文, 12 处必填校验 message 仍是硬编码中文.

**实现:**
- 新增 `frontend/src/i18n/locales/nodePropertyPanel.ts` (4 locale: zh-CN/en-US/ja-JP/ko-KR, `npp.*` 命名空间)
- 修改 `NodePropertyPanel.tsx`: 导入 `useTranslation` 钩子, 100+ 硬编码中文 label + 4 个英文 label + 12 处校验 message 替换为 `t('npp.xxx')`
- 修改 `frontend/src/i18n/index.ts`: 注册 `nodePropertyPanel` 到 messages map

**文件:**
- 新增: `frontend/src/i18n/locales/nodePropertyPanel.ts`
- 修改: `frontend/src/components/Pipeline/NodePropertyPanel.tsx`
- 修改: `frontend/src/i18n/index.ts`
- **状态**: ✅ 已修复

### Task 5.2: 前端错误码映射表自动同步 (P4)

**问题**: i18n `error.codes.*` 映射表手动维护, 后端新增 ErrorCode 时前端不会自动同步, 容易漏.

**实现:**
- 新增 `scripts/bootstrap/sync_error_codes_i18n.py`:
  - AST 扫描 `backend/gaf_core/error_codes.py` (ErrorCode IntEnum + NodeErrorCode StrEnum) + `agent/src/core/error_codes.py` (NodeErrorCode 镜像)
  - 提取每个枚举成员的行内注释作为 zh-CN 默认文案
  - regex 扫描 `frontend/src/i18n/locales/common.ts` 4 个 locale 段的 `error.codes.*` key 集合
  - 报告 missing / extra key 差异
  - `--update` 模式: 自动追加缺失 key (zh-CN 用源码注释, en-US 用 enum name Title Case, ja-JP/ko-KR 用 `<TODO: translate>` 占位)
  - `--json` 模式: 输出 CI 友好的 JSON 报告
  - exit code: 0 = in sync, 1 = has diff (适合 hook / CI 集成)
- 设计原则: 不破坏人工翻译 (已有 key 一律保留), 不删除 extra key (避免误删废弃枚举)
- 测试: `scripts/tests/test_sync_error_codes_i18n.py` (5 个用例: AST 解析 / 期望 key 构建 / 前端扫描 / 差异报告 / 自动补全)
- 当前状态: 4 个 locale 各 35 个 `error.codes.*` key, 与后端 35 个枚举成员完全同步 (exit 0)

**文件:**
- 新增: `scripts/bootstrap/sync_error_codes_i18n.py`
- 新增: `scripts/tests/test_sync_error_codes_i18n.py`
- **状态**: ✅ 已修复

### Task 5.3: JSONL 日志聚合查询层 (P4)

**问题**: 当前 JSONL 是单次执行的扁平日志, 跨执行诊断需手动 grep. AI 想查"最近 7 天所有 TIMEOUT 失败的节点"或"按 error_code 分组失败率"只能逐文件 grep + 手工统计.

**实现:**
- 新增 `scripts/bootstrap/jsonl_query.py` (SQLite-backed, 无新依赖, sqlite3 标准库):
  - `ingest` 子命令: 递归扫描 `debug/**/structured.jsonl`, 扁平化关键字段后导入 SQLite 索引. 增量导入: 记录每个文件的 mtime + size, 未变化的文件跳过
  - `query` 子命令: 按 `--exec-id` / `--node-type` / `--event` / `--error-code` / `--pipeline` / `--failed-only` / `--success-only` / `--since` / `--until` / `--limit` 过滤查询事件
  - `stats` 子命令: 按指定字段 (`--group-by error_code|node_type|event|pipeline_name|execution_id`) 聚合统计, 输出 total/failed/fail%/avg_ms/min_ms/max_ms
  - `status` 子命令: 打印索引状态 (文件数 / 事件数 / 最后导入时间 / Top events / Top error codes)
  - `rebuild` 子命令: 清空 + 全量重新导入
  - 数据库位置: `debug/.jsonl_index.sqlite` (与 debug 目录同级, 避免污染源代码)
  - 自动增量: `query`/`stats` 子命令执行前自动跑 `ingest`, 保证数据最新
  - 字段扁平化: timestamp/execution_id/node_id/node_type/step_index/event/success/error_code/error_msg/elapsed_ms/confidence/coord_system/device_type/pipeline_name + raw_json (保留原始 payload)
  - pipeline_name 从父目录名解析 (格式 `YYYYMMDD_HHMMSS_<pipeline_name>_<exec_id>`)
- 测试: `scripts/tests/test_jsonl_query.py` (6 个用例: 单文件导入 / 增量跳过 / rebuild 清空 / 查询过滤 / 聚合统计 / pipeline_name 解析)
- 实机验证: 当前 debug 目录 2 个 JSONL 文件 8 个事件已正确导入, TIMEOUT 失败事件可查询, 按 error_code 聚合统计正确 (TIMEOUT 1 次 100% 失败, success path 1 次 0% 失败)

**文件:**
- 新增: `scripts/bootstrap/jsonl_query.py`
- 新增: `scripts/tests/test_jsonl_query.py`
- **状态**: ✅ 已修复

### Task 5.4: Agent structured.jsonl 未写入归一化 debug 目录 (P2, N194 已修复 2026-07-28)

**问题**: backend `dispatch_task` 已正确传递 `debug_dir` (归一化目录完整路径) 给 agent, 但归一化目录中只有 `meta.json` + `run.log` (backend 写), 缺少 `structured.jsonl` (agent 应写).

**根因**: `backend/protocol/consumers.py` 的 `task_assign` 方法转发 WS 消息时, 只挑选了部分字段 (execution_id/task_id/task_definition/device_info 等), **丢弃了 `debug_dir`/`debug_mode`/`game_account_id`/`resource_pack`/`start_step_index`/`previous_results` 等 N194 新增字段**. 导致 agent handler 收到 `debug_dir=''`, 兜底用 `./debug`, structured.jsonl 写到 `agent/debug/structured/<exec_id>.jsonl` 而非归一化目录.

**修复**: 在 `task_assign` 方法中透传所有 N194 字段 (debug_dir/debug_mode/game_account_id/game_account_name/resource_pack/start_step_index/previous_results).

**验证**: execution 122 归一化目录 `20260728_161619_..._122/` 含 `structured.jsonl` (5401 bytes, 7 行 JSONL) + `screenshots/` 目录 + agent 本地镜像 `agent/debug/20260728_..._122/structured.jsonl` (5401 bytes, 双写成功).

**文件:**
- 修改: `backend/protocol/consumers.py`
- **状态**: ✅ 已修复

---

## 阶段 11: debug 目录嵌套结构改版 (Task 6.1-6.11)

> **背景**: 2026-07-29 用户要求把扁平 ``debug/YYYYMMDD_HHMMSS_<pipeline>_<exec_id>/``
> 改为嵌套 ``debug/YYYYMMDD/<pipeline>/HHMMSS_<exec_id>/``, 按 日期→pipeline→执行
> 三级分组. 用户决策: 历史扁平目录直接删除; pipeline 重命名后孤儿目录保留不动;
> archives 跟着嵌套; 重点是双写路径 (backend 镜像 + agent 本地镜像).

### Task 6.1: 改 agent 权威生成器

**实现**:
- `agent/src/utils/debug_path.py` 三核心函数适配嵌套:
  - `build_execution_debug_dir`: 输出 ``<root>/<YYYYMMDD>/<safe_name>/<HHMMSS_suffix>/``
  - `_is_unified_exec_dir`: 检测 ``HHMMSS_<suffix>`` (嵌套) + 旧扁平兼容
  - `find_exec_dir_by_id`: 两层扫描 (date→pipeline→exec) + 旧扁平兼容

### Task 6.2: 同步 backend 镜像

**实现**: `backend/gaf_core/debug_path.py` 三函数镜像同步.

### Task 6.3: 修复双写路径

**实现**:
- `agent/src/utils/structured_logger.py _resolve_mirror_path`: 保留三层嵌套镜像
  (旧版只取 basename 一层, 嵌套结构下会丢 date/pipeline 两层)
- `backend/tasks/tasks.py dispatch_task`: 用 ``os.path.relpath`` 代替 ``os.path.basename``
  保留嵌套层级
- `backend/gaf_core/handlers.py`: 调 ``find_exec_dir_by_id`` 自动跟随, 无需改

### Task 6.4: 修复技术债 pipeline/views.py

**实现**: `backend/pipeline/views.py` 从硬编码 ``f"{dir}/{ts}_{safe_name}"`` 迁移到
``build_execution_debug_dir`` 调用, 与 ``dispatch_task`` 入口统一. 此前这是唯一仍用
旧格式的生成器.

### Task 6.5-6.6: 外部解析器 + cleanup

**实现**:
- `scripts/bootstrap/jsonl_query.py`: pipeline_name 从祖父目录取 (嵌套) + 旧扁平兼容
- `backend/gaf_core/tasks.py cleanup_old_archives`: rglob 递归扫 + 嵌套目录清理 + 空目录自动清理

### Task 6.7: archive 路径嵌套

**实现**: `backend/debug/services.py pack_execution_logs` 从 src_dir 反推 date/pipeline
拼嵌套 archive 路径 ``<archive_dir>/<YYYYMMDD>/<pipeline>/<exec_id>.tar.gz``.

### Task 6.8-6.10: 测试 + i18n + 文档

**实现**:
- `scripts/tests/test_jsonl_query.py`: fixture 改嵌套结构, 6/6 测试通过
- `frontend/src/i18n/locales/settings.ts`: 4 locale ``agent_debug_dir_desc`` 更新为嵌套格式
- `scripts/monitor_logs.ps1`: 注释更新
- `docs/business/tasks/debug-mode-design.md`: 顶部加过时标注, 指向本 spec
- `backend/tracing/{context,models}.py` + `backend/gaf_ai/agent/tools.py`: 过时注释更新

### Task 6.11: 测试 + 删除历史目录

**实现**: 跑全量测试验证 + 删除 debug/ 下所有扁平历史目录 (保留 _global/ + .jsonl_index.sqlite).

**文件:**
- 修改: `agent/src/utils/debug_path.py`, `agent/src/utils/structured_logger.py`
- 修改: `backend/gaf_core/debug_path.py`, `backend/gaf_core/tasks.py`, `backend/gaf_core/handlers.py` (无改, 自动跟随)
- 修改: `backend/tasks/tasks.py`, `backend/pipeline/views.py`, `backend/debug/services.py`
- 修改: `backend/tracing/context.py`, `backend/tracing/models.py`, `backend/gaf_ai/agent/tools.py`
- 修改: `scripts/bootstrap/jsonl_query.py`, `scripts/tests/test_jsonl_query.py`
- 修改: `scripts/monitor_logs.ps1`, `frontend/src/i18n/locales/settings.ts`
- 修改: `docs/business/tasks/debug-mode-design.md`
- **状态**: ✅ 已完成 (受影响测试 89/89 通过, 历史扁平目录已删除)

### Task 6.12: 修复过时测试 (N193 任务归属)

**背景**: Task 6.11 全量测试发现 3 个测试文件期望旧扁平格式 `<tmpdir>/logs/<exec_id>/run.log`,
与 N194 嵌套结构不匹配. 这些测试在 N194 归一化时未同步更新, 属于本次任务发现的问题,
按 N193 纳入当前 spec 修复.

**实现**:
- `backend/tracing/tests/test_log_handler.py`: 3 个测试加 `_precreate_exec_dir` helper,
  期望路径改为嵌套 `<exec_dir>/run.log`
- `backend/gaf_core/tests/test_file_log_handler.py`: 6 个测试同上,
  `_global` fallback 路径去掉 `logs/` 前缀
- `backend/gaf_core/tests/test_cleanup_old_archives.py`: 5 个测试移除 `jsonl_deleted` 断言
  (N194 改为 `exec_dirs_deleted`), 新增 `test_deletes_old_exec_dirs_keeps_recent` 测试嵌套目录清理

**文件:**
- 修改: `backend/tracing/tests/test_log_handler.py`
- 修改: `backend/gaf_core/tests/test_file_log_handler.py`
- 修改: `backend/gaf_core/tests/test_cleanup_old_archives.py`
- **状态**: ✅ 已完成 (14/14 测试通过)

### Task 6.13: 前端通知声音默认关闭 (用户反馈)

**背景**: 2026-07-29 用户反馈 "agent启动的声音给我默认关闭". 排查发现:
- `frontend/src/hooks/useAudioAlert.ts` `readMuted()` 默认返回 `false` (声音开)
- `frontend/src/components/Notifications/NotificationPreferences.tsx` 3 处 `sound_alert ?? true`

**实现**: 声音默认改为关闭, 用户需手动开启:
- `useAudioAlert.ts` `readMuted()`: `raw === null` 时返回 `true` (默认静音)
- `NotificationPreferences.tsx` 3 处 `sound_alert ?? true` → `?? false`
- `NotificationPreferences.tsx` `initialValues.sound_alert: true` → `false`

**文件:**
- 修改: `frontend/src/hooks/useAudioAlert.ts`
- 修改: `frontend/src/components/Notifications/NotificationPreferences.tsx`
- **状态**: ✅ 已完成

---

## 验收标准

- [x] agent 全量测试通过 (2154 passed, 3 skipped, 0 failed, 150s) — 2026-07-29
  - 根因: pyproject.toml 配置 DJANGO_SETTINGS_MODULE 导致 pytest-django 插件
    在 agent 测试时也加载 Django 环境, 每测试多 12s Django setup 开销
  - 修复: 跑 agent 测试用 `python -m pytest agent/tests/ -p no:django -o addopts=""`
    禁用 django 插件, 速度从 ~2h 提升到 2.5min (48x)
- [x] backend 全量测试通过 (排除环境性 Redis 连接失败) — 1788 passed, 0 failed (2026-07-29)
- [x] frontend `npx tsc -p tsconfig.app.json --noEmit` 0 错误 (2026-07-29)
- [x] frontend `npm run build` 构建成功 (2026-07-29)
- [x] scripts/tests/test_sync_error_codes_i18n.py 5 用例全通过 (Task 5.2)
- [x] scripts/tests/test_jsonl_query.py 6 用例全通过 (Task 5.3, Task 6.8 嵌套结构适配)
- [x] 嵌套结构受影响测试 89/89 通过 (Task 6.11: debug_path + structured_logger +
      jsonl_query + file_log_handler + cleanup_old_archives + debug_image_saver)
- [x] N192 视角 A 成熟度 ≥ 9.0/10 (覆盖 4 阶段共 65 个 Task, A1-A7 全部实现)
- [x] N192 视角 B 成熟度 ≥ 9.0/10 (覆盖 4 阶段共 65 个 Task, B1-B7 全部实现)
- [x] N191 架构归一化成熟度 ≥ 9.5/10 (chain→pipeline 归一化 + nested schema +
      字段名三方对齐 + debug 嵌套结构 + 文档全部归一化)
- [x] 无"遗留建议"表述,所有问题已实现或在已知限制段记录
- [x] 原"已知限制"段 4 项全部已修复 (Task 5.1/5.2/5.3/5.4)
- [x] debug 目录嵌套结构改版完成 (Task 6.1-6.13), 历史扁平目录已删除
- [x] 阶段 12 (Task 7.1-7.5) 全部完成 — 预先存在的测试/类型问题清零
  - Task 7.1 ✅: ScreenshotCache Redis 失败降级修复 (8/8 测试通过)
  - Task 7.2 ✅: backend conftest.py 全局 mock channel_layer (Redis 信号隔离)
  - Task 7.3 ✅: 3 个测试断言归一化 (test_execution_api + test_views)
  - Task 7.4 ✅: backend 测试批量适配 unified_response 信封 (~100 个失败归零,
    subagent 修了 14 个测试文件 ~80 个失败 + 主 agent 补修遗漏的 3 个, 全量 1788 passed)
  - Task 7.5 ✅: frontend TypeScript 错误清零 (271 → 0, 两个 subagent 分两轮修复)

## 阶段 12: 预先存在的问题清零 (Task 7.1-7.5)

> **背景**: 2026-07-29 用户要求"先修预先存在的问题"再归档 spec.
> 按 N193 任务归属硬约束, 把原"已知限制"段 3 项 (agent test_screenshot_cache_ttl /
> backend 测试失败 / frontend TS 错误) 全部纳入本 spec 实现, 不再作为"已知限制"抛出.
> 阶段 12 实施后, 已知限制段清空, spec 可归档到 done/.

### Task 7.1: 修复 ScreenshotCache Redis 失败降级 (原 P3)

**问题**: `agent/src/devices/screenshot_cache.py:186` `int(effective_ttl)` 把 float `0.1`
截为 `0`, Redis `setex` 拒绝 ttl=0 报错; `get()` 在 Redis 返回 None (key 不存在) 时
不降级查 memory, 导致 set 失败 fallthrough 到 memory 后, get 仍只查 Redis 返回 None
(数据丢失路径).

**实现**:
- `set()`: Redis `setex` ttl 用 `max(1, int(round(effective_ttl)))` 保证 ≥1, 避免截断到 0
- `get()`: Redis 返回 None 时 fallthrough 到 memory 查 (与 set 的 fallthrough 对称)
- 测试: `test_screenshot_cache_ttl` 不再依赖"int(0.1)=0 触发 Redis 失败"副作用

**文件:**
- 修改: `agent/src/devices/screenshot_cache.py`
- 修改: `agent/tests/test_degradation_chain.py` (如需)

### Task 7.2: backend Redis 信号路径 mock (16 个测试)

**问题**: `backend/tasks/signals.py:208` `broadcast_execution_status` 信号触发
`channel_layer.group_send` 打真实 Redis, 测试未 mock 此路径, 导致 16 个测试
`redis.exceptions.ConnectionError`.

**实现**:
- `backend/conftest.py` (或对应目录 conftest) 全局 patch `channel_layer.group_send`
  为 Mock, 避免测试打真实 Redis
- 不修改信号/消费者代码 (生产逻辑正确, 仅测试隔离缺口)

**文件:**
- 修改: `backend/conftest.py` (或 `backend/tasks/tests/conftest.py`)

### Task 7.3: backend 响应 schema 断言归一化 (3 个测试)

**问题**: 3 个测试断言旧 schema (`error`/`valid_actions` 顶层键), 实际响应已归一为
`{code, message, data}` 结构.

**实现**:
- `test_invalid_action_returns_400_with_list`: `body['valid_actions']` → `body['data']['valid_actions']`
- `test_missing_action_returns_400`: `body['error']` → `body['message']`
- `test_validate_returns_check_items_with_node_id`: 适配新响应结构

**文件:**
- 修改: `backend/executions/tests/test_execution_api.py`
- 修改: `backend/tasks/tests/test_views.py`

### Task 7.4: backend 测试批量适配 unified_response 信封 (~100 个测试)

**问题**: 阶段 1 Task 1.1 启用 `GAF_UNIFIED_RESPONSE_ENABLED=True` 后, 后端响应统一归一为
`{code, message, data}` 结构, 但 ~100 个测试断言仍读顶层字段, 导致大面积回归失败。

**实际跑全量 backend 测试发现的失败分布** (2026-07-29):
- accounts/test_accounts.py: 5 (detail → message)
- accounts/test_game_account.py: 5 (id/game_name/username/results 顶层 → data.*)
- accounts/test_jwt_refresh.py: 7 (access/refresh 顶层 → data.*)
- accounts/test_user_session.py: 4 (期望 1 实际 3 filter 缺失 + TypeError)
- scheduler/test_scheduler_plan.py: 7 (days 顶层 + ErrorCode vs string)
- scheduler/test_scheduler_timewindow.py: 5 (start_time 顶层 + 期望 1 实际 [])
- scheduler/test_unattended_session.py: 21 (session_id/status/mode_status 顶层)
- scheduler/test_unattended.py: 14 (同上)
- search/test_search.py: 5 (tasks/totalCount 顶层)
- settings/test_appsettings.py: 1 (setting_key 顶层)
- settings/test_strategy.py: 4 (recovery 顶层)
- skills/test_skill_market.py: 8 (skill_name/title 顶层 + 期望 1 实际 3)
- tasks/test_tasks.py: 1 (validate_returns_check_items 期望 200 实际 400 — Task 1.5 设计变更)
- tests/test_auth_flow.py: 5 (id/access/refresh/initialized 顶层)
- tests/test_integration.py: 9 (id/templates/review_status/status 顶层)
- tracing/tests/test_api.py: 4 (trace_id/traces 顶层)
- tracing/tests/test_logentry_filter.py: 2 (results 顶层)

**实现策略** (复用 `backend/pipeline/tests/test_views.py` 已有的 `_unwrap`/`_get_results`
helper 模式):
- 在每个测试文件加 `_unwrap(resp)` helper (优先取 `resp.data['data']`, 降级到 `resp.data`)
- 在每个测试文件加 `_login` helper 适配 (优先取 `resp.data['data']['access']`)
- 断言 `resp.data['error']` → `resp.data['message']`
- 断言 `resp.data['code'] == 'already_running'` → `resp.data['code'] == ErrorCode.INVALID_PARAMS`
  (后端错误响应 code 已归一为 ErrorCode 数字枚举)
- 错误响应断言: 检查 `code` (ErrorCode 数字) + `message` (中文文案) + `data` (额外上下文)
- 分页响应: `resp.data['results']` → `_unwrap(resp)['results']` 或 `_get_results(resp)`

**特殊处理**:
- `tasks/test_tasks.py::test_validate_returns_check_items_with_node_id`: spec Task 1.5
  设计变更为校验失败返回 400 (而非 200), 测试期望需更新为 400
- `accounts/test_user_session.py`: 期望 1 实际 3 是 filter 缺失 — 排查是否是 spec 阶段 5/6
  字段名归一化引入的回归 (如 `pipelineId` → `pipeline_id`)
- `skills/test_skill_market.py`: 期望 1 实际 3 是 fixture 数据污染 — 排查 setUp 共享状态
- `scheduler/test_scheduler_timewindow.py`: 期望 1 实际 [] — 排查 enabled filter

**文件:**
- 修改: `backend/accounts/tests/test_accounts.py`
- 修改: `backend/accounts/tests/test_game_account.py`
- 修改: `backend/accounts/tests/test_jwt_refresh.py`
- 修改: `backend/accounts/tests/test_user_session.py`
- 修改: `backend/scheduler/tests/test_scheduler_plan.py`
- 修改: `backend/scheduler/tests/test_scheduler_timewindow.py`
- 修改: `backend/scheduler/tests/test_unattended_session.py`
- 修改: `backend/scheduler/tests/test_unattended.py`
- 修改: `backend/search/tests/test_search.py`
- 修改: `backend/settings/tests/test_appsettings.py`
- 修改: `backend/settings/tests/test_strategy.py`
- 修改: `backend/skills/tests/test_skill_market.py`
- 修改: `backend/tasks/tests/test_tasks.py` (validate 端点 400 vs 200)
- 修改: `backend/tests/test_auth_flow.py`
- 修改: `backend/tests/test_integration.py`
- 修改: `backend/tracing/tests/test_api.py`
- 修改: `backend/tracing/tests/test_logentry_filter.py`

### Task 7.5: frontend TypeScript 错误清零 (271 个错误, 76 个文件)

**问题**: frontend TypeScript 编译错误 271 个, 分 7 类:
- TS6133/TS6196 未使用导入/变量 (~50 个)
- TS7006 隐式 any 参数 (~35 个, 多在 PipelineEditorPage.tsx 21 个)
- TS2339 属性不存在 (~40 个, ScanModal/EmulatorManagement/Accounts)
- TS2345 类型不匹配 (~50 个, Plugin vs PluginItem, string/number 混用)
- TS2304 找不到名称 (~7 个, theme/token/afterEach 缺 import)
- TS1261/TS1149 文件名大小写冲突 (2 个)
- TS2786 JSX 组件类型不合法 (2 个)
- P0: ajv 未正确安装 (4 个错误)

**实现策略** (按优先级分批):
1. **P0 环境**: `npm install` 安装 ajv@8 (修复 schemaValidator.ts 4 个错误)
2. **P1 类型归一**: 删除 `Plugin` 接口 (models.ts:796), 统一用 `PluginItem`; 修
   `AgentStatusEnum`/`TaskStepStatusEnum` 改用内联 union; 修 `total_accounts` → `totalAccounts`
3. **P2 缺 import**: theme/token/afterEach 在 4-7 处补 import
4. **P3 文件名大小写**: TagPicker/Form 路径归一
5. **P3 未使用清理**: 删除 ~50 个未使用导入/变量 (批量)
6. **P3 隐式 any**: PipelineEditorPage 21 个回调参数加类型注解
7. **P3 属性不存在/类型不匹配**: 逐个文件排查 (ScanModal/EmulatorManagement/Accounts 等)

**文件:**
- 修改: `frontend/package.json` (ajv 安装)
- 修改: `frontend/src/types/models.ts` (Plugin 删除, AgentStatus/StepStatus 改 union)
- 修改: `frontend/src/stores/usePluginStore.ts` (PluginItem)
- 修改: `frontend/src/stores/__tests__/useUnattendedStore.test.ts` (camelCase)
- 修改: `frontend/src/utils/schemaValidator.ts` (ajv 类型修正)
- 修改: 76 个文件 (按 P0/P1/P2/P3 分批)

---

## 已知限制 (清空)

> 阶段 12 (Task 7.1-7.5) 实施后, 原"已知限制"段 3 项全部纳入 spec 实现.
> 当前 spec 无已知限制.
