---
summary: 文档状态标记/审计 Y/N 矩阵 — 3步验证/审计3棵代码树/Roadmap双向验证
applies_to: [doc-status, audit, roadmap-verification, reflection]
last_updated: 2026-07-11
source: Split from yn-matrices.md (Phase 4 Task 4.2)
---

## §3 honest-status — 文档状态标记/审计

> **注**: N126 文档诚实标记的 Y/N 矩阵已包含在 §1 workflow ⑳ (N124/N125/N126 合并矩阵) 中, 此处不再重复。本节聚焦 N128/N129/N130 文档状态验证系列。

### ㉑ N128 文档状态 3 步验证 Y/N 矩阵 (R34 闭环 — N128 加项)

> **触发条件** (任意一条即触发):
> - AI 更新 pending-roadmap.md / GAF-optimal-solution.md / completed-features.md 状态标记 (✅/🔧/❌)
> - AI 在文档中写 "✅ 已完成 (N tests)" 或类似带测试计数的标记
> - AI 审计发现虚报 ✅ (N14/N126/N128 同根因第三次)
> - AI 调研某功能"现状"准备标记状态

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | Glob 查文件是否存在 (如 `GAF/backend/**/verify*.py`) | | `Glob` 工具 |
| 2 | Grep 查类/函数是否存在 (如 `class VerifyHandler`) | | `Grep` 工具 |
| 3 | pytest 查测试是否真的通过 (如 `pytest tests/test_verify_handler.py -v`) | | `RunCommand` 跑 pytest |
| 4 | 测试计数真实 (文档写 "39 tests" → 实际 pytest 输出 39 passed) | | 对比 pytest 输出 |
| 5 | 虚报修正加 "(N128 审计)" 注释, 便于追溯 | | `grep "(N128 审计)"` |

**AI 必做 (N128 硬规则)**:
- ✅ 文档状态 ✅ 标记必须跑 3 步验证 (Glob + Grep + pytest), 3 步全过才能标 ✅
- ✅ 测试计数必须真实, 禁止捏造 (如 "30 tests 全通过" 必须有对应 test_*.py 文件)
- ✅ 虚报修正加 "(N128 审计)" 注释, 便于追溯
- ✅ 任一步失败必须标 ❌ 未实现 / 🔧 部分实现, 不能标 ✅
- ❌ NEVER 凭印象标 ✅, 必须有代码文件 + 测试文件作为证据
- ❌ NEVER 捏造测试计数 (禁止在文档中写 "N tests 全通过" 而没有对应 test_*.py)
- ❌ NEVER 跳过代码级验证 (更新状态时必须跑 3 步验证)

**同根因家族**: N14 (假实现) + N126 (5 false positives) + **N128 (6/7 false positives + fabricated test counts)** —— 同根因 (状态标记不诚实, 第三次重现)

### ㉒ N129 审计范围 3 棵代码树 Y/N 矩阵 (R34 闭环 — N129 加项)

> **触发条件** (任意一条即触发):
> - AI 审计某功能"现状"准备标记状态 (✅/🔧/❌)
> - AI 跑 Glob/Grep 搜代码文件/类/函数
> - AI 调研某模块是否存在
> - N128 假阳性 (虚报 ✅) 后的反向验证 (防 N129 假阴性)

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 审计前先 `LS GAF/` 列出所有子目录, 确认搜索范围 | | `LS` 工具 |
| 2 | Glob/Grep 覆盖 `GAF/backend/` (Django backend) | | `Glob`/`Grep` 工具 |
| 3 | Glob/Grep 覆盖 `GAF/agent/` (standalone agent module) | | `Glob`/`Grep` 工具 |
| 4 | Glob/Grep 覆盖 `GAF/frontend/` (React frontend, 如相关) | | `Glob`/`Grep` 工具 |
| 5 | 不假设所有后端代码在 `GAF/backend/` (自动化引擎在 `GAF/agent/`) | | 检查假设 |

**AI 必做 (N129 硬规则)**:
- ✅ 审计前先 `LS GAF/` 列出所有子目录, 确认 3 棵代码树
- ✅ Glob/Grep 必须覆盖 `GAF/backend/` + `GAF/agent/` + `GAF/frontend/` (如相关)
- ✅ 假阴性 (误判已实现为未实现) 与假阳性 (虚报 ✅) 一样严重, 都需避免
- ❌ NEVER 假设所有后端代码在 `GAF/backend/` (自动化引擎在 `GAF/agent/`)
- ❌ NEVER 只搜一个子目录就下结论
- ❌ NEVER 跳过 `LS GAF/` 直接开搜

**GAF 3 棵代码树**:
- `GAF/backend/` — Django REST API + 业务逻辑
- `GAF/agent/` — Standalone automation agent (src/core/, src/devices/, src/recognition/, src/engine/)
- `GAF/frontend/` — React SPA

**同根因家族**: N14 (假实现) + N126 (5 false positives) + N128 (6/7 false positives) + **N129 (6/7 false negatives, audit scope too narrow)** + **N130 (roadmap 假阴性 "前端 0%" 但代码已实现)** —— 同根因 (验证不充分, N129/N130 方向相反: 假阴性 vs 假阳性)

### ㉓ N130 Roadmap 双向验证 Y/N 矩阵 (R34 闭环 — N130 加项)

> **触发条件** (任意一条即触发):
> - AI 读 pending-roadmap.md 准备标记任务状态 (✅/🔧/❌)
> - AI 看到 roadmap 标 "✅ 已完成" 准备跳过该任务
> - AI 看到 roadmap 标 "❌ 未实现" / "🔧 代码存在" 准备实施该任务
> - N128/N130 假阴性/假阳性后双向验证

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 当 roadmap 标 ✅ → Glob 查文件是否存在 | | `Glob` 工具 |
| 2 | 当 roadmap 标 ✅ → Grep 查类/函数是否存在 | | `Grep` 工具 |
| 3 | 当 roadmap 标 ✅ → Read 实际代码确认非 stub | | `Read` 工具 |
| 4 | 当 roadmap 标 ❌/🔧 → Glob 查文件是否真的不存在 | | `Glob` 工具 (N130 新增) |
| 5 | 当 roadmap 标 ❌/🔧 → Grep 查关键符号是否真的不存在 | | `Grep` 工具 (N130 新增) |
| 6 | 当 roadmap 标 ❌/🔧 → Read 候选文件确认确实未实现 | | `Read` 工具 (N130 新增) |

**AI 必做 (N130 硬规则 — 双向验证)**:
- ✅ 当 roadmap 标 ✅ → 必须验证代码存在 (N128 方向)
- ✅ 当 roadmap 标 ❌/🔧 → 必须验证代码确实不存在 (N130 方向)
- ✅ 两个方向都需要 3 步验证 (Glob + Grep + Read)
- ❌ NEVER 信任 roadmap 状态而不验证代码 (无论 ✅ 还是 ❌)
- ❌ NEVER 假设 "前端 0%" 意味着前端代码不存在 (N130 教训)

**N128 家族历史** (4 次重现):
| 重现 | 日期 | 虚假方向 | 现实 |
|:---:|------|---------|------|
| N14 | earlier | 假 ✅ | 功能未实现 |
| N126 | — | 假 ✅ + 捏造测试数 | 6/7 假 |
| N128 | — | 假 ❌ (只搜 backend/) | 全部已实现 (in agent/) |
| **N130** | — | 假 ❌ ("前端 0%") | 前端 100% 已实现 |

**模式**: Roadmap 与代码状态漂移, 无论方向 (假阳性 OR 假阴性)。

### ㉔ N157 AI memory 文档虚构实现 Y/N 矩阵 (闭环)

> **触发条件** (任意一条即触发):
> - AI 要写/更新 AI memory 文档 (游戏档案、架构文档、API 文档等)
> - AI 读取 AI memory 文档后基于其内容执行操作 (搜路径、引用文件等)
> - 文档中描述的路径/文件/类型/成熟度未经实际代码验证

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 写 AI memory 文档前, Glob/Read 了实际代码/资源目录？ | | `Glob("<path>/**")` 或 `Read(<file>)` |
| 2 | 文档中写的路径, 验证过存在？ | | `Glob("<path>")` 非空 |
| 3 | 文档中写的文件名, 验证过存在？ | | `Glob("**/<filename>")` 非空 |
| 4 | 文档中写的 API/节点类型, Grep 过实际代码？ | | `Grep("<type>" agent/src/ backend/)` 非空 |
| 5 | 标 ✅ 前, 有验证证据 (测试通过/截图/pytest)？ | | N128 3 步验证 |
| 6 | 读 AI memory 文档后, 验证了关键路径/文件存在？ | | `Glob("<doc提到的路径>")` 非空 |
| 7 | 文档生成后, 实际代码变更时同步更新文档？ | | 代码改了文档也要改 |

**AI 必做 (N157 硬规则)**:
- ✅ **写 AI memory 文档前, 必 Glob/Read 实际代码/资源目录**: 不凭空写"看起来合理"的路径/文件名/类型
- ✅ **读 AI memory 文档后, 验证关键路径/文件存在**: `Glob("<doc提到的路径>")` 非空才信任
- ✅ **文档描述"实际怎么做"**: 不描述"打算怎么做"
- ✅ **标 ✅ 必有验证证据**: N128 3 步验证 (Glob + Grep + pytest/截图)
- ❌ NEVER 描述"打算怎么做"为"实际怎么做"
- ❌ NEVER 标 ✅ 无验证证据
- ❌ NEVER 信任 AI memory 文档的路径/文件名而不验证

**反模式示例**:
```
❌ BAD (实际发生):
  1. 生成 .ai-memory/games/browndust-ii/common-tasks.md
  2. 凭空写 assets/templates/browndust-ii/ (没 Glob 实际路径)
  3. 凭空写 btn_battle.png (没 Glob 实际文件名)
  4. 凭空写 click_template 节点类型 (没 Grep 实际代码)
  5. 标 ✅ 98% (没跑过任何测试)
  → 后续 AI 搜 assets/templates/browndust-ii/ → 空 → 报告"资源不存在"

✅ GOOD:
  1. Glob("resources/**") → 发现 resources/BrownDust-II/
  2. Glob("resources/BrownDust-II/templates/**") → 发现 67 个中文 PNG
  3. Read("resources/BrownDust-II/pipelines/login.json") → 发现 template_match 节点
  4. 标 🔧 待验证 (没跑过 e2e)
  → 后续 AI 搜 resources/BrownDust-II/ → 找到 → 正确引用
```

**N126 家族历史** (5 次重现):
| 重现 | 日期 | 虚假方向 | 现实 |
|:---:|------|---------|------|
| N14 | earlier | 假 ✅ | 功能未实现 |
| N126 | — | 假 ✅ + 捏造测试数 | 6/7 假 |
| N128 | — | 假 ❌ (只搜 backend/) | 全部已实现 (in agent/) |
| N130 | — | 假 ❌ ("前端 0%") | 前端 100% 已实现 |
| **N157** | — | 假文档 (虚构实现) | 路径/文件名/类型/成熟度全错 |

**模式**: N126 家族从"标记错误"升级到"整个文档虚构" (N157)。

---

