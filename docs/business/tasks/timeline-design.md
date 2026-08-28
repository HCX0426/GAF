---
summary: '调试产物时间链路设计 — 让用户和 AI 都能按时间链追溯问题 (2026-07-29 废弃: timeline_generator/diagnosis_generator/score_curve_generator 三个工具已删除, 改用 JSONL trace + 前端节点详情抽屉)'
applies_to: [agent, design]
last_updated: 2026-07-29
---

# 调试产物时间链路设计

> **日期**: 2026-07-24
> **状态**: 已废弃 (2026-07-29) — 原计划的 timeline_generator.py / diagnosis_generator.py / score_curve_generator.py 三个工具从未实现到 agent/src/utils/, N192 双调试视角改用 JSONL trace + 前端节点详情抽屉 (ExecutionMonitorPanel + node-trace 端点) 替代。本文档保留作为设计参考。
> **来源**: 用户反馈 — "用户要能通过日志和截图的时间链发现问题，目前 IDE 的 AI 也要能读出哪里出现了问题，就和前面你自己调试一样"
> **前置文档**: [debug-mode-design.md](debug-mode-design.md)（2026-07-12，基础调试模式架构）

## 1. 背景与目标

### 问题

BD2 get_email pipeline 测试中发现模板匹配评分低（0.47），根因是 DPI 缩放未接入 ImageProcessor.find_template。诊断过程暴露了调试产物的 5 个缺口：

1. **wait 节点循环中间状态丢失** — `wait_template` 循环 check 20 次，中间 19 次失败的截图不保存，只在结束时保存 1 张。AI 无法看到「为什么一直没匹配到」。
2. **调试目录分散** — 调试图分散在 `template_match/`、`ocr/`、`action/` 三个子目录，JSONL 在 `structured/`，AI 要读 4 个目录才能拼出时间链。
3. **无任务级时间线索引** — 没有 `timeline.md` 把「事件 → 截图 → 指标」按时间串起来，AI 必须逐行读 JSONL。
4. **调试图文件名缺步骤序号** — 文件名如 `match_success_主界面_143025123.png`，AI 看文件名无法知道这是第几步、属于哪个执行。
5. **wait 失败时无诊断提示** — wait 超时只返回 `template not found within 5.0s`，不像 template_match 有详细调试图（含 score/threshold）。AI 不知道是「模板不存在」还是「DPI 不匹配」还是「UI 没出现」。

### 目标

1. **用户视角**: 用户通过 `timeline.md` + 调试图按时间链追溯问题，一个文件看完整个执行流程
2. **AI 视角**: AI 通过 `diagnosis.md` + wait 失败快照直接读出问题，不需要手写诊断脚本
3. **长期架构**: 调试产物按执行 ID 归档，目录结构统一，便于清理和程序化分析

## 2. 现有架构评估

### 已有基础设施（复用）

| 组件 | 位置 | 作用 | 评估 |
|------|------|------|------|
| DebugImageSaver | [debug_image_saver.py](file:///d:/code/GAF/agent/src/utils/debug_image_saver.py) | 保存带标注的调试图（ROI 蓝框/匹配红框/模板缩略图/scale 信息） | ✅ 信息密度高，AI 可读，无需重写 |
| StructuredLogger | [structured_logger.py](file:///d:/code/GAF/agent/src/utils/structured_logger.py) | JSONL 结构化日志，每行一个事件，含 screenshot_path 关联调试图 | ✅ LLM 友好设计，schema 完整 |
| 执行 ID | `exec-<uuid12>` | 一次 pipeline 跑一个 ID，JSONL 文件名含 ID | ✅ 可追溯，但调试图文件名未含 |
| screenshot_path 关联 | JSONL 字段 | 每个事件记录对应调试图路径 | ✅ 已串联，但分散目录 |

### 关键缺口（本设计解决）

| 缺口 | 影响 | 本设计章节 |
|------|------|-----------|
| wait 循环中间状态丢失 | AI 无法诊断 wait 超时根因 | §3.1 |
| 调试图无步骤序号 | AI 难以按顺序还原执行 | §3.2 |
| 无时间线索引 | AI 必须逐行读 JSONL | §3.3 |
| 无诊断报告 | AI 需手写脚本才能诊断 | §3.4 |
| 调试目录分散 | AI 要读 4 个目录 | §3.5 |
| 无匹配分数曲线 | 潜在风险点不直观 | §3.6 |

## 3. 设计

### 3.1 wait 节点循环中间状态保存

**问题**: `wait_template` / `wait_disappear` / `wait_ocr` 循环 check N 次，只在结束时保存 1 张调试图。

**方案**: 失败时保存最后 N 次 check 的截图（默认 N=3）。

**实现位置**: [wait.py](file:///d:/code/GAF/agent/src/engine/nodes/wait.py) `_wait_template` / `_wait_disappear` / `_wait_ocr` 超时失败分支

**新增数据结构**:
```python
# wait.py _wait_template 内部
check_history: list[dict] = []  # 最近 N 次 check 的诊断数据
CHECK_HISTORY_SIZE = 3

while time.monotonic() < deadline:
    screen = device.capture_screen()
    match = image_processor.find_template(screen, template, roi=roi, threshold=threshold)
    if match:
        return success_result(...)
    # 记录最近 N 次失败 check
    check_history.append({
        "timestamp": time.monotonic() - start,
        "score": match.get("confidence", 0.0) if match else 0.0,
        "screenshot": screen,  # 保留 ndarray 引用，结束时保存
    })
    if len(check_history) > CHECK_HISTORY_SIZE:
        check_history.pop(0)
    time.sleep(check_interval)

# 超时失败 — 保存最后 N 次 check 截图
if check_history:
    from utils.debug_image_saver import DebugImageSaver
    saver = DebugImageSaver(debug_dir=os.path.join(debug_dir, "wait_failure"))
    for i, check in enumerate(check_history):
        saver.save_template_debug(
            screen=check["screenshot"],
            template_orig=template_img,  # 期望模板
            template_scaled=None,
            template_name=f"{node_id}_check{i+1}",
            is_success=False,
            confidence=check["score"],
            threshold=threshold,
            scale_ratio=0.0,  # wait 不做 DPI 缩放（走 ImageProcessor 已处理）
            roi_phys=roi_phys,
            match_bbox_phys=None,
        )
```

**输出目录**: `<debug_dir>/wait_failure/wait_<node_id>_fail_check{1,2,3}.png`

**JSONL 事件**: 新增 `wait.check.fail` 事件（DEBUG 级别，每次 check 都记录）
```json
{
  "event": "wait.check.fail",
  "node_id": "wait_main_menu",
  "step_index": 11,
  "success": false,
  "confidence": 0.42,
  "threshold": 0.8,
  "check_index": 5,
  "elapsed_ms": 2500,
  "screenshot_path": "debug/.../wait_failure/wait_main_menu_fail_check3.png"
}
```

### 3.2 调试图文件名加步骤序号 + 执行 ID

**问题**: 当前文件名 `match_success_主界面_143025123.png` 无步骤序号和执行 ID。

**方案**: 文件名格式改为 `step{NN}_{node_type}_{status}_{node_id}_{exec_id}_{ts}.png`

**示例**:
- 旧: `match_success_主界面_143025123.png`
- 新: `step03_template_match_success_open_mailbox_exec-abc123_143025123.png`

**实现位置**: [debug_image_saver.py](file:///d:/code/GAF/agent/src/utils/debug_image_saver.py) `save_template_debug` / `save_ocr_debug` / `save_action_debug` 签名新增 `step_index` + `execution_id` 参数

**调用方改动**: 所有调用 `_save_debug` 的节点（template_match / ocr / wait / click / swipe / key_press）从 PipelineContext 读取 `step_index` 和 `execution_id` 传入

**向后兼容**: step_index 和 execution_id 可选，缺省时用旧格式（不破坏现有测试）

### 3.3 任务级时间线索引 timeline.md

**问题**: AI 必须逐行读 JSONL 才能理解流程。

**方案**: 任务结束时自动生成 `timeline.md`，一行一个节点，含时间/状态/指标/截图路径。

**输出路径**: `<debug_dir>/structured/<execution_id>_timeline.md`

**内容格式**:
```markdown
# 执行时间线: get_email (exec-abc123def456)

- **Pipeline**: get_email
- **执行 ID**: exec-abc123def456
- **开始**: 2026-07-24T14:30:25.123Z
- **结束**: 2026-07-24T14:31:12.456Z
- **总耗时**: 47.333s
- **状态**: SUCCESS

## 节点执行顺序

| Step | Time | Node ID | Type | Status | Score/Threshold | Screenshot |
|------|------|---------|------|--------|-----------------|------------|
| 01 | +0.000s | open_mailbox | template_match | ✅ SUCCESS | 0.9592/0.80 | [step01_template_match_success_open_mailbox_...png](../template_match/step01_...) |
| 02 | +0.450s | wait_regular_email | wait(ocr) | ✅ SUCCESS | — | [step02_wait_success_wait_regular_email_...png](../action/step02_...) |
| 03 | +5.500s | detect_empty_email | template_match | ✅ SUCCESS | 0.8800/0.80 | [step03_...](../template_match/step03_...) |
| 04 | +5.950s | branch_empty_email | branch | ✅ SUCCESS | — | — |
| 05 | +5.950s | claim_all_rewards | ocr | ❌ FAIL | — | [step05_ocr_fail_claim_all_rewards_...png](../ocr/step05_...) |

## 失败节点详情

### Step 05: claim_all_rewards (ocr) — FAIL
- **耗时**: 1.200s
- **错误**: OCR 未识别到「全部领取」文本
- **诊断**: 可能是 UI 未出现，或文本被遮挡
- **调试图**: [step05_ocr_fail_claim_all_rewards_...png](../ocr/step05_...)
- **wait 失败快照** (若适用):
  - [wait_claim_all_rewards_fail_check1.png](../wait_failure/wait_claim_all_rewards_fail_check1.png)
  - [wait_claim_all_rewards_fail_check2.png](../wait_failure/wait_claim_all_rewards_fail_check2.png)
  - [wait_claim_all_rewards_fail_check3.png](../wait_failure/wait_claim_all_rewards_fail_check3.png)
```

**实现位置**: 新增 `agent/src/utils/timeline_generator.py`，在 [orchestrator.py](file:///d:/code/GAF/agent/src/core/orchestrator.py#L982) `execute_pipeline` 结束时调用

**数据来源**: 
- StructuredLogger 的 JSONL 文件（读所有事件）
- 调试图目录扫描（建立 文件名→路径 映射）

### 3.4 诊断报告 diagnosis.md

**问题**: AI 需要手写脚本才能诊断（如我前面写的 `bd2_verify_dpi_fix.py`）。

**方案**: 任务结束时自动生成 `diagnosis.md`，含失败原因分类 + 异常指标 + 诊断提示。

**输出路径**: `<debug_dir>/structured/<execution_id>_diagnosis.md`

**内容格式**:
```markdown
# 诊断报告: get_email (exec-abc123def456)

- **执行 ID**: exec-abc123def456
- **状态**: FAIL
- **失败节点**: claim_all_rewards (step 05)
- **失败时间**: +5.950s (执行开始后)

## 失败原因分类

### claim_all_rewards (ocr) — OCR 未识别到文本
- **期望文本**: 全部领取
- **实际识别**: 0 行文本
- **可能原因**:
  1. UI 未出现 — 上游 wait_regular_email 虽然成功，但可能识别到错误的「普通邮箱」文本
  2. ROI 越界 — roi=[1573,969,252,61] 在 1540x866 截图中可能越界（检查 base_resolution 配置）
  3. OCR 引擎问题 — rapidocr 可能不支持当前 UI 字体

## 异常指标

| Step | Node | 指标 | 值 | 阈值 | 状态 |
|------|------|------|-----|------|------|
| 01 | open_mailbox | score | 0.9592 | 0.80 | ✅ 正常 |
| 03 | detect_empty_email | score | 0.8800 | 0.80 | ✅ 正常（接近阈值，建议关注） |
| 05 | claim_all_rewards | ocr_lines | 0 | — | ❌ 异常 |

## 诊断提示

### 提示 1: detect_empty_email score 接近阈值 (0.88 vs 0.80)
- **风险**: 该节点可能在其他场景下误判
- **建议**: 检查模板 `空邮箱标识.png` 是否清晰，或提高 threshold 到 0.85

### 提示 2: claim_all_rewards OCR 未识别到文本
- **检查清单**:
  - [ ] UI 是否真的出现了「全部领取」按钮？
  - [ ] ROI [1573,969,252,61] 在当前截图分辨率下是否正确？
  - [ ] OCR 引擎是否正常工作（查看 step05 调试图）？
  - [ ] 是否需要截图时 DPI 归一化（base_resolution=1920x1080 vs 截图分辨率）？
```

**实现位置**: 新增 `agent/src/utils/diagnosis_generator.py`，在 orchestrator 结束时调用

**诊断规则引擎**:
- score 接近阈值（margin < 0.05）→ 提示风险
- score 远低于阈值（margin > 0.3）→ 提示 DPI/模板问题
- OCR 0 行文本 → 提示 UI 未出现/ROI 越界/引擎问题
- wait 超时 → 提示查看 wait_failure 快照
- 模板加载失败 → 提示路径问题

### 3.5 调试目录按执行 ID 归档

**问题**: 调试图分散在 `template_match/`、`ocr/`、`action/`、`structured/`、`wait_failure/` 五个目录。

**方案**: 每次执行独立目录，所有调试产物归档在 `<debug_dir>/<execution_id>/` 下。

**新目录结构**:
```
debug/agent/
  exec-abc123def456/                  # 一次执行一个目录
    template_match/
      step01_template_match_success_open_mailbox_exec-abc123_143025123.png
      step03_template_match_success_detect_empty_email_exec-abc123_143025130.png
    ocr/
      step05_ocr_fail_claim_all_rewards_exec-abc123_143025135.png
    action/
      step02_wait_success_wait_regular_email_exec-abc123_143025128.png
      step06_key_press_success_exit_mailbox_exec-abc123_143025140.png
    wait_failure/
      step05_wait_claim_all_rewards_fail_check1_exec-abc123_143025134.png
      step05_wait_claim_all_rewards_fail_check2_exec-abc123_143025135.png
      step05_wait_claim_all_rewards_fail_check3_exec-abc123_143025136.png
    structured/
      exec-abc123def456.jsonl         # 结构化日志
      exec-abc123def456_timeline.md   # 时间线索引
      exec-abc123def456_diagnosis.md  # 诊断报告
      exec-abc123def456_score_curve.png  # 匹配分数曲线
    pipeline.log                      # 人类可读文本日志
```

**实现位置**: 
- [orchestrator.py](file:///d:/code/GAF/agent/src/core/orchestrator.py#L785) `effective_debug_dir` 改为 `<debug_dir>/<execution_id>/`
- 所有 `DebugImageSaver(debug_dir=...)` 调用方改用 `effective_debug_dir + 子目录`
- StructuredLogger 的 `get_logger(execution_id, debug_dir)` 改为 `debug_dir=<debug_dir>/<execution_id>/structured/`

**向后兼容**: 旧路径 `<debug_dir>/template_match/` 等仍可用（不强制归档），但新路径优先

**清理便利**: 按 execution_id 目录删除，`rm -rf debug/agent/exec-abc123*` 清理一次执行的所有产物

### 3.6 匹配分数曲线 score_curve.png

**问题**: 潜在风险点（score 接近阈值）不直观。

**方案**: 任务结束生成 `score_curve.png`，横轴步骤序号，纵轴 score，红线标注 threshold。

**输出路径**: `<debug_dir>/<execution_id>/structured/<execution_id>_score_curve.png`

**实现**: 用 matplotlib（agent 依赖已有）或 OpenCV 绘制（避免新依赖）

**内容**:
- 横轴: step_index
- 纵轴: confidence (0.0-1.0)
- 红线: 各节点的 threshold
- 绿点: 成功节点
- 红点: 失败节点
- 黄点: score 接近阈值（margin < 0.05）

## 4. 数据流

```
execute_pipeline 开始
    ↓
生成 execution_id = exec-<uuid12>
    ↓
effective_debug_dir = <debug_dir>/<execution_id>/
    ↓
engine.load(debug_dir=effective_debug_dir)
    ↓
StructuredLogger 写 <execution_id>/structured/<execution_id>.jsonl
    ↓
各节点执行:
    template_match → DebugImageSaver 写 <execution_id>/template_match/stepNN_...png
    ocr → DebugImageSaver 写 <execution_id>/ocr/stepNN_...png
    wait → DebugImageSaver 写 <execution_id>/action/stepNN_...png
    wait 超时 → 额外写 <execution_id>/wait_failure/stepNN_...check{1,2,3}.png
    click/swipe/key_press → DebugImageSaver 写 <execution_id>/action/stepNN_...png
    ↓
execute_pipeline 结束
    ↓
TimelineGenerator 读 JSONL → 生成 <execution_id>_timeline.md
DiagnosisGenerator 读 JSONL + 调试图 → 生成 <execution_id>_diagnosis.md
ScoreCurveGenerator 读 JSONL → 生成 <execution_id>_score_curve.png
    ↓
result.structured_log_path = <execution_id>/structured/<execution_id>.jsonl
result.timeline_path = <execution_id>/structured/<execution_id>_timeline.md
result.diagnosis_path = <execution_id>/structured/<execution_id>_diagnosis.md
result.score_curve_path = <execution_id>/structured/<execution_id>_score_curve.png
```

## 5. 涉及文件

### 新增

| 文件 | 作用 |
|------|------|
| `agent/src/utils/timeline_generator.py` | 读 JSONL 生成 timeline.md |
| `agent/src/utils/diagnosis_generator.py` | 读 JSONL + 调试图生成 diagnosis.md |
| `agent/src/utils/score_curve_generator.py` | 读 JSONL 生成 score_curve.png |

### 修改

| 文件 | 改动 |
|------|------|
| [wait.py](file:///d:/code/GAF/agent/src/engine/nodes/wait.py) | `_wait_template`/`_wait_disappear`/`_wait_ocr` 失败时保存最后 3 次 check 截图到 `wait_failure/`；每次 check 记录 `wait.check.fail` JSONL 事件 |
| [debug_image_saver.py](file:///d:/code/GAF/agent/src/utils/debug_image_saver.py) | `save_template_debug`/`save_ocr_debug`/`save_action_debug` 签名新增 `step_index` + `execution_id` 可选参数，文件名格式改为 `step{NN}_{node_type}_{status}_{node_id}_{exec_id}_{ts}.png` |
| [template_match.py](file:///d:/code/GAF/agent/src/engine/nodes/template_match.py) | `_save_debug` 调用传入 `step_index` + `execution_id` |
| [ocr.py](file:///d:/code/GAF/agent/src/engine/nodes/ocr.py) | 同上 |
| [click.py](file:///d:/code/GAF/agent/src/engine/nodes/click.py) | 同上 |
| [swipe.py](file:///d:/code/GAF/agent/src/engine/nodes/swipe.py) | 同上 |
| [key_press.py](file:///d:/code/GAF/agent/src/engine/nodes/key_press.py) | 同上 |
| [orchestrator.py](file:///d:/code/GAF/agent/src/core/orchestrator.py) | `effective_debug_dir` 改为 `<debug_dir>/<execution_id>/`；结束时调用 TimelineGenerator + DiagnosisGenerator + ScoreCurveGenerator；result 新增 timeline_path/diagnosis_path/score_curve_path |
| [structured_logger.py](file:///d:/code/GAF/agent/src/utils/structured_logger.py) | `get_logger` 的 `debug_dir` 参数支持新归档路径；新增 `log_wait_check_fail` 便捷方法 |

## 6. 验收标准

1. **wait 失败有快照**: wait 超时后，`wait_failure/` 目录有最后 3 次 check 的标注截图，每张含模板/score/threshold/ROI
2. **调试图文件名含步骤序号**: 文件名格式 `step{NN}_{node_type}_{status}_{node_id}_{exec_id}_{ts}.png`，按文件名排序可还原执行顺序
3. **timeline.md 自动生成**: 每次执行后 `<execution_id>/structured/<execution_id>_timeline.md` 存在，含所有节点的表格 + 失败节点详情 + wait 快照链接
4. **diagnosis.md 自动生成**: 每次执行后 `<execution_id>/structured/<execution_id>_diagnosis.md` 存在，含失败原因分类 + 异常指标 + 诊断提示
5. **score_curve.png 自动生成**: 每次执行后 `<execution_id>/structured/<execution_id>_score_curve.png` 存在，横轴步骤序号，纵轴 score，红线 threshold
6. **调试目录按执行 ID 归档**: 所有调试产物在 `<debug_dir>/<execution_id>/` 下，清理时按目录删除
7. **AI 可读性**: AI 读取 timeline.md + diagnosis.md 即可定位问题，不需要手写诊断脚本
8. **向后兼容**: step_index/execution_id 缺省时用旧文件名格式；旧调用路径仍可用
9. **零开销**: 调试模式 OFF 时不生成任何文件

## 7. 实施顺序

1. **Phase 1: wait 失败快照**（解决最痛点）
   - 修改 wait.py 三个 `_wait_*` 方法
   - 新增 `wait.check.fail` JSONL 事件
   - 验收: wait 超时后 `wait_failure/` 有 3 张标注截图

2. **Phase 2: 文件名加步骤序号**
   - 修改 debug_image_saver.py 签名
   - 修改所有节点 `_save_debug` 调用
   - 验收: 文件名含 `stepNN` + `exec_id`

3. **Phase 3: 调试目录归档**
   - 修改 orchestrator.py `effective_debug_dir`
   - 修改 StructuredLogger 路径
   - 验收: 所有产物在 `<execution_id>/` 下

4. **Phase 4: timeline.md**
   - 新增 timeline_generator.py
   - 在 orchestrator 结束时调用
   - 验收: timeline.md 含表格 + 失败详情

5. **Phase 5: diagnosis.md**
   - 新增 diagnosis_generator.py
   - 实现诊断规则引擎
   - 验收: diagnosis.md 含失败原因 + 异常指标 + 诊断提示

6. **Phase 6: score_curve.png**
   - 新增 score_curve_generator.py
   - 用 OpenCV 绘制（避免 matplotlib 依赖）
   - 验收: score_curve.png 含步骤/score/threshold

## 8. 与现有文档的关系

- [debug-mode-design.md](debug-mode-design.md)（2026-07-12）: 基础调试模式架构（AgentConfig.debug_mode + DebugImageSaver + 前端开关）
- 本文档: 在基础架构上的时间链路增强（wait 快照 + 文件名 + timeline + diagnosis + 归档 + score_curve）
- 不替代 debug-mode-design.md，是其演进版本
