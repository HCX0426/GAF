---
date: 2026-07-11
symptom: [test-before-understand, e2e-failure, wrong-endpoint, pre-existing-bug, false-confidence, api-ui-gap, python, import, missing, threading, type-annotation, commit-without-e2e, p-004]
solution: 测试先于理解家族合并 (N156+N147)。(1) 写 Playwright E2E 测试前必 Grep 前端 store/api 层确认实际调用的后端端点；"API 通过" ≠ "UI 通过"；临时测试通过后持久化到 scripts/e2e/scenarios/；测试失败先读代码不盲目重试。(2) Python 新 typing/threading 构造使用必同步加 import；commit 前必端到端验证 (不只单元测试)；静态检查通过 ≠ 运行时可用。
diff_keywords: ["qapanel", "useailabstore", "ai", "qa", "views", "qa_views", "chat", "ai_qa_chat", "handler", "screenshot", "cache", "screenshot_cache"]
related_files:
  - frontend/src/pages/AI/QAPanel.tsx
  - frontend/src/stores/useAiLabStore.ts
  - frontend/src/api/ai.ts
  - backend/gaf_ai/qa_views.py
  - scripts/e2e/scenarios/ai_qa_chat.py
  - agent/src/client/handler.py
  - agent/src/devices/screenshot_cache.py
created_by: AI
merged_n_ids: [N156, N147]
level: L1
n_id: N156
topic: testing
---


# N156 + N147 — 测试先于理解：E2E 端点确认 + Python import 同步 + 端到端验证

## 家族合并说明

本文件合并 N156（Test before understand: E2E tests fail when you don't read the frontend code first）和 N147（Python 新库/typing 使用必须同步添加 import + commit 前端到端验证）。两者同属"测试先于理解 / 静态检查 ≠ 运行时可用"根因家族：
- **N156** 关注**前端 E2E 测试**：写 Playwright 前不读前端代码 → 假设错误端点 → 测试失败
- **N147** 关注**后端 Python import**：新增 typing/threading 构造忘加 import → 静态检查通过但运行时 NameError

合并后形成完整的"测试先于理解"检查清单：从前端 E2E 到后端 import，核心原则一致：**静态检查通过 ≠ 运行时可用，必须端到端验证**。

---

## N156: Test before understand — E2E tests fail when you don't read the frontend code first

> **级别**: L1 可复用经验（Y/N 检查清单价值 + 影响 AI 全局测试行为）
> **分类**: 测试方法论 — E2E 测试反模式（先测试后理解）
> **来源**: 2026-07-11 SiliconFlow UI 集成测试 — 2 轮 Playwright 测试失败
> **登记**: 2026-07-11
> **状态**: ✅ FIXED (commit `-` bug 修复 + `ai_qa_chat.py` 回归测试持久化)

### 触发原话

"为啥之前端到端测试测不出来，以后怎么可以测完，Playwright 测试，git的命令为啥都要我确认？"

### 事件概述

用户要求测试 SiliconFlow LLM 集成："登录打开gaf再选这个来对话"。AI 执行了 3 轮 Playwright E2E 测试：

| 轮次 | 测的页面 | AI 假设的端点 | 实际调用的端点 | 结果 |
|:----:|---------|-------------|--------------|:----:|
| 1 | `/ai/assistant` | `/ai/chat/` | `/ai/generate-pipeline-stream/` (Pipeline SSE) | ❌ |
| 2 | `/ai/qa` | `/qa/qa-sessions/{id}/messages/` | 同左（不存在，404） | ❌ |
| 3（修复后） | `/ai/qa` | `/qa/ask/` | `/qa/ask/` → `call_llm()` | ✅ |

**第 1 轮失败原因**：AI 用 PowerShell 验证了 `/ai/chat/` API 能工作，就假设 UI 也调用 `/ai/chat/`。但 `AiAssistantPanel.tsx` 实际调用 `/ai/generate-pipeline-stream/`（Pipeline 生成 SSE），完全不是聊天端点。

**第 2 轮失败原因**：AI 切换到 QA 面板，但没有先读 `QAPanel.tsx` 代码。`QAPanel.tsx` 调用 `sendQAMessage()` → `/qa/qa-sessions/{id}/messages/`，这个端点**根本不存在**（后端只有 `/qa/ask/`）。同时发现 `backend/gaf_ai/qa_views.py` 有 `model_name` NameError bug。

### 根因分析

#### 反模式："先测试后理解"

```
错误流程（AI 实际执行）:
  1. PowerShell 测 /ai/chat/ API → ✅ 通过
  2. 假设 UI 也用 /ai/chat/ → 写 Playwright 测 /ai/assistant
  3. 测试失败 → 才去读前端代码 → 发现 UI 用的是另一个端点
  4. 切换页面 → 又不读代码 → 又失败
  5. 最终读代码 → 发现 2 个预存 bug → 修复 → 通过

正确流程:
  1. PowerShell 测 /ai/chat/ API → ✅ 通过
  2. Grep 前端代码: "ai/chat" → 发现只有 api/ai.ts 用它（测试连接用）
  3. Grep 前端代码: "fetch.*ai" → 发现 AiAssistantPanel 用 generate-pipeline-stream
  4. Grep 前端代码: "qa-sessions" → 发现 QAPanel 用 /qa/qa-sessions/{id}/messages/
  5. Grep 后端代码: "qa-sessions.*messages" → 发现端点不存在
  6. 先修 bug → 再写测试 → 一次通过
```

#### 为什么"API 通过"≠"UI 通过"

| 层 | 测什么 | 通过条件 |
|---|--------|---------|
| API 层 | 后端端点直接调用 | 返回 200 + 正确 JSON |
| UI 层 | 前端组件 → store → api → 后端 | 前端调用的端点必须存在 + 返回格式匹配 + UI 正确渲染 |

API 测试只验证后端，UI 测试验证完整链路。前端可能调用**完全不同的端点**（如 Pipeline vs Chat），或调用**不存在的端点**（如本例的 messages/ 404）。

### 修复

#### 1. Bug 修复（commit `-`）

- `backend/gaf_ai/qa_views.py`: `model_name` 从 `objects.create()` 关键字参数提取为局部变量
- `frontend/src/pages/AI/QAPanel.tsx`: 改用 `askQuestion()` → `/qa/ask/`，不再调用不存在的 `/qa/qa-sessions/{id}/messages/`

#### 2. E2E 测试持久化（`scripts/e2e/scenarios/ai_qa_chat.py`）

将临时测试脚本（`临时验证脚本 (已删除)`）持久化为正式回归测试，注册到 `scripts/e2e/run_all.py`。下次改 LLM 相关代码后可一键回归。

### Y/N 检查清单

| # | 检查项 | Y/N | 说明 |
|:-:|--------|:---:|------|
| 1 | 写 Playwright 测试前，是否 Grep 了前端 store/api 层确认实际调用的端点？ | | Y=继续写测试 / N=先读代码 |
| 2 | API 测试通过后，是否确认 UI 调用的是同一个端点？ | | Y=继续 / N=Grep 前端代码 |
| 3 | 测试失败后，是否先读前端代码再修改测试？ | | Y=正确 / N=不要盲目重试 |
| 4 | 临时测试脚本验证通过后，是否持久化到 `scripts/e2e/scenarios/`？ | | Y=回归覆盖 / N=用完即丢=无回归 |
| 5 | 发现预存 bug 时，是否在当次任务内修复？ | | Y=修复 / N=登记 tech-debt |

### 适用范围

- **触发条件**：任何涉及 Playwright/browser-use E2E 测试的任务
- **特别适用**：测试 UI 功能时，前端组件调用后端 API 的场景
- **不适用**：纯后端 API 测试（不涉及前端代码）

### 关联

- **N135**: 批量重构后浏览器验证 — 本教训是其**测试方法论**层面的补充
- **N129**: 审计 3 棵代码树 — 本教训是"审计前端代码树"在测试场景的应用
- **N126**: 文档诚实标记 — "API 通过"不等于"UI 通过"是类似的诚实问题
- **commit**: `-`（bug 修复）+ `ai_qa_chat.py`（回归测试）

### 复发记录

- 2026-07-11: 首次登记（2 轮 E2E 测试失败后才读前端代码）

---

## N147: Python 新库/typing 使用必须同步添加 import + commit 前端到端验证

**日期**: 2026-07-06
**严重级别**: P0
**commit**: - (引入 bug), - (修复)
**触发原话**: 用户 "继续"（推进 P-004 R37-P2 验证收尾）

### 症状

P-004 R37-P2 commit `-` 添加并行截图功能，使用 `ThreadPoolExecutor(max_workers=4)`
和 `Optional[List[str]]` 类型注解，但忘记在 handler.py 顶部添加对应的 import。

Agent 启动后截图流线程立即抛异常：

```
[AGENT] 收到截图流控制: action=start
[AGENT] 截图流线程已启动
[AGENT] 截图流: 第 1 次异常: name 'ThreadPoolExecutor' is not defined
[AGENT] 截图流: 连续异常过多，停止线程
```

前端收到 0 个 screenshot_frame，设备卡片显示黑屏（无截图）。

更隐蔽的是：即使 `Optional[List[str]]` 的 `List` 也没导入，但因为
`__init__` 中 `Optional[List[str]] = None` 会求值类型注解，理论上应
在 MessageHandler 实例化时抛 `NameError: List`。实际未触发是因为
handler 在截图流线程启动前已实例化（可能是 Python 对某些变量注解
求值时机的小心眼，但无论如何这是定时炸弹）。

### 根因

双重遗漏：

1. **import 遗漏**: commit `-` 在 handler.py 添加了
   - L746: `ThreadPoolExecutor(max_workers=4)` 调用
   - L35: `Optional[List[str]]` 类型注解
   但顶部 import 区没有同步添加：
   - 缺 `from concurrent.futures import ThreadPoolExecutor, as_completed`
   - 缺 `List`（typing import 只有 `Any, Callable, Dict, Optional`）

2. **验证遗漏**: commit 前没有跑端到端验证（启动 agent + 触发截图流），
   只确认了"模块能 import"（`python -c "import handler"` 不报错），
   没确认"功能能运行"（截图流线程实际启动并产出帧）。

### 反模式本质

Python 不像 TypeScript 有编译时 import 检查：

- **TypeScript**: `tsc` 编译时报 "Cannot find name 'X'"，编译失败 → 容易发现
- **Python**: 模块加载时只解析顶部 import，函数体内的 `NameError` 要等
  运行时调用到那一行才暴露。类型注解 `Optional[List[str]]` 在变量赋值
  时会求值（除非 `from __future__ import annotations`）。

更深的反模式是：**"静态检查通过 ≠ 运行时可用"**。
- `python -c "import handler"` 通过 ≠ 截图流工作
- lint 通过 ≠ 功能正常
- 模块加载成功 ≠ 线程内调用成功

### 修复

handler.py 顶部添加 2 个 import：

```python
# L7 新增
from concurrent.futures import ThreadPoolExecutor, as_completed
# L9 加 List
from typing import Any, Callable, Dict, List, Optional
```

### 验证

Playwright E2E（`临时验证脚本 (已删除)`）：

- 登录成功（url=/dashboard）
- 导航 /devices，找到 2 个设备卡片
- 收到 2 个 screenshot_frame（之前 0）
- 图像解码 shape=(864, 1536, 3)，brightness=77.28（之前黑屏）
- 0 console errors, 0 page errors
- agent 日志: `Future 完成: msg_type=screenshot.frame`（截图帧成功发送）
- **无 `ThreadPoolExecutor is not defined` 错误**

### 预防规则

1. **添加新库使用 → 立即检查顶部 import**:
   - 添加 `ThreadPoolExecutor(...)` → `from concurrent.futures import ...`？
   - 添加 `Optional[List[...]]` → typing 有 `List`？
   - 添加 `Tuple/Set/Union/Iterable/Sequence` → typing 覆盖？
   - 添加 `Path(...)` → `from pathlib import Path`？

2. **commit 前端到端验证（不只是启动服务）**:
   - 启动 agent ≠ 截图流工作（截图流要前端触发才启动）
   - 必须触发功能（Playwright E2E 或手动浏览器操作）
   - lint 通过 ≠ 运行时可用

3. **Python 项目 commit 前 ruff/pyflakes 检查**:
   - `ruff check F821` 能发现未定义名称（undefined name）
   - 但前提是 commit hook 配置了 ruff（本项目 pre-commit 未覆盖 agent/）

### 反模式家族

- **N135**: tsc 0 错误 ≠ 前端可用（前端批量重构后浏览器验证）
- **N147**: Python import 通过 ≠ 运行时可用（后端新功能 commit 前端到端验证）— 本教训

两者核心一致：**静态检查通过 ≠ 运行时可用**，但语言和场景不同：
- N135 针对 TypeScript 前端 + 批量重构
- N147 针对 Python 后端 + 新功能

### Y/N 检查清单（commit 前）

| # | 检查项 | Y/N |
|---|--------|-----|
| 1 | 新增库调用（如 `ThreadPoolExecutor`）→ 顶部 import 已添加？ | |
| 2 | 新增 typing 类型（如 `List`/`Tuple`/`Set`）→ typing import 覆盖？ | |
| 3 | 新增类型注解（`Optional[...]`/`Dict[...]`）→ 内部类型已导入？ | |
| 4 | 涉及线程/异步/截图 → 端到端验证触发过功能？ | |
| 5 | `python -c "import module"` 通过 ≠ 功能可用，跑过实际调用？ | |

### 关联

- 引入 bug: commit - (P-004 R37-P2 per-device filter + parallel capture)
- 修复: commit -
- 相关: N135（前端批量重构后浏览器验证）
- 相关: N128（文档状态 3 步验证 — 代码同理需 3 步验证）
- 文件: agent/src/client/handler.py
