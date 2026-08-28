---
date: 2026-07-30
topic: [testing-workflow, real-device-test, pipeline-debug, emulator-vs-window, ai-debugging-perspective]
priority: high
cross_refs: [N195, N191, N192, N182, N184, N133]
status: active
created_by: AI
trigger: '用户测试 `resources/BrownDust-II/tasks/get_email.json` 时连续出现多个流程问题: (1) 没确认 BD2 窗口状态就直接跑 pipeline, 导致第一个节点失败; (2) 测试中断后下次没问用户怎么返回起点, 直接重跑; (3) 设备发现只看到 LDPlayer (ADB), 误判 BD2 窗口在线状态; (4) 节点点击位置算对了但点击没生效, 没及时查窗口前台状态. 用户反馈"这种任务调试的经验需要沉淀下吗, 成为个知识文档啥的".'
symptom: [no-preflight-check, no-asking-user-how-to-return, emulator-online-misjudged, window-foreground-not-checked, ai-not-using-debug-log, test-loop-inefficient]
solution: 实机测试 pipeline 必须遵循"测前确认 → 节点链路分析 → 分阶段执行 → 日志驱动诊断"四步流程. 测前用 OCR+模板匹配确认当前画面处于节点链路的哪个阶段, 不在起点则问用户返回路径 (不要假设画面). 设备发现"ADB 在线"≠"窗口可点击", 模拟器最小化也能跑 ADB, 必须额外检查窗口可见性. 点击失败优先查窗口前台状态 + input_method (SendInput 需前台, PostMessage 对 Unity 游戏无效).
diff_keywords: [real-device, pipeline-test, emulator, preflight, debug-log]
related_files:
  - resources/BrownDust II/tasks/get_email.json
  - agent/src/devices/center.py
  - agent/src/platforms/windows/input_variants.py
  - agent/src/platforms/windows/input.py
  - agent/src/engine/nodes/template_match.py
  - .ai-memory/lessons/N195-transparent-png-alpha-mask-bug.md
  - .ai-memory/lessons/N191-schema-unification-data-flow-checklist.md
  - .trae/rules/env-hardrules.md
  - .ai-memory/lessons/N133-emulator-control-gap.md
---

# N196: 实机测试 pipeline 的标准流程与诊断手法

## 核心问题: AI 在实机测试时的 4 个反复犯的错误

### 错误 1: 不做测前确认, 直接跑 pipeline

**现象**: 用户说"测试 get_email.json", AI 直接 `python scripts/test_get_email_real.py`, 结果第一个节点 `open_mailbox` 失败 — 因为 BD2 窗口不在主界面 (可能在其他页面, 或根本不在线).

**正确做法**:
```text
测前必做 3 件事:
1. 设备发现: 列出所有发现的设备, 确认目标设备在线
2. 截图 + OCR: 截当前画面, OCR 识别文字, 推断处于哪个画面
3. 对照节点链路: 看 pipeline 第一个节点期望什么画面, 当前画面是否匹配
   - 不匹配: 问用户"当前在 X 页面, 第一个节点需要 Y 页面, 怎么返回?"
   - 匹配: 再跑 pipeline
```

### 错误 2: 测试中断后, 下次直接重跑, 没问用户怎么返回起点

**现象**: 上次测试到第 5 个节点失败, BD2 画面停在邮箱列表页. 这次直接重跑, 第一个节点 `open_mailbox` (期望主界面) 又失败.

**正确做法**:
```text
中断后重跑前必问:
- "上次测试停在 X 节点, 当前画面应该在 Y 页面"
- "第一个节点需要 Z 页面, 请问怎么从 Y 返回 Z?"
  (例如: "从邮箱列表页返回主界面, 是点返回键还是按 ESC?")
- 用户确认画面就绪后再跑
```

**用户原话**: "可能之前测试是到任务的某一阶段出问题了, 然后下次任务你也没返回第一步的界面对吧, 其实你可以问我怎么返回的"

### 错误 3: 设备发现"ADB 在线"误判窗口可点击

**现象**: `DeviceCenter.auto_discover()` 返回 LDPlayer (ADB 设备), AI 以为 BD2 窗口在线. 实际 LDPlayer 模拟器窗口最小化也能跑 ADB — ADB 连接只依赖 adb server + 模拟器进程, 不依赖窗口可见性.

**用户原话**: "雷电模拟器在线判断不能只看 adb, 还得看那个窗口有没有在, 模拟器的窗口在最小化也能跑"

**正确做法**:
```text
设备在线状态分级:
- Level 1 (ADB 在线): adb devices 能看到 serial — 仅表示 adb server 可连
- Level 2 (窗口可见): 窗口未最小化, 可截图 — WindowsDevice.get_client_rect() 有效
- Level 3 (窗口前台): 窗口在前台, 可 SendInput 点击 — GetForegroundWindow() == hwnd

测试 template_match + click 类 pipeline 必须 Level 3 (SendInput 需前台).
测试 OCR + key_press 类 pipeline 可降到 Level 2 (PostMessage key 对部分游戏有效).
纯 ADB pipeline (截图 + adb shell input) Level 1 即可.
```

### 错误 4: 点击没生效时, 没及时查窗口前台状态 + input_method

**现象**: `open_mailbox` 节点 template_match 成功 (confidence=0.97), 点击位置算对了 (logical 859,30 → phys 1289,45), 但 BD2 没反应, 邮箱界面没打开.

**正确做法**:
```text
点击没生效诊断顺序:
1. 查 input_method: BD2 是 Unity 游戏, PostMessage 鼠标事件被忽略, 必须用 SendInput
2. 查窗口前台状态: SendInput 需要窗口在前台, 用 GetForegroundWindow() == hwnd 确认
3. 查点击坐标: logical → physical 转换是否正确 (dpi_ratio 是否注入)
4. 查窗口客户区: 点击坐标是否在 client_rect 内 (不在客户区内点击无效)
5. 查 BringToForeground: 是否在 click 前调用 bring_to_foreground(hwnd)
```

## 标准流程: 实机测试 pipeline

### Step 1: 测前确认 (Pre-flight Check)

```python
# 1.1 设备发现 + 状态分级
center = DeviceCenter()
devices = center.auto_discover()
for d in devices:
    print(f"{d.name}: type={type(d).__name__}, id={d.device_id}")

# 1.2 目标设备截图 + OCR
target = pick_windows_device(devices)  # 优先 WindowsDevice
target.connect()
img = target.capture_screen()
ocr_results = rapid_ocr.recognize(img)
full_text = " ".join(r.text for r in ocr_results)

# 1.3 对照 pipeline 第一个节点期望画面
first_node = pipeline["nodes"][0]
expected_screen = infer_expected_screen(first_node)  # template_match 期望什么图标 / ocr 期望什么文字
current_screen = infer_current_screen(full_text)     # OCR 命中哪些关键词 → 推断当前画面
if expected_screen != current_screen:
    ask_user_how_to_return(current_screen, expected_screen)
    # 不要假设画面, 不要自动点击返回, 问用户
```

### Step 2: 节点链路分析

测试前过一遍 pipeline 的节点链路, 标注每个节点期望的画面 + 匹配方式:

```text
get_email.json 节点链路 (示例):
| # | 节点 | 类型 | 期望画面 | 匹配方式 |
|---|------|------|---------|---------|
| 1 | open_mailbox | template_match | 主界面 (右上角邮箱图标) | 图片 |
| 2 | wait_regular_email | wait/ocr | 邮箱列表页 | 文字"普通邮箱" |
| 3 | detect_empty_email | template_match | 邮箱列表页 | 图片 (空邮箱标识) |
| 4 | branch_empty_email | branch | — | 分支 |
| 5 | claim_all_rewards | ocr | 有邮件页 | 文字"全部领取"+点击 |
| 6 | wait_mailbox_still_visible | wait/template | 邮箱还在 | 图片 |
| 7 | click_back_dismiss_popup | template_match | 弹窗页 | 图片 (返回键) |
| 8 | wait_popup_dismissed | wait/disappear | 弹窗消失 | 图片消失 |
| 9 | exit_mailbox | key_press | 退出邮箱 | 按键 ESC |
| 10 | wait_between_esc | wait/fixed | — | 等待 |
| 11 | back_to_main_esc | key_press | 回主界面 | 按键 ESC |
| 12 | wait_main_menu | wait/template | 主界面 | 图片 (主界面标识) |
```

这张表的作用:
- 测试失败时, 快速定位"当前画面 + 失败节点 → 期望画面是什么 → 画面不匹配的根因"
- 测前确认时, 对照第一个节点期望画面判断是否需要让用户返回
- 测试中断后重跑时, 知道应该回到哪个画面

### Step 3: 分阶段执行 (不要一次性跑完)

```text
阶段 1: 跑前 2-3 个节点, 验证起点 + 进入流程
  - 成功: 继续阶段 2
  - 失败: 看日志, 修 bug 或让用户调整画面

阶段 2: 跑中间节点 (claim_all_rewards / wait / click_back)
  - 成功: 继续阶段 3
  - 失败: 看日志, 诊断匹配/点击问题

阶段 3: 跑退出节点 (exit_mailbox / back_to_main / wait_main_menu)
  - 成功: pipeline 完成
  - 失败: 看日志, 诊断退出/返回问题
```

**不要一次性跑完 12 个节点** — 失败后定位是哪个节点的问题要翻全日志, 而且画面可能已经变化 (例如点击误中其他按钮跳到未知页面).

### Step 4: 日志驱动诊断 (不要凭猜测)

GAF 有完整的 structured JSONL 日志, 每个节点执行都会记:
- `node.execute.start` / `node.execute.complete`
- `coord_transform` (sub_image_to_full / publish_match_pos / logical_to_physical)
- `variables_snapshot` (节点间变量传递)
- `screenshot_path` (annotated + raw)

```text
诊断顺序:
1. 看最新 exec-*.jsonl: Get-ChildItem debug/agent/structured/*.jsonl | Sort LastWriteTime -Desc | Select -First 1
2. 找失败节点: grep '"success": false' exec-*.jsonl
3. 看失败节点的 input_config + error_msg + variables_snapshot
4. 看失败节点的 coord_transform trace (坐标系转换链路)
5. 看 screenshot_path 的 annotated 图 (红色框 = 匹配位置)
6. 看 previous_node_result_data (上一个节点输出 → 当前节点输入)
```

**不要凭猜测改代码** — 先看日志, 日志会告诉你:
- confidence 多少 (匹配是否成功)
- match_loc 在哪 (点击位置是否对)
- coord_system 是什么 (坐标系是否一致)
- variables_snapshot 有什么 (变量是否传递成功)

## 诊断手法: 点击没生效

### 手法 1: 查 input_method + 窗口前台状态

```python
import ctypes
target.connect()
print(f"input_method: {target._input_method}")  # SendInput / PostMessage
hwnd = int(target._get_target(), 16)
fg = ctypes.windll.user32.GetForegroundWindow()
print(f"foreground: {fg}, target: {hwnd}, is_fg: {fg == hwnd}")
# 如果 is_fg=False 且 input_method=SendInput, 点击会发到错误窗口
```

### 手法 2: 查窗口客户区 + 点击坐标是否在内

```python
client_rect = target.get_client_rect()  # (0, 0, 1540, 866)
click_x, click_y = 1289, 45  # physical
# 转回 client-logical
logical_x = click_x / 1.5  # 859
logical_y = click_y / 1.5  # 30
# 检查是否在客户区内
in_client = (0 <= logical_x < client_rect[2]) and (0 <= logical_y < client_rect[3])
print(f"click in client: {in_client}")
```

### 手法 3: 手动点击验证

```python
# 用 WindowsInputHandler 直接点击, 看是否生效
from platforms.windows.input import WindowsInputHandler
handler = WindowsInputHandler(method="SendInput")
handler.set_dpi_ratio(1.5)
result = handler.click(target._get_target(), 859, 30)
print(f"click result: {result.success}, error: {result.error}")
# 如果手动点击也不生效, 说明窗口/游戏问题, 不是代码问题
```

### 手法 4: 查 input_compatibility (Unity/Unreal/Godot)

```python
from platforms.windows.input_variants import INPUT_COMPATIBILITY_TABLE, recommend_legacy_input_method
import ctypes
class_name = ctypes.create_unicode_buffer(256)
ctypes.windll.user32.GetClassNameW(hwnd, class_name, 256)
print(f"window class: {class_name.value}")
# UnityWndClass → PostMessage 鼠标无效, 必须 SendInput
recommended = recommend_legacy_input_method(class_name.value)
print(f"recommended input: {recommended}")
```

## 诊断手法: OCR 识别失败

### 手法 1: ROI 裁剪 + 全图识别对比

```python
# A. ROI 内识别 (节点方法)
roi_phys = transformer.process_roi(roi_base, ...)
crop = img[ry:ry+rh, rx:rx+rw]
texts_roi = ocr.recognize(crop)

# B. 全图识别 (最宽容)
texts_full = ocr.recognize(img)

# 如果 B 命中目标文字但 A 没有, 说明 ROI 裁剪偏移
# 如果 A/B 都没命中, 说明 OCR 引擎问题或画面确实没有目标文字
```

### 手法 2: 画面阶段推断

```python
stage_keywords = {
    "主界面": ["邮件", "邮箱", "任务", "商店", "公会"],
    "邮箱列表页": ["普通邮箱", "全部领取", "领取"],
    "空邮箱": ["空"],
    "弹窗": ["确认", "确定", "关闭"],
}
for stage, kws in stage_keywords.items():
    hits = [kw for kw in kws if kw in full_text]
    if hits:
        print(f"[可能] {stage}: 命中 {hits}")
```

## 设备发现的陷阱

### 陷阱 1: LDPlayer 最小化也能跑 ADB

`DeviceCenter.auto_discover()` 发现 LDPlayer (ADB) 不代表窗口可见:
- ADB 连接只依赖 `adb server` + `ldplayer.exe` 进程
- LDPlayer 窗口最小化到任务栏, ADB 仍然可连
- LDPlayer 窗口隐藏到托盘, ADB 仍然可连
- LDPlayer 进程在但窗口已关闭 (后台保活), ADB 仍然可连

**结论**: ADB 在线 ≠ 窗口可点击. 测试 click 类 pipeline 前必须确认窗口可见 + 前台.

### 陷阱 2: Windows 窗口被 LDPlayer 进程去重

`DeviceCenter.auto_discover()` 第二 pass 发现 Windows 窗口时, 会跳过属于已知模拟器进程的窗口 (line 127-137). 如果 BD2 跑在 LDPlayer 内, BD2 的 Windows 窗口会被识别为"模拟器窗口"跳过, 只返回 ADB 设备.

**但**: 如果用户想用 WindowsDevice 路径 (SendInput 点击, 比 ADB shell input 快), 需要手动绕过去重:
- 选项 A: 关闭 LDPlayer, 用 BD2 PC 版 (独立窗口, 非模拟器)
- 选项 B: 修改 DeviceCenter 加 `force_include_emulator_window=True` 参数
- 选项 C: 测试脚本直接构造 WindowsDevice, 绕过 auto_discover

### 陷阱 3: BD2 窗口标题不固定

BD2 窗口标题可能是 "BrownDust II" / "棕色尘埃2" / "雷电模拟器" (LDPlayer 内). `WindowDiscovery.find_gaming_windows()` 可能漏识别. 测试前手动确认窗口标题.

## AI 调试视角 (N192 A 视角) 应用

实机测试时, AI 自己跑 pipeline 报错, 需要能从日志快速定位问题:

```text
□ A1. 报错可读性: 节点失败 error_msg 是否含 节点 id / 输入参数 / 失败原因?
       - get_email 测试: error_msg="模板匹配置信度 0.1745 低于阈值 0.8" ✓ 含原因
       - 但缺节点 id (在 JSONL log 里有, error_msg 里没有)

□ A2. 中间结果落盘: 失败节点的 variables_snapshot 是否完整?
       - get_email 测试: variables_snapshot 含 open_mailbox_match_result (confidence/x/y/clicked) ✓
       - wait_regular_email 失败时, variables_snapshot 含 ocr_result (texts/boxes/region) ✓

□ A3. 日志分段: 能否从 JSONL log 快速定位"卡在第几个节点"?
       - grep '"event": "node.execute.start"' exec-*.jsonl → 列出所有节点执行顺序
       - grep '"success": false' → 找失败节点

□ A4. 节点链路可追溯: 失败时能否回溯 上一个节点输出 → 当前节点输入?
       - JSONL log 有 previous_node_id + previous_node_result_data ✓
       - 有 inter_node_gap_ms (节点间间隔) ✓

□ A5. retry/fallback trace: 重试路径是否留 trace?
       - template_match 有 auto-heal (debug_mode=True 时尝试不同截图方法), JSONL log 有记录
```

## 用户调试视角 (N192 B 视角) 应用

用户在前端编辑器配置 pipeline 时, 需要能看懂错误:

```text
□ B1. 错误提示归一: "模板匹配置信度 0.1745 低于阈值 0.8" 用户能看懂吗?
       - 技术用户: 能看懂, 知道调阈值或换模板
       - 非技术用户: 看不懂, 需要"模板匹配失败, 请检查模板图片是否正确"

□ B3. 错误定位: 用户能知道"第几个节点 / 哪个字段"出错吗?
       - JSONL log 有 node_id, 但前端展示需要从 log 反查节点配置
       - 当前 dashboard 有节点链路高亮 (待确认)

□ B4. 模板可跑通: resources/*/templates/template.json 是否能让用户照着改就能跑通?
       - BD2 get_email.json 用的是 roi 数组 [x,y,w,h] (canonical), 模板路径是相对路径
       - 用户照着改 ROI / 模板路径, 应该能跑通 (N195 透明 PNG bug 修复后)

□ B6. 执行反馈: 任务执行失败后, UI 是否展示节点链路 + 失败节点高亮?
       - backend scheduler 有 task_execution_log, dashboard 有展示 (待确认)
```

## 失败模式 (禁止)

- ❌ 不确认窗口状态直接跑 pipeline → ✅ 测前 OCR + 对照节点链路
- ❌ 中断后重跑不问用户怎么返回起点 → ✅ 主动问"当前在 X, 需要回 Y, 怎么返回?"
- ❌ ADB 在线就以为窗口可点击 → ✅ 分级判断 (ADB / 窗口可见 / 窗口前台)
- ❌ 点击没生效就反复重试 → ✅ 查 input_method + 前台状态 + 客户区
- ❌ 不看 JSONL log 凭猜测改代码 → ✅ 先看日志, 日志会告诉你 confidence/loc/coord_system
- ❌ 一次性跑完 12 个节点 → ✅ 分阶段执行 (前 2-3 / 中间 / 退出)
- ❌ 把"LDPlayer ADB 在线"等同于"BD2 窗口在线" → ✅ 模拟器最小化也能跑 ADB, 必须额外查窗口

## 检查清单 (实机测试前必跑)

```text
□ 1. 设备发现: auto_discover() 列出所有设备, 确认目标设备在线
□ 2. 窗口可见性: WindowsDevice.get_client_rect() 有效, 不抛异常
□ 3. 窗口前台: GetForegroundWindow() == hwnd (SendInput 需前台)
□ 4. 画面确认: OCR 截图识别当前画面, 对照 pipeline 第一个节点期望画面
□ 5. 画面不匹配: 问用户"当前 X, 需要 Y, 怎么返回?" (不要自动点击)
□ 6. 节点链路分析: 过一遍 pipeline 节点表 (节点 / 类型 / 期望画面 / 匹配方式)
□ 7. 分阶段执行: 前 2-3 节点 → 中间节点 → 退出节点, 不要一次性跑完
□ 8. 日志驱动: 失败后看最新 exec-*.jsonl, 找 success=false 节点
□ 9. input_method: BD2 (Unity) 必须 SendInput, PostMessage 鼠标无效
□ 10. 坐标转换链路: logical → physical → screen, 每一步都查 trace
```

## 与其他 lesson 关系

- **N195**: 透明 PNG alpha mask bug. 本 lesson 是测试流程经验, N195 是具体 bug.
- **N191**: schema 归一化. 本 lesson 强调"测前确认", N191 强调"改后全链路扫描".
- **N192**: 双调试视角. 本 lesson 应用 N192 的 A/B 视角到实机测试场景.
- **N182**: 三维根因分析. 本 lesson 的诊断手法用 N182 的三维定位思路.
- **N184**: 节点可观测性. 本 lesson 依赖 JSONL log, N184 定义了 log 字段规范.
- **N133**: 模拟器控制 gap. 本 lesson 补充 N133 的"模拟器最小化也能跑 ADB"陷阱.

## L0 硬约束升级建议 (待评估)

考虑升级到 `env-hardrules.md` L0 级:

```text
## 实机测试硬约束 (N196 衍生, 待评估)

- 跑实机 pipeline 前必做 3 件事: 设备发现 + 截图 OCR + 画面阶段推断
- 画面不在起点时, 必须问用户怎么返回, 不能自动点击返回
- ADB 在线 ≠ 窗口可点击, 模拟器最小化也能跑 ADB
- 点击失败优先查 input_method + 窗口前台状态
- 失败诊断必须看 JSONL log, 不能凭猜测改代码
```

当前不升级 L0, 理由: 流程类经验不像 conda/heredoc 那样"违反就报错", 更像"最佳实践". 留作 lesson 级别 + gaf-orchestrator 决策树引用即可.
