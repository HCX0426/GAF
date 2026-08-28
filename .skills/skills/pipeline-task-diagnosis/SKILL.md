---
name: pipeline-task-diagnosis
description: Use when a pipeline node execution fails, times out, or behaves unexpectedly — OCR/timeout/coordinate/screenshot/screenshot-related issues during pipeline execution. Not for general debugging or test failures.
version: "2.2.0"
license: MIT
load_when:
  - task_type == bug_fix AND (symptom 涉及 pipeline 节点执行 / OCR 超时 / 模板匹配失败 / 坐标偏移)
  - 对话中出现任务失败关键词（失败 / 超时 / 报错 / 识别不到 / 没反应 / NODE_TIMEOUT / TEMPLATE_NOT_FOUND）
  - 日志中出现 pipeline 错误码（NODE_TIMEOUT / TEMPLATE_NOT_FOUND / OCR_LOW_CONFIDENCE）
metadata:
  hermes:
    tags: [pipeline, diagnosis, ocr, timeout, node, popup]
---

# Pipeline 节点任务诊断

## 概述

节点执行失败 ≠ 代码 bug。多数情况是**配置问题**（ROI 偏移、分辨率不匹配、截图方法不对）或**数据流断裂**（coord_transformer 缺失、预期文本与 ROI 区域不重叠）。此外，**弹窗遮挡**是高频被忽视的失败原因。

## 核心原则

1. **主动触发** — AI 在对话中检测到失败关键词或异常模式时，必须主动加载诊断流程
2. **弹窗优先** — 上一节点成功但当前节点失败时，必须先检查弹窗遮挡
3. **从当前步骤续跑，不从头重来** — 调试时跳过已验证的节点，直接从失败节点开始
4. **先隔离节点，再缩小范围，最后验证修复** — 配置问题 > 数据流问题 > 弹窗遮挡 > 代码问题
5. **诊断脚本写 debug 目录要规范** — 见下方目录规范
6. **拿不定时先试，试完无法推进再问用户**

## 触发机制

### 主动触发（AI 自动检测）

即使用户没有明确指出哪个任务错误，AI 也必须在以下模式下主动加载诊断：

| 触发模式 | 示例 | 行动 |
|----------|------|------|
| 对话中提到失败关键词 | "失败"、"超时"、"报错"、"识别不到" | 主动加载本 Skill |
| 日志中出现错误信息 | agent 日志显示 NODE_TIMEOUT、TEMPLATE_NOT_FOUND | 主动分析根因 |
| 截图显示异常画面 | 截图中有弹窗遮挡、界面未切换 | 主动检查弹窗问题 |
| 用户描述"没反应"、"没变化" | 暗示点击/操作未生效 | 主动检查上一节点 |

### 弹窗遮挡触发

**触发条件**（满足以下所有条件时，立即执行弹窗检测）：
- 上一节点报告成功（如 `click_on_match: success`）
- 当前节点持续失败（如 OCR 多次全部乱码）
- 截图显示画面异常（有弹窗/遮罩/未预期的界面元素）

## 日志路径速查

诊断前必须先读日志，了解错误上下文。日志按日期分桶存放：

```
debug/YYYYMMDD/
├── agent/system/
│   └── agent.log                   # Agent 系统日志 (设备发现、心跳、WebSocket 状态)
├── backend/system/
│   ├── daemon.log                  # Daemon 日志 (服务状态、重启、端口探测)
│   └── HH/django.log               # Django 应用日志 (API 请求、序列化、业务异常)
├── <pipeline>/<HHMMSS>_<suffix>/
│   ├── run.log                     # 任务执行日志 (FileLogHandler, 每次执行一个目录)
│   ├── structured.jsonl            # Agent 结构化日志镜像
│   └── screenshots/{annotated,raw}/ # 本次执行的截图
├── backend/tasks/<pipeline>/HH/
│   └── execution.jsonl             # 任务结构化日志 (BackendTaskLogger, JSON 格式)
├── agent/<pipeline>/HH/
│   └── structured.jsonl            # Agent 结构化执行日志（主副本）
├── frontend/<page>/HH/
│   └── console.jsonl               # 前端控制台日志
├── archives/YYYYMMDD/              # 历史归档 (tar.gz)
└── gaf_daemon.pid                  # Daemon 单例 PID
```

> **说明**: `<HHMMSS>_<suffix>` 由 `build_execution_debug_dir` 生成，`suffix` 是 execution_id 后 8 字符。
> 例: `debug/20260809/get_email/143022_a1b2c3d4/run.log`
> `run.log` 是 FileLogHandler 在有 execution_id 时的写入路径（每次执行独立目录）；
> `execution.jsonl` 是 BackendTaskLogger 的结构化日志（按 pipeline+小时分桶）；
> 两者互补：`run.log` 是人类可读的文本日志，`execution.jsonl` 是结构化 JSON。

**读取策略**（按节点失败场景选择）：

| 失败类型 | 优先读的日志 | 关键字过滤 |
|----------|-------------|-----------|
| OCR 超时 / 节点失败 | `agent.log` + `run.log` + `django.log` | `NODE_TIMEOUT` / `OCR` / `trace_id` / `node_execute` |
| 模板匹配失败 | `agent.log` + `run.log` | `TEMPLATE_NOT_FOUND` / `template_match` |
| 点击未生效 | `agent.log` + `run.log` + `django.log` | `click_on_match` / `dispatch` / `node_complete` |
| 后端调度问题 | `django.log` + `daemon.log` + `execution.jsonl` | `dispatch_task` / `Celery` / `retry_pending` / `task_started` |
| WebSocket 断连 | `agent.log` + `django.log` | `connection` / `disconnect` / `heartbeat` / `register` |
| 服务重启 | `daemon.log` | `restart` / `watchdog` / `进程已退出` / `端口检测` |
| 任务执行全链路 | `execution.jsonl` + `structured.jsonl` + `run.log` | `trace_id` / `execution_id` 串联三端 |

## 诊断流程

```
节点失败/超时
    │
    ├─ ⓪ 读日志（★ 必须首先执行）
    │   ├─ 读系统级日志
    │   │   ├─ agent.log (debug/YYYYMMDD/agent/system/agent.log)
    │   │   │   过滤: NODE_TIMEOUT / TEMPLATE_NOT_FOUND / ERROR / trace_id
    │   │   ├─ django.log (debug/YYYYMMDD/backend/system/HH/django.log)
    │   │   │   过滤: ERROR / Exception / dispatch_task / 对应的 trace_id
    │   │   └─ daemon.log (debug/YYYYMMDD/backend/system/daemon.log)
    │   │       过滤: restart / 进程已退出 / WARNING
    │   ├─ 读任务级日志（根据 pipeline 名 + 时间 + suffix 定位）
    │   │   ├─ run.log (debug/YYYYMMDD/<pipeline>/<HHMMSS>_<suffix>/run.log)
    │   │   │   过滤: node_execute / node_complete / ERROR / 失败节点名
    │   │   └─ execution.jsonl (debug/YYYYMMDD/backend/tasks/<pipeline>/HH/execution.jsonl)
    │   │       过滤: task_started / node_completed / task_failed
    │   └─ 汇总错误: 定位失败节点 + 错误码 + 时间戳 + trace_id + execution_id
    │
    ├─ ① 隔离节点
    │   └─ 写独立脚本绕过 pipeline 直接跑该节点逻辑
    │       └─ 成功? → 配置/数据流问题 → ②
    │       └─ 失败? → 引擎/依赖问题 → 修代码
    │
    ├─ ② 验输入
    │   ├─ 截图: 全窗口截图看画面是否正确
    │   ├─ 分辨率: 截图尺寸 vs pipeline 基准分辨率 (1920x1080)
    │   └─ 引擎: OCR/模板匹配 是否能独立工作
    │
    ├─ ③ 弹窗遮挡检测（★ 高频失败场景）
    │   ├─ 截图并检查画面: 截取当前游戏画面
    │   ├─ 检查是否有弹窗: 用弹窗模板匹配
    │   │   - 关闭按钮 (×): 通常在弹窗右上角
    │   │   - 弹窗背景框: 中间的半透明/不透明弹窗区域
    │   │   - 跳过/确认按钮: 弹窗内的操作按钮
    │   ├─ 检查画面是否符合预期: 界面是否已切换到目标页面?
    │   └─ 如检测到弹窗:
    │       ├─ 点击右上角 × 关闭弹窗 (或点击跳过/确认按钮)
    │       ├─ 重新截取画面验证
    │       └─ 重新验证当前节点
    │
    ├─ ④ 同 ROI 模板降级匹配（★ 关键诊断策略）
    │   ├─ 读取 roi-template-mapping.md 获取 ROI→模板组映射
    │   ├─ 查找当前节点使用的模板所属 ROI
    │   ├─ 获取同 ROI 的所有模板
    │   ├─ 依次尝试匹配（主模板优先）
    │   │   ├─ 匹配成功 → 使用该模板
    │   │   └─ 全部失败 → 继续下一步
    │   └─ 记录降级匹配结果
    │
    └─ ⑤ 验配置
        ├─ ROI: 坐标是否覆盖目标区域? (常见: y 值偏低裁掉文本)
        ├─ coord_transformer: 有/无 缩放差异?
        ├─ timeout: 是否足够? (OCR 首次初始化 ~3.4s，建议 >= 15s)
        ├─ mode/type: 节点类型是否匹配预期行为?
        ├─ screenshot_method: 对比所有截图方法置信度 (GDI/PrintWindow/DXGI/WGC)
        └─ continue_on_error: 是否需要允许节点失败后继续执行?
```

## 调试目录规范

诊断脚本产生的截图和日志必须写入规范路径，避免污染 `debug/` 顶层：

```
debug/YYYYMMDD/diag_<method>/
  ├─ screenshots/
  │   ├─ annotated/    # 标注后的截图 (PNG)
  │   └─ raw/          # 原始截图 (JPG)
  └─ result.json       # 诊断结果 (可选)
```

示例：`debug/20260731/diag_printwindow/screenshots/annotated/215738928_diag_printwindow_match_fail.png`

**禁止**：
- ❌ 直接写 `debug/screenshots/`、`debug/diag_gdi/`（无日期分桶，污染顶层）
- ❌ 直接写 `debug/agent/screenshots/`（agent 旧格式，无日期分桶）
- ✅ 写 `debug/YYYYMMDD/diag_<method>/screenshots/`

## 常见错误模式

| 症状 | 根因 | 诊断方法 |
|------|------|---------|
| OCR 超时但引擎正常 | ROI 裁剪掉了目标文本 | 全图 OCR vs ROI 裁剪 OCR 对比 |
| 模板匹配失败 | 分辨率不匹配，模板在缩放后失真 | 截全图对比 base_res 与实际尺寸 |
| 点击位置错误 | coord_transformer 缺失，子图坐标当全图坐标用 | 检查 publish_match_pos 的坐标来源 |
| 节点返回空截图 | 截图方法不对（PrintWindow 返回黑屏） | 换截图方法对比 |
| 坐标偏移 | ROI 子图坐标未加 ROI 原点偏移 | 检查 sub_image_to_full 调用链 |
| OCR 超时（引擎初始化慢） | OCR 引擎首次初始化耗时 ~3.4s，timeout 不够 | 设置 timeout >= 15s，或预初始化引擎 |
| 同节点不同截图方法置信度差异大 | GDI 0.17 vs PrintWindow 0.94，auto-heal 未触发 | 用 `_debug_capture.py` 对比所有截图方法的置信度 |
| 子流程节点执行异常 | coord_transformer 未从父流程传递到子流程 | 检查 sub_pipeline.py 中 `getattr(context, "coord_transformer")` 而非 `transformer` |
| 单节点失败终止整个 pipeline | 缺少 `continue_on_error: true` 配置 | 在节点 config 中添加 `continue_on_error: true` |
| ★ 上一节点成功，当前节点 OCR 全乱码 | **弹窗遮挡目标区域** | 截全图检查弹窗模板（×关闭按钮、弹窗背景框、跳过按钮），点击 × 关闭弹窗 |
| ★ 点击成功但界面没变化 | **弹窗拦截了点击事件** | 检查是否有弹窗覆盖在点击目标上方 |
| 界面跳转后节点仍失败 | **弹窗需要先关闭才能看到目标** | 在点击节点后添加 wait_dismiss_popup 节点，检测并关闭弹窗 |
| ★ 模板匹配失败但 ROI 正确 | **同 ROI 的其他模板可用** | 查 roi-template-mapping.md，尝试同 ROI 的其他模板降级匹配 |
| ★ 界面状态不确定（激活/禁用） | **组件有多种状态模板** | 用同 ROI 的多个模板分别匹配，选择置信度最高的 |

## 快速诊断脚本

> **2026-08-09 更新**: 以下脚本已创建在 `agent/debug/` 目录，可直接使用。

### 脚本列表

| 脚本 | 用途 | 用法 |
|------|------|------|
| `_diag_node.py` | 节点隔离测试 | `python agent/debug/_diag_node.py --node-id wait_regular_email --pipeline tasks/get_email.json` |
| `_diag_ocr.py` | OCR 诊断 | `python agent/debug/_diag_ocr.py --text "普通邮箱" --roi "[214,10,333,276]" --compare-full` |
| `_diag_template.py` | 模板匹配诊断 | `python agent/debug/_diag_template.py --template "邮箱.png" --roi "[1564,28,95,61]"` |
| `_diag_popup.py` | 弹窗检测 | `python agent/debug/_diag_popup.py --popup-templates "关闭按钮.png,跳过.png"` |
| `_diag_template_fallback.py` | 同 ROI 降级匹配 | `python agent/debug/_diag_template_fallback.py --primary-template "邮箱.png" --roi "[1564,28,95,61]" --mapping roi-template-mapping.md` |
| `_diag_full.py` | 完整诊断 (Level 1-3) | `python agent/debug/_diag_full.py --pipeline get_email --node wait_regular_email --level 2` |

### 使用示例

```bash
# 1. 节点隔离测试
conda run -n gaf python agent/debug/_diag_node.py \
    --node-id wait_regular_email \
    --pipeline "resources/BrownDust II/tasks/get_email.json" \
    --save-screenshots

# 2. OCR 验证 (对比全图 vs ROI 裁剪)
conda run -n gaf python agent/debug/_diag_ocr.py \
    --text "普通邮箱" \
    --roi "[214,10,333,276]" \
    --compare-full

# 3. 模板匹配验证 (对比不同截图方法)
conda run -n gaf python agent/debug/_diag_template.py \
    --template "templates/get_email/邮箱.png" \
    --roi "[1564,28,95,61]" \
    --threshold 0.8

# 4. 弹窗检测 (检查中间弹窗框 + 右上角 ×)
conda run -n gaf python agent/debug/_diag_popup.py \
    --popup-templates "templates/public/关闭按钮.png,templates/public/跳过.png" \
    --roi "[600, 200, 720, 680]"  # 屏幕中央区域

# 5. 同 ROI 降级匹配 (关键诊断策略)
conda run -n gaf python agent/debug/_diag_template_fallback.py \
    --primary-template "templates/get_email/邮箱.png" \
    --roi "[1564,28,95,61]" \
    --mapping "resources/BrownDust II/docs/roi-template-mapping.md"

# 6. 完整诊断 (推荐)
conda run -n gaf python agent/debug/_diag_full.py \
    --pipeline get_email \
    --node wait_regular_email \
    --level 2
```

## 关键约束

- **主动触发诊断** — 对话中检测到失败关键词时，必须主动加载本 Skill，不要等用户明确要求
- **弹窗优先检查** — 上一节点成功但当前节点失败时，必须先检查弹窗遮挡，再检查配置
- **同 ROI 模板降级** — 模板匹配失败时，必须尝试同 ROI 的其他模板（读取 roi-template-mapping.md）
- **不要只改代码** — 先验证配置、截图、数据流，确认是代码问题再改
- **不要跳过 coord_transformer 检查** — 有/无 transformer 时 ROI 行为不同，是常见坑
- **不要忽略分辨率** — pipeline 基准分辨率 1920x1080，实际窗口可能不同
- **不要相信默认值** — 验证 timeout、check_interval、threshold 等参数是否合理
- **OCR timeout 必须包含引擎初始化时间** — RapidOCR 首次 ~3.4s，建议 timeout >= 15s
- **截图方法影响模板匹配置信度** — PrintWindow 在 BD2 上表现最好（0.94），GDI 最差（0.17）
- **子流程必须传递 coord_transformer** — sub_pipeline.py 中从 context 获取 `coord_transformer` 而非 `transformer`
- **单节点失败不一定要终止 pipeline** — 用 `continue_on_error: true` 允许跳过失败节点继续执行
- **从当前步骤续跑** — 调试时跳过已验证节点，直接从失败节点开始，不从头重来

### 弹窗检测伪代码

```python
# 弹窗检测流程 (弹窗特征: 中间框 + 右上角 ×)
def check_popup_obstruction(screen, pipeline_config):
    """检查是否有弹窗遮挡目标区域"""
    # 1. 检查弹窗关闭按钮 (×, 通常在弹窗右上角)
    popup_templates = get_popup_close_templates(pipeline_config)  # ×关闭按钮、跳过按钮、确认按钮
    
    for template in popup_templates:
        match = template_match(screen, template, threshold=0.7)
        if match.success:
            logger.warning(f"⚠️ 检测到弹窗! 匹配到关闭按钮 [{template.name}]")
            # 点击 × 关闭弹窗 (不是点击返回键)
            click_position(match.x + match.w/2, match.y + match.h/2)
            return True, match
    
    # 2. 检查弹窗背景框 (中间区域的半透明/不透明区域)
    popup_region = detect_center_popup_region(screen)  # 检测屏幕中央的弹窗框
    if popup_region:
        logger.warning("⚠️ 检测到中间弹窗框!")
        # 查找弹窗右上角的 × 按钮
        close_btn = find_close_button_in_region(popup_region)
        if close_btn:
            click_position(close_btn.x, close_btn.y)
        return True, popup_region
    
    # 3. 检查界面是否异常
    expected_state = get_expected_state(pipeline_config)
    if not screen_matches_expected(screen, expected_state):
        logger.warning("⚠️ 界面状态与预期不符，可能有遮挡")
        return True, None
    
    return False, None
```

### 同 ROI 模板降级匹配伪代码

```python
# 核心发现: 相同 ROI 的模板对应同一组件的不同状态
# 如: 邮箱按钮的 [默认, 高亮, 禁用] 三种状态

def template_fallback_match(screen, roi, primary_template, mapping_doc):
    """同 ROI 模板降级匹配"""
    # 1. 从映射表获取同 ROI 的模板列表
    templates = get_templates_for_roi(mapping_doc, roi)
    
    # 2. 主模板优先，其他模板按名称相似度排序
    sorted_templates = prioritize(primary_template, templates)
    
    # 3. 依次尝试匹配
    for template_path in sorted_templates:
        result = template_match(screen, template_path, roi=roi, threshold=0.7)
        if result.success:
            logger.info(f"🎯 降级匹配成功: {template_path} (confidence={result.confidence:.3f})")
            return result
    
    logger.warning("所有同 ROI 模板匹配失败")
    return None
```

## 游戏资源标准结构

> **归一化状态（2026-08-09 已完成）**: `tasks/` 成为唯一数据源，`pipelines/` 已移除。
> 
> **读写一致性**:
> - **读取**: 只读 `tasks/` ✅
> - **写入**: 只写 `tasks/` ✅ ([import_utils.py](file:///d:/code/GAF/backend/resources/import_utils.py))
> - **计数**: 只数 `tasks/` ✅ ([serializers.py](file:///d:/code/GAF/backend/resources/serializers.py))
> 
> **详细规范**: 见 [docs/specs/archived/2026-08/2026-08-09-pipeline-task-diagnosis-spec.md](file:///d:/code/GAF/docs/specs/archived/2026-08/2026-08-09-pipeline-task-diagnosis-spec.md)

### 当前目录结构（已归一化）

```
resources/<game>/
  ├── config/           # 配置文件
  ├── monitors/         # 监控器配置
  ├── tasks/            # ✅ 唯一数据源（读写统一）
  ├── templates/        # 模板图像
  └── manifest.json     # 任务清单
```

### 诊断时的注意事项

1. **任务定义读取**: 只从 `tasks/*.json` 读取
2. **写入路径**: 统一写入 `tasks/`
3. **必需文档**: `docs/task-reference.md` 和 `docs/roi-template-mapping.md`

### 必需文档

1. **`docs/task-reference.md`（界面导航图）**
   - 作用：记录每个任务的入口界面、出口界面、界面跳转路径
   - 重要性：没有它，AI 无法判断"任务是否成功执行"
   
2. **`docs/roi-template-mapping.md`（ROI-模板组映射）**
   - 作用：记录相同 ROI 的模板组关系，用于模板降级匹配
   - 重要性：模板匹配失败时，可快速找到同 ROI 的替代模板

3. **`docs/bd2-troubleshooting.md`（故障排查指南）**
   - 作用：快速排查流程、高频故障场景、各任务常见问题
   - 重要性：遇到具体任务失败时的首选排查文档

### 弹窗模板（必须）

弹窗特征：**中间弹窗框 + 右上角 × 关闭按钮**

**现有模板**:
- `templates/public/跳过.png` — 弹窗内的跳过按钮

**需要添加的模板**:
- `templates/public/关闭按钮.png` — 弹窗右上角的 × 关闭按钮（用于关闭中间弹窗）

**说明**: 
- 弹窗通常在屏幕中央（ROI 建议 `[600, 200, 720, 680]`）
- 关闭按钮在弹窗右上角，点击 × 即可关闭弹窗
- 添加模板方法：截取弹窗关闭按钮的截图，保存为 `关闭按钮.png` 到 `templates/public/`

### 快速参考路径

| 游戏 | task-reference.md | roi-template-mapping.md | troubleshooting.md |
|------|-------------------|------------------------|---------------------|
| BrownDust II | `resources/BrownDust II/docs/task-reference.md` | `resources/BrownDust II/docs/roi-template-mapping.md` | `resources/BrownDust II/docs/bd2-troubleshooting.md` |
| GAF Default | `resources/GAF Default/docs/task-reference.md` | `resources/GAF Default/docs/roi-template-mapping.md` | — |

## BD2 诊断上下文

BD2 任务诊断时，以下信息对快速定位问题至关重要：

### BD2 特有参考

- **坐标系统**: `.ai-memory/games/browndust-ii/coordinate-system.md`
- **常见任务速查**: `.ai-memory/games/browndust-ii/common-tasks.md`

### BD2 已知关键参数

| 参数 | 值 | 说明 |
|------|-----|------|
| 基准分辨率 | 1920×1080 | 所有 pipeline 的 ROI 基于此设计 |
| 实际窗口 | ~1540×866 | 物理像素，DPI 缩放 ~150% |
| 最佳截图方法 | PrintWindow | 置信度 0.94+，GDI 仅 0.17 |
| OCR 首次初始化 | ~3.4s | timeout 建议 >= 15s |
| 公共子流程 | `back_to_main.json` | 返回键 → ESC 降级返回主界面 |

### BD2 常见失败模式

| 症状 | 根因 | 快速排查 |
|------|------|----------|
| 模板匹配置信度低 | 截图方法不对 | 对比 GDI vs PrintWindow 置信度 |
| OCR 识别不到文本 | ROI 偏了 | 全图 OCR 定位文本实际位置，修正 ROI |
| 返回主界面失败 | 子流程 coord_transformer 未传递 | 检查 `sub_pipeline.py` 中 `getattr(context, "coord_transformer")` |
| 单节点失败终止 pipeline | 缺少 `continue_on_error: true` | 在节点 config 中添加 |

## 自我进化（AI 必读）

> 本技能必须持续更新。每次你用本技能诊断后，如果现有方法不够用或发现了新模式，**必须立即更新本文件**。

### 触发更新条件（任一即触发）

1. 诊断过程中发现**现有「诊断流程」或「常见错误模式」表未覆盖的新根因**
2. 诊断过程中用了**新的工具/脚本/命令**，之前未记录在「快速诊断脚本模板」中
3. 诊断过程中发现**现有方法找不出问题**，最后用不同思路才定位到
4. 修复后发现**更好的诊断方法**（更快、更准、更通用）

### 更新方式

找到对应章节追加，若无对应章节则新增：
- **新根因 → 追加到「常见错误模式」表**（症状/根因/诊断方法 三列）
- **新步骤 → 追加到「诊断流程」树**（保持缩进风格）
- **新脚本/命令 → 追加到「快速诊断脚本模板」**（注释说明场景）
- **新约束 → 追加到「关键约束」**（用 `- **` 列表格式）

### 更新示例

```markdown
# 新增错误模式示例
| 症状 | 根因 | 诊断方法 |
|------|------|---------|
| xxx | xxxx | xxxx |

# 新增诊断步骤示例
# 在「诊断流程」的③验配置下追加
        ├─ 引擎版本: OCR 引擎版本是否过旧导致识别率低?
```

### 不更新就是违规

- ❌ "这次问题特殊，不值得更新" → 问题没有"特殊"到不可复用
- ❌ "下次再补" → 下次对话没有本技能上下文，记不住
- ❌ "只加在自己笔记里" → 必须更新本文件，否则团队/AI 都学不到
- ✅ 每次诊断完，自然语言追加到对应章节，30 秒的事