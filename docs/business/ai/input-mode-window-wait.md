---
summary: 输入模式测试 + 窗口后台等待功能设计 — BD2 get_mailbox 点击不生效问题修复方案
applies_to: [agent, design]
last_updated: 2026-07-12
---

# Input Mode Testing & Window-Background-Wait Feature Design

> **Status**: Approved (2026-07-12)
> **Author**: AI + User brainstorming
> **Related**: `debug-mode-design.md`, `template-match-debug-visualization.md`

## Background

BD2 `get_email` pipeline 测试中发现 `open_mailbox` 节点模板匹配成功 (confidence=0.9590) 并点击 (857,30)，但邮箱未打开。调试模式已修复 (commit `-`) 并生成调试图片，确认点击坐标正确但未生效。

根因调查发现：
1. BD2 (UnityWndClass) 实际走 `SendInput` 纯前台模式（经 `_resolve_auto_input_method` 从 PseudoBackground 切换）
2. `SendInput` 模式不自动前台化窗口，BD2 不在前台时点击落到错误窗口
3. `PseudoBackground` 模式存在但 `SetForegroundWindow` 未用 AttachThreadInput，跨进程前台化可能失败
4. 缺乏"窗口后台时暂停任务"机制，任务在窗口后台时静默失败

用户需求：
- 测试前台模式 (SendInput) 和伪后台模式 (PseudoBackground)
- 新功能：前台模式时，窗口被置后台则任务暂停，恢复前台后继续
- 写 DPI/坐标系文档和任务执行排查步骤文档
- 解决调查中发现的技术债务

## Stage 1: Fix PseudoBackground + Test Input Modes

### 1.1 Fix PseudoBackground AttachThreadInput

**Problem**: `agent/src/platforms/windows/input.py:469-516` 的 `_click_pseudo_background` 使用 `SetForegroundWindow` 但未用 AttachThreadInput 技巧，跨进程前台化会被 OS 前台锁定拒绝。

**Fix**: 从 `agent/src/platforms/windows/input_variants.py:441-473` 的 `SeizeInputVariant._ensure_foreground` 移植 AttachThreadInput 技巧：

```
1. 获取前台窗口 hwnd_foreground 和其线程 id
2. 获取目标窗口 hwnd_target 的线程 id
3. AttachThreadInput(foreground_tid, target_tid, TRUE)
4. SetForegroundWindow(hwnd_target)
5. AttachThreadInput(foreground_tid, target_tid, FALSE)  // detach
6. 验证 GetForegroundWindow() == hwnd_target
```

**Logging**: 前台化成功/失败、AttachThreadInput 成功/失败、恢复原前台窗口结果。

> **Note (Spec C / TD-121, 2026-07-16)**: Stage 1.1 的 AttachThreadInput 修复在 agent 端解决了"跨进程前台化被拒绝"问题, 但未解决多 session 并行时 SendInput/PseudoBackground 串台的并发问题。Spec C 在 `WindowsInputHandler` 实例级加 `threading.RLock`, 串行化 6 个方法入口 (`_click_sendinput` / `_swipe_sendinput` / `_key_press_sendinput` / `_text_input_sendinput` + `_click_pseudo_background` / `_key_press_pseudo_background` / `_text_input_pseudo_background`), 作为 Stage 1.1 的底层并发兜底。
>
> **RLock 选择理由**: PseudoBackground 内部调用 `_click_sendinput` 等方法, 若用 `Lock` 会死锁; `RLock` 可重入允许同线程多次获取。
>
> **PostMessage/SendMessage 路径不加锁**: hwnd-isolated, 天然可并行。
>
> 详见 SendInput 序列化历史 spec（已归档清理；前台 SendInput 由 input_mode 配置互斥控制，见 section 1.1）。

### 1.2 Test SendInput (Foreground) Mode

**Precondition**: BD2 窗口手动置前台。
**Action**: 执行 get_email pipeline (debug_mode=True)。
**Verify**:
- `open_mailbox` 点击后邮箱是否打开
- 调试图片 `template_match/match_success_*.png` 确认匹配位置
- 调试图片 `action/wait_fail_*.png` 确认等待节点看到的是邮箱界面还是主菜单

### 1.3 Test PseudoBackground Mode

**Setup**: 临时修改 `device.py` 让 BD2 强制走 PseudoBackground（在 `_resolve_auto_input_method` 中对 UnityWndClass 返回 PseudoBackground，或加 CLI override）。

**Precondition**: BD2 窗口在后台（Trae IDE 或其他窗口在前台）。
**Action**: 执行 get_email pipeline (debug_mode=True)。
**Verify**:
- PseudoBackground 临时前台化是否成功（日志）
- 点击是否生效（邮箱是否打开）
- 原前台窗口是否正确恢复

**Cleanup**: 测试完成后恢复 `_resolve_auto_input_method` 原逻辑（Unity → SendInput）。

## Stage 2: Documentation

### 2.1 DPI/Coordinate System Document

**Path**: `docs/business/devices/dpi-coordinate.md`

**Content**:
1. 3 层坐标模型 (BASE → LOGICAL → PHYSICAL → SCREEN)
2. DPI-aware 游戏的 logical 层虚构问题
   - BD2 (Unity) 窗口化时 logical=1024x576 是虚构分辨率
   - 游戏实际渲染在 physical=1536x864
   - DPI 在转换链中数学抵消，但 logical 层有认知误导风险
3. 全屏 vs 窗口化的 DPI 处理差异
   - 全屏: is_fullscreen=True, logical_to_physical_ratio=1.0
   - 窗口化: is_fullscreen=False, logical_to_physical_ratio=dpi_scale
4. 模板图片从 DPI=1 (1920x1080) 截取的缩放链
   - scale_ratio = target_physical / base = 1536/1920 = 0.8
   - DPI 不影响 scale_ratio（用 physical 计算）
5. ROI 缩放处理
   - BASE ROI → LOGICAL ROI → PHYSICAL ROI
   - `apply_roi_offset_to_subcoord` 不处理 DPI（上游已处理）
6. 验证方法 + 调试图片解读
7. 常见错误模式（N49-N53 坐标易错点）

### 2.2 Task Execution Troubleshooting Document

**Path**: `docs/business/tasks/troubleshooting.md`

**Content**:
1. 分层排查步骤（每层含"症状 / 检查方法 / 常见根因 / 修复方向"）：
   - Layer 1: WS 消息链 (backend → consumer → agent handler)
   - Layer 2: 设备解析 (device_info → _resolve_target_device)
   - Layer 3: 截图 (method 选择、black_ratio、client_only)
   - Layer 4: 模板匹配 (confidence、scale_ratio、ROI 偏移)
   - Layer 5: 点击 (input_method、前台状态、坐标变换)
   - Layer 6: OCR (engine 注册、ROI 缩放、识别内容)
2. 调试模式启用流程
3. 调试图片解读方法
4. AI auto-heal 契约（穷尽尝试后才通知用户）
5. 历史教训索引（N133/N145/N148/N154）
6. 排查后维护流程（更新文档 + 登记 lesson）

**AI 使用约定**：
- AI 接到任务失败问题时，按 Layer 1→6 顺序排查
- 每层记录检查结果（✅/❌）
- 穷尽所有层后仍找不到根因 → 询问用户
- 排查完成后检查文档是否需要新增检查步骤

## Stage 3: Window-Background-Wait Feature

### 3.1 Configuration Storage

**AppSettings** (`setting_key='wait_when_background'`):
```json
{
  "enabled": false,
  "timeout_seconds": 1800,
  "check_interval_ms": 500
}
```

- `enabled`: 是否启用窗口后台等待（默认 false）
- `timeout_seconds`: 等待超时（默认 1800=30分钟，0=无限等待）
- `check_interval_ms`: 前台状态检查间隔（默认 500ms）

### 3.2 Backend API

**Endpoint**: `GET/POST /api/v2/settings/wait-when-background/`
- 复用 `settings/views.py:agent_debug_view` 模式
- singleton upsert 语义

**Pipeline Execute 集成**:
- `pipeline/views.py:execute` 读取 `wait_when_background` 配置
- 附带到 WS task_data: `wait_when_background={enabled, timeout_seconds, check_interval_ms}`

### 3.3 Agent Implementation

**orchestrator.execute_pipeline 修改**:
```python
def execute_pipeline(self, pipeline_json, debug_mode=False, debug_dir="",
                    wait_when_background=None):
    # ... existing setup ...
    
    if wait_when_background and wait_when_background.get("enabled"):
        self._start_window_monitor(
            device=device,
            timeout=wait_when_background.get("timeout_seconds", 1800),
            interval=wait_when_background.get("check_interval_ms", 500) / 1000,
        )
    
    result = engine.execute()
    
    self._stop_window_monitor()
    return result
```

**WindowMonitor 集成**:
- 启动后台线程，按 interval 检查 `device.is_foreground()`
- 检测到失焦：
  1. `engine.pause()` (引擎暂停在当前节点完成后)
  2. WS 通知前端: `task.progress {status: "paused", reason: "window_background"}`
  3. 等待恢复（受 timeout 限制）
- 检测到恢复前台：
  1. `engine.resume()`
  2. WS 通知前端: `task.progress {status: "running"}`
- 超时：`engine.cancel()` + WS 通知 `task.result {success: false, error_msg: "窗口后台等待超时"}`

### 3.4 Frontend UI

**Settings Page**: "Agent 调试模式" 配置组附近新增"窗口后台等待"配置组：
- Switch: 启用/禁用
- Input Number: 等待超时（秒）
- Input Number: 检查间隔（毫秒）

**Task Execution Page**: 状态栏显示：
- 正常执行: "执行中"
- 窗口后台暂停: "已暂停：窗口在后台，请恢复窗口前台以继续" (黄色提示)
- 超时失败: "失败：窗口后台等待超时"

**i18n**: 中英文双语。

### 3.5 Why This Approach

- 利用现有 `pause_task()/resume_task()` 和 `WindowMonitor` 基础设施
- 与 engine 解耦（engine 不感知窗口状态，只接收 pause/resume 信号）
- WS 通知让前端实时显示暂停状态
- 超时兜底防止任务卡死
- 仅任务执行期间监控（用户选择），不占用空闲资源

## Tech Debt (Discovered During Investigation)

### TD-090: Two Parallel Input Systems (Medium Priority)

**Symptom**: `input_variants.py` (9 variants enum) 和 `input.py` (3 method strings) 并存，`device.py` 实际只用 3 方法字符串系统，9 变体仅用于兼容性查询。

**Fix Direction**: 统一为一套系统。推荐保留 3 方法字符串系统（实际使用），将 9 变体的兼容性表合并到 `input_variants.py` 的查询函数中，删除未使用的 InputVariant 子类。

**When**: Stage 1.1 修复 PseudoBackground 后评估（如果 9 变体系统有 AttachThreadInput 实现可复用，先移植再统一）。

### TD-091: Two RuntimeDisplayContext Classes (Low Priority)

**Symptom**: `utils/display_context.py` (正式，286行) 和 `utils/display.py` (遗留，44行) 都定义了 `RuntimeDisplayContext`，字段完全不同。

**Fix Direction**: 删除 `utils/display.py` 中的遗留类，全局搜索引用并迁移到 `utils/display_context.py`。

**When**: Stage 2.1 写 DPI 文档时顺便修复（文档需要描述正确的 RuntimeDisplayContext）。

### TD-092: gaf-orchestrator References Non-Existent Scripts (N157)

**Symptom**: `.skills/skills/gaf-orchestrator/SKILL.md:130-131` 引用 `scripts/debug/check_execution.py` 和 `scripts/debug/trace_logs.py`，实际 `scripts/debug/` 目录不存在。

**Fix Direction**: 
- 选项 A: 创建这两个脚本（实现排查功能）
- 选项 B: 更新 SKILL.md 引用为实际存在的工具（如 `agent/src/utils/screenshot_diagnostic.py`）

**When**: Stage 2.2 写排查步骤文档时决定（文档需要引用可用的排查工具）。

### TD-093: data-chain-checklist Path Inconsistency

**Symptom**: `gaf-orchestrator/SKILL.md` 引用 `.ai-memory/checklists/data-chain-checklist.md`，实际文件位于 `.ai-memory/checklists/data-chain-checklist.md`。

**Fix Direction**: 更新 SKILL.md 引用路径。

**When**: Stage 2.2 写排查步骤文档时一并修复。

## Verification Criteria

### Stage 1
- [ ] PseudoBackground 修复后，AttachThreadInput 日志显示前台化成功
- [ ] SendInput 模式：BD2 前台时 get_email open_mailbox 点击生效
- [ ] PseudoBackground 模式：BD2 后台时临时前台化点击生效
- [ ] 调试图片生成正常

### Stage 2
- [ ] `docs/business/devices/dpi-coordinate.md` 覆盖 3 层模型 + DPI-aware 虚构问题 + 验证方法
- [ ] `docs/business/tasks/troubleshooting.md` 覆盖 6 层排查步骤 + AI 使用约定
- [ ] AI 按排查步骤文档能诊断 get_email 问题

### Stage 3
- [ ] `POST /api/v2/settings/wait-when-background/` 正常返回
- [ ] 启用后，任务执行期间 BD2 窗口置后台 → 任务暂停 → WS 通知前端
- [ ] BD2 窗口恢复前台 → 任务继续 → WS 通知前端
- [ ] 超时后任务失败 + WS 通知
- [ ] 前端设置页 + 任务执行页 UI 正常

### Tech Debt
- [ ] TD-090 评估并处理
- [ ] TD-091 修复
- [ ] TD-092 处理
- [ ] TD-093 修复

## Commit Plan

分阶段 commit，每阶段 2-4 个 commit：

**Stage 1** (3 commits):
1. `fix(agent): port AttachThreadInput to PseudoBackground for cross-process foreground`
2. `test(agent): verify SendInput foreground mode with BD2 get_email`
3. `test(agent): verify PseudoBackground mode with BD2 get_email`

**Stage 2** (2 commits):
1. `docs(design): add DPI coordinate system document`
2. `docs(troubleshooting): add task execution troubleshooting guide`

**Stage 3** (4 commits):
1. `feat(backend): wait-when-background settings API + WS passthrough`
2. `feat(agent): orchestrator window monitor + pause/resume on background`
3. `feat(frontend): wait-when-background settings UI + task pause status`
4. `feat(i18n): wait-when-background translations`

**Tech Debt** (按需):
- `refactor(agent): unify input method systems`
- `refactor(agent): remove legacy RuntimeDisplayContext`
- `fix(skills): update gaf-orchestrator script references`
