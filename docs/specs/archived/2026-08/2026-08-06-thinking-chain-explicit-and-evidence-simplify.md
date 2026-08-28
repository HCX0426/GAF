---
spec: 2026-08-06-governance-overhaul
title: GAF 治理体系大修 — 思维链外显 + Evidence 简化 + 软环节硬化 + 生命周期管理
status: completed
created: 2026-08-06
completed: 2026-08-06
estimated_effort: 12-14 hours
risk: medium
---

# GAF 治理体系大修 — 思维链外显 + Evidence 简化 + 软环节硬化 + 生命周期管理

## 背景

### 现状量化

| 指标 | 数值 | 评估 |
|------|------|------|
| Lessons 总数 | 59 个 .md 文件 | 膨胀严重，AI 读不完 |
| Evidence 累计文件 | 218 个 | active 为 0，全在 archived |
| failure-modes.md 索引 | 169 行 / 55+ N## | 太长，AI 不主动读 |
| Lessons 最大文件 | 635 行 (N191) | 单文件过长，AI 不会全读 |
| Evidence 实际读取率 | < 5% | 只有 `--query` 命中才会加载 |
| L2 硬加载文件数 | 2 个 | ai-operating-handbook + tech-stack |

### 11 个已识别问题（按严重性排序）

#### P0 — 核心故障

**问题 1：Evidence 管道写了没人读**

5 层沉淀管道中，只有 L0 hardrules（env-hardrules.md）真正在 AI 启动时被加载。其余 4 层（evidence → lessons → failure-modes）都是"可选读取"，实际读取率 < 5%。

- Evidence 每个任务都写（~30 行），但 AI 新对话不自动读 evidence 目录
- Lessons 平均 ~120 行，但只有 `--query` 命中才会加载
- failure-modes.md 有 55+ 条，AI 启动时不加载它
- **根因**：信息藏在 L3 层，AI 不会主动去读

**问题 2：AI 思维链完全隐藏**

AI 的实际推理过程（走了哪个分支、匹配了哪些症状、为什么这么选）是隐藏的。Evidence 记录"做了什么"（post-hoc），不是"怎么想的"（过程）。出问题时无法回溯 AI 的决策路径。

#### P1 — 高影响软环节

**问题 3：关键治理检查是"软执行"**

决策树和反思清单很完善，但 AI 是否严格遵循仍是"自觉"层面：
- "是否真跑了七维度评估" → 仅靠 post-commit WARNING（exit 0），约束力为零
- "是否真跑了双调试视角 7 项" → AI 声称跑了但无法验证
- "是否真加载了 L2 必读文件" → 反思矩阵 [L2] 标记 N，但不阻塞 commit
- **根因**：过程检查仅靠 AI 自觉，pre-commit hook 只检查结构化产物

**问题 4：规模分级判定依赖 AI 自判**

`project_rules.md` 定义了小/中/大修改三级（如 "50-500 行 diff = 中修改"），但：
- `check_big_change.py` 能客观判定"大修改"，但中/小修改的豁免判定无脚本
- AI 自判"这是小修改，可以不跑七维度" → 可能误判为大修改浪费时间，或误判为小修改跳过必要检查
- **根因**：中/小修改的豁免判定是纯手动流程

**问题 5：规则文档"5 层跳转"开销**

AI 执行一个任务时，可能需要跨越 4-5 层文档：
```
L0 env-hardrules.md → L2 ai-operating-handbook.md → L3 yn-matrices/_workflow.md → lessons/N191-checklist.md
```
对 AI 上下文预算造成压力，经常导致"为了查一个规则跳了 5 层，上下文用完了"。

#### P2 — 中影响效率问题

**问题 6：L3 循环被动触发条件模糊**

L3 循环（任务间持续评估）的触发依赖 AI 判断用户意图：
- "强触发"词：循环执行 / L3 循环 / 按优先级接修
- "弱触发"词：继续 / 评估一下
- 触发词列表是静态的，边界情况下容易误判

**问题 7：Evidence → Lesson 沉淀的自动化不足**

Evidence 沉淀的两个触发点（启动时触发点 1 + 任务结束触发点 3）都是"AI 主动检查"：
- 无 pre-commit hook 强制验证"同 topic evidence ≥ 2 是否已沉淀为 lesson"
- AI 可能忘记检查 → evidence 堆积但不沉淀

**问题 8：症状 → 知识点映射是"软触发"**

映射表定义了"AI 看到关键词时主动加载对应知识点"，但触发依赖 AI 自身理解：
- AI 是否能在复杂对话中准确识别"schema 重构"场景？
- AI 是否能在看到"测试慢"时主动加载 N194？
- 没有脚本强制映射

#### P3 — 低影响治理债务

**问题 9：Pre-commit hook 的"二阶段"问题**

ESLint/Prettier/Ruff/Mypy 被放到 `manual` stage（本地 commit 不阻塞）：
- AI 提交的代码可能有 lint 错误，只能 CI 阶段发现
- 这是"开发效率 vs 代码质量"的取舍，但 AI 主导开发模式下应更严格

**问题 10：L1 教训"真二分制"判定依赖 AI**

`project_rules.md` §6.2 定义了 L0（一次性事件）vs L1（可复用经验）+ L1-小/中/大子分级，但判定过程是 AI 自问自答（"问 2 个问题判定级别"），没有脚本强制。

**问题 11：规则执行率缺乏量化追踪**

`env-hardrules.md` 提到"治理形式化（无 evidence + 执行率 < 10%）"和"AI 必需治理（有 evidence + 执行率 > 50%）"的区分，但执行率追踪完全依赖 AI 自觉记录，没有自动化统计。

#### P2 — 长期可持续性问题

**问题 12：文件长期膨胀无控制**

治理体系中的所有文件都缺乏硬指标约束，长期运行后必然膨胀：
- cheatsheet.md 条目无限增长，无过期检测
- session-traces/ 无限堆积，无自动清理
- lessons/ 归档后永不清理
- failure-modes.md 的 Dormant/Retired 条目永远不删除
- **根因**：没有任何文件级别的行数/条目数硬上限

**问题 13：长期不触发的规则无退役机制**

某些治理规则/扫描模式在代码问题解决后就再也不会触发，但仍然：
- 消耗 pre-commit hook 检查时间
- 消耗 AI 加载上下文
- 在 failure-modes.md 中占用索引位置
- 扫描模式消耗 grep 时间
- **根因**：只有"新增"机制，没有"退役"机制。规则一旦加入就永不退出

---

## 目标

1. **思维链外显**：让 AI 的决策路径可追溯、可观测
2. **Evidence 简化**：将 5 层沉淀管道精简为 2 层，降低 AI 负担
3. **软环节硬化**：将依赖 AI 自觉的关键检查升级为脚本强制 / pre-commit hook 验证
4. **信息必达**：确保关键信息在 L2 层面被 AI 主动加载，消除"写了没人读"
5. **分级自动化**：小/中/大修改的分级判定脚本化，消除 AI 自判
6. **执行率可量化**：自动追踪每条硬约束的实际执行情况

---

## 设计方案

### 方案一：思维链外显（解决问题 2）

#### 1.1 思维链追踪日志（Thinking Trace）

**做法**：每个任务结束后，AI 在 `.ai-memory/session-traces/` 写入追踪日志。

**日志格式**（每会话 1 个文件，按 session_id 命名）：

```markdown
# Session Trace: <session_id>
Date: 2026-08-06T10:30:00

## Task 1: <task_description>
- **task_type**: bug_fix
- **决策路径**:
  - step_1: 判定为 bug_fix（匹配关键词: "fix", "error", "报错"）
  - step_2: 加载 context（failure-modes.md, error-codes.md）
  - step_3: `--query "pipeline timeout"` → 命中 N194
  - step_4: 跑 systematic-debugging → 定位根因
  - step_5: 修复 + 写 evidence
  - step_6: 跑 verification-before-completion
- **症状匹配**: [pytest 慢 / django setup]
- **执行的检查**: 双调试视角 A1-A7 (7 项), 七维度评估 (7 项)
- **关键决策**: "选择禁用 pytest-django 插件 (-p no:django)"
- **产出**: evidence (1 份)

## Task 2: ...
```

**约束**：
- 单文件上限 200 行
- 每会话最多 1 个 trace 文件
- 自动保留最近 20 个会话，超过自动清理
- **纳入 pre-commit hook**（软检查，WARNING 不阻塞 — 详见方案三）

#### 1.2 关键决策点内联标注

在对话中，AI 在关键决策点主动用结构化标签标注：

```
[🧭 决策: bug_fix 分支] 匹配关键词 "fix" + "报错", 加载 gaf-reflect-and-evolve
[🔍 症状: schema 重构] 匹配 N191, 加载数据流全链路扫描清单
[✅ 验证: 双调试视角 A7 项全部通过]
```

**约束**：
- 仅 4 种场景标注：task_type 判定、症状匹配、反思完成、验证完成
- 每任务最多 4 个标注
- 标注格式固定，方便机器解析

#### 1.3 思维链 vs 隐私

思维链追踪日志记录**决策路径**，不是完整的内部推理：
- ✅ 记录："选择了 bug_fix 分支，因为用户说'fix' + '报错'"
- ❌ 不记录：完整 chain-of-thought 推理过程

---

### 方案二：Evidence 简化（解决问题 1 + 问题 5）

#### 2.1 简化后的管道

```
简化前 (5 层):
  evidence(3步) → active/ → promotion(≥2同topic) → lessons/ → failure-modes.md → L0 hardrules

简化后 (2 层):
  发现问题 → 写入 单一备忘文件 (.ai-memory/ai-cheatsheet.md)
           → L2 硬加载 (ai-operating-handbook.md 引用)
```

#### 2.2 ai-cheatsheet.md 结构与写入规则

**文件**: `.ai-memory/ai-cheatsheet.md`（单文件，L2 硬加载）

```markdown
# GAF AI Cheat Sheet

## 环境与命令
- conda gaf: `D:\code\environment\conda\envs\gaf\python.exe` (3.11.15)
- 启动: `scripts/gaf_services.ps1 start`
- Agent 测试: `... -p no:django -o addopts=""` (2.5min vs 2h)

## Shell (PowerShell)
- 禁止 heredoc `<<EOF` / `&&` / `||`
- git commit 用多 `-m` flag, 禁用 `-F`
- 禁止 Unix 命令: head/tail/grep → PowerShell 等价

## 跨层约束
- URL 版本号从 `GAF_API_PREFIX` 读, 禁止硬编码
- Schema 改后必跑数据流全链路扫描 (7 项)
- 任务中发现的问题归属当前任务, 禁止抛用户

## 常见坑
- pytest-django 强制 django.setup(): 加 `-p no:django`
- Conda `run` 不支持多行 -c: 写临时 .py
- ROI 子图坐标必须加回原点偏移
- pre-commit hook 失败不要盲目 stash
```

**关键设计决策**：

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 文件数量 | 1 个 | AI 每次对话都能读完 |
| 加载时机 | L2 硬加载 | 必读，不跳过 |
| 每条长度 | 1-3 行关键点 | 速记，非详细文档 |
| 清理策略 | AI 每 2 周评审 (>150 行强制) | 保持精简 |
| 写入时机 | 任务结束时 AI 判定有新知识点时 | 非每任务都写 |
| pre-commit hook | 不强制 | 降低 commit 时间 |

#### 2.3 现有 59 个 Lessons 的迁移

| 阶段 | 内容 | 操作 |
|------|------|------|
| Phase 1 | 提取高频 N## 要点 | 写入 cheatsheet.md |
| Phase 2 | 评估剩余 lessons | 保留高价值为 L3 深度参考，其余归档 |
| Phase 3 | 精简 failure-modes.md | 55+ → ≤ 20 条 |

**Lessons 保留标准**（满足任一）：
1. trigger_count ≥ 3（高频引用）
2. 涉及跨系统契约（schema/URL/API 协议）
3. 含独特诊断流程/脚本
4. cheatsheet 条目需要详细背景支撑

**迁移后的分层**：

```
L0 (system prompt):  env-hardrules.md (不变)
L2 (硬加载):         ai-operating-handbook.md + tech-stack.md + ai-cheatsheet.md (新增)
L3 (按需):           lessons/ (≤ 15 个深度参考) + failure-modes.md (≤ 20 条精简版)
```

#### 2.4 简化后的 Evidence 机制

| 项目 | 简化前 | 简化后 |
|------|--------|--------|
| 每任务写 evidence | 必写 3 步 | 仅在出错/发现新坑时写 |
| 结构 | 3 步 (~30 行) | 2 步 (~10 行) |
| 去向 | 5 层管道流转 | 直接评估 → cheatsheet 追加 / 不写 |
| pre-commit | evidence completeness 强制 | 仅 AI 自决是否需要写 |

---

### 方案三：软环节硬化（解决问题 3 + 问题 7 + 问题 8）

#### 3.1 七维度评估 + 双调试视角的 pre-commit 验证

**当前问题**：AI 声称跑了七维度评估 / 双调试视角，但无法验证。

**解决方案**：将 `select_reflection_checks.py` 的输出纳入 pre-commit hook 验证。

**做法**：
1. `select_reflection_checks.py` 在选完检查项后，输出 `_reflection_checks.json`：
```json
{
  "task_type": "bug_fix",
  "diff_lines": 230,
  "selected_checks": {
    "seven_dim": ["代码正确性", "可测试性", "可维护性"],
    "dual_debug": ["A1", "A2", "A3", "A4", "A5", "A6", "A7"]
  },
  "ai_confirmation": {
    "seven_dim_done": true,
    "dual_debug_done": true,
    "timestamp": "2026-08-06T10:30:00"
  }
}
```

2. `gaf_governance_batch.py` 新增 R9 规则：
   - 读取 `_reflection_checks.json`
   - 校验 `ai_confirmation.seven_dim_done == true`（中/大修改时）
   - 校验 `ai_confirmation.dual_debug_done == true`（涉及代码/前端修改时）
   - 校验 `timestamp` 在当前会话内（防止复用旧文件）
   - 未通过 → **WARNING + 阻塞 commit**（从软检查升级为硬检查）

**分级规则**：
- 小修改（< 50 行 diff）：仅校验 `dual_debug_done`
- 中修改（50-500 行）：校验 `seven_dim_done` + `dual_debug_done`
- 大修改（> 500 行）：校验全部 + 强制双写期评估

#### 3.2 思维链追踪日志的 pre-commit 验证

**做法**：`gaf_governance_batch.py` 新增 R10 规则：
- 校验 `.ai-memory/session-traces/<session_id>.md` 是否存在
- 校验 trace 包含必要字段（task_type + 决策路径 + 执行的检查）
- 未通过 → **WARNING 不阻塞**（纯诊断用途，不强制）

#### 3.3 症状 → 知识点映射的硬触发

**当前问题**：映射表定义了主动加载，但触发依赖 AI 自觉。

**解决方案**：在 `gaf_init.sh` 步骤 4.5 中追加症状匹配扫描：

```bash
# 新增步骤 4.6: 症状关键词硬匹配
# 扫描当前工作目录的 git diff, 匹配硬编码模式
python scripts/scan_hardcoded_patterns.py --diff-only
# 输出:
#   [HIT] 发现硬编码 "/api/v2" → 加载 N197 (URL 归一化)
#   [HIT] 发现 schema 字段 "action_type" → 加载 N191 (Schema 归一化)
```

**扫描模式**（与 ai-operating-handbook.md Part 1 映射表对齐）：
| 硬编码模式 | 对应 N## | 自动加载 |
|-----------|---------|---------|
| `/api/v2` | N197 | ✓ |
| `action_type\|next_step\|retry_interval` | N191 | ✓ |
| `conda run -n gaf\|python manage.py` | N188 | ✓ |
| `<<EOF\|\|\|\|\&\&` | N190 | ✓ |
| `time.sleep\|sleep(` | N196 | ✓ |
| `grep\|head\|tail\|sed\|awk` | N190 | ✓ |

---

### 方案四：分级判定自动化（解决问题 4 + 问题 10）

#### 4.1 中/小修改判定脚本

**新增脚本**：`scripts/check_change_scope.py`

**用法**：
```bash
python scripts/check_change_scope.py
```

**输出**：
```json
{
  "scope": "medium",
  "diff_lines": 230,
  "files_changed": 8,
  "apps_affected": ["gaf_core", "gaf_ai", "frontend"],
  "db_migration": false,
  "api_contract_changed": false,
  "required_checks": {
    "seven_dim": true,
    "dual_debug": true,
    "l3_scan": false
  }
}
```

**判定标准**（与 project_rules.md §0 对齐）：
```python
if diff_lines > 1500 or apps_affected > 5 or db_migration or api_contract_changed:
    scope = "big"       # 强制走 N151 5 步流程 + L3 扫描
elif diff_lines > 50 or apps_affected > 2:
    scope = "medium"    # 强制七维度 + 双调试视角
else:
    scope = "small"     # 仅双调试视角 + 验证
```

**集成**：pre-commit hook R11 规则调用此脚本，校验 scope 等级与 AI 声明的 `required_checks` 一致。

#### 4.2 L0/L1 分级判定脚本

**新增脚本**：`scripts/check_lesson_level.py --topic <topic>`

**用法**：
```bash
python scripts/check_lesson_level.py --topic "schema-unification"
```

**输出**：
```json
{
  "level": "L1",
  "sub_level": "medium",
  "reasoning": "topic 涉及跨系统契约(schema), 可复用经验",
  "promotion_target": "cheatsheet.md + lessons/L3-reference"
}
```

**判定逻辑**（与 project_rules.md §6.2 对齐）：
- 问题是否可在其他项目复现？ → 是 = L1，否 = L0
- L1 子分级：影响模块数 × 跨进程数 × 复杂度

---

### 方案五：执行率量化追踪（解决问题 11）

#### 5.1 治理执行率统计脚本

**新增脚本**：`scripts/governance/execution_rate.py`

**做法**：
1. 每完成 1 个任务，AI 在 thinking trace 中记录执行了哪些检查
2. 脚本扫描 `.ai-memory/session-traces/` 累积数据
3. 按规则统计执行率：

```
规则 N188 (conda 环境): 最近 30 天 12/12 任务执行 → 100% (有效治理)
规则 N190 (PowerShell): 最近 30 天 8/12 任务执行 → 67% (有效治理)
规则 N191 (Schema 归一化): 最近 30 天 2/12 任务执行 → 17% (形式化治理)
规则 N194 (pytest 环境): 最近 30 天 12/12 任务执行 → 100% (有效治理)
规则 N197 (URL 归一化): 最近 30 天 0/12 任务执行 → 0% (形式化治理)
```

**触发**：每 2 周评审时自动运行，标记"形式化治理"条目（执行率 < 50%）供人工审核。

---

### 方案六：Pre-commit Hook 二阶段优化（解决问题 9）

#### 6.1 将 lint hooks 升级到 pre-commit stage

**当前**：
```yaml
manual:  # 本地 commit 不阻塞
  - eslint
  - prettier
  - ruff
  - mypy
```

**目标**：
```yaml
pre-commit:  # 本地 commit 阻塞
  - gaf_governance_batch  # 治理检查 (11 条规则)
  - eslint-fix            # 前端 lint 自动修复
  - ruff-check-fix        # 后端 Python lint 自动修复
manual:
  - prettier-check        # 格式化检查 (可手动跳过)
  - mypy                  # 类型检查 (慢，按需)
```

**分级策略**：
- `eslint --fix` 和 `ruff --check-fix`：有自动修复能力，升级到 pre-commit
- `prettier` 和 `mypy`：纯检查/无自动修复，保留在 manual（太慢）
- **核心原则**：有自动修复能力的 hook 升级到 pre-commit，纯检查的保留 manual

---

### 方案七：生命周期管理 — 膨胀控制 + 自动退役（解决问题 12 + 问题 13）

> **背景**：治理体系引入新机制后，如果没有生命周期管理，必然出现两类长期退化：
> 1. **膨胀**：cheatsheet.md 条目无限增长、session-traces 堆积、lessons 永不归档
> 2. **僵尸**：某些 N## 规则/扫描模式长期零触发但仍在消耗上下文和检查时间

#### 7.1 三态生命周期模型

所有治理实体（规则、lessons、扫描模式、cheatsheet 条目）遵循统一的三态生命周期：

```
┌──────────┐  零触发 90 天   ┌──────────┐  人工/自动归档   ┌──────────┐
│  Active  │ ──────────────→ │  Dormant │ ──────────────→ │ Archived │
│ (活跃)   │                 │ (休眠)   │                 │ (归档)   │
└──────────┘                 └──────────┘                 └──────────┘
     ↑                             ↑                             │
     │       重新触发/人工激活       │                             │
     └─────────────────────────────┘                             ↓
                                                            永久删除
                                                            (保留引用索引)
```

| 状态 | 含义 | AI 行为 |
|------|------|---------|
| **Active** | 活跃使用中 | 正常加载、检查、统计执行率 |
| **Dormant** | 长期未触发，保留但不主动加载 | AI 搜索时仍可命中，pre-commit 检查跳过 |
| **Archived** | 已归档，不再主动维护 | 仅保留引用索引，定期删除 |

#### 7.2 Cheatsheet.md 膨胀控制

**硬指标**：

| 指标 | 警告阈值 | 强制阈值 | 触发动作 |
|------|----------|----------|----------|
| 文件行数 | > 120 行 | > 150 行 | 自动标记过时条目 |
| 主题分组数 | > 8 组 | > 10 组 | 合并相关分组 |
| 条目数 | > 40 条 | > 50 条 | 标记 last_used > 30 天的条目 |

**条目级过期检测**：

cheatsheet.md 每条目增加 frontmatter 元数据：
```markdown
## 常见坑
<!-- meta: {last_used: "2026-08-01", trigger_count: 5, expire_days: 30} -->
- pytest-django 强制 django.setup(): 加 `-p no:django` 禁用
```

**清理逻辑**（由 `scripts/governance/cleanup_cheatsheet.py` 执行）：
```
对每条目:
  if last_used > expire_days 天:
    标记为 [过时] (行首加 ~)
    在下一次 AI 加载时提醒
    如果连续 2 次提醒仍未使用 → 归档到 cheatsheet-archived.md
```

**集成**：`gaf_init.sh` 步骤 4.7 追加 cheatsheet 清理检查（WARNING 不阻塞）。

#### 7.3 N## 规则自动退役

**退役触发器**（满足任一即触发评估）：

| 触发器 | 条件 | 动作 |
|--------|------|------|
| 零触发期 | 连续 90 天无任何任务触发该 N## | 标记候选退役 |
| 低执行率 | 最近 30 天执行率 < 10% | 标记候选退役 |
| 代码消失 | 规则对应的代码模式已在 git diff 中消失 | 标记候选退役 |
| 重复规则 | 两个 N## 规则覆盖相同场景 | 合并为一条 |

**退役流程**（由 `scripts/governance/retire_rules.py` 执行）：
```
1. 扫描 execution_rate.py 历史数据
2. 识别候选退役规则 (零触发期/低执行率/代码消失)
3. 生成退役报告:
   N197 (URL 归一化): 90 天零触发, 代码已改用环境变量 → 建议退役
   N191 (Schema 归一化): 执行率 8%, 仅 1/12 任务触发 → 建议降级为 Dormant
4. 人工审批 (AI 在会话中展示报告, 用户确认)
5. 执行退役:
   - Active → Dormant: failure-modes.md 标记 [DORMANT], pre-commit 跳过该检查
   - Dormant → Archived: 移至 archived-lessons.md, 保留索引
   - Archived → 永久删除: 保留 N## 编号占位 (防止编号冲突), 删除全文
```

**节奏**：每 2 周评审时自动运行（与 execution_rate.py 同步）。

#### 7.4 L3 Lessons 自动退役

**退役标准**（满足任一）：

| 条件 | 说明 |
|------|------|
| 90 天无 `--query` 命中 | 从未被 AI 搜索加载过 |
| trigger_count = 0 | failure-modes.md 中从未记录触发 |
| 文件大小 > 300 行 | 过长，AI 不会全读 |

**退役流程**：
```
Active lesson → Dormant: 移至 .ai-memory/lessons/_dormant/
Dormant lesson → Archived: 移至 docs/archived/lessons/, failure-modes.md 标记 [ARCHIVED]
```

**Lessons 保留上限**：L3 活跃 lessons ≤ 15 个（硬上限），超过时强制触发退役评估。

#### 7.5 硬编码扫描模式退役

**扫描模式生命周期**：

每条扫描模式在 `scan_hardcoded_patterns.py` 中维护 `last_hit` 元数据：
```python
SCAN_PATTERNS = [
    {"pattern": r"/api/v2", "n_id": "N197", "last_hit": "2026-08-01", "hit_count": 3},
    {"pattern": r"action_type", "n_id": "N191", "last_hit": "2026-06-15", "hit_count": 0},
    # N191: 90 天零命中 → 候选退役
]
```

**退役条件**：`hit_count == 0` 且 `last_hit` 距今 > 90 天 → 从扫描列表中移除。

**注**：扫描模式退役不代表对应的 N## 规则退役。可能代码中确实不再有硬编码（问题已解决），但规则本身仍然有效。

#### 7.6 Session Traces 膨胀控制

**三级保留策略**：

| 保留等级 | 保留条件 | 保留数量 | 清理动作 |
|----------|----------|----------|----------|
| 活跃 | 最近 20 个会话 | 20 个 | 自动清理超出 |
| 压缩归档 | 20-100 个会话 | 80 个 | 压缩为 `.trace-summary.md` (仅保留 task_type + 决策摘要) |
| 永久删除 | > 100 个会话 | — | 永久删除 |

**清理脚本**：`scripts/governance/cleanup_traces.py`
- 每次新 trace 写入时自动运行
- 超过 20 个 → 压缩最旧的到 summary
- 超过 100 个 → 永久删除最旧的

#### 7.7 退役总览脚本

**新增脚本**：`scripts/governance/lifecycle_report.py`

**用法**：
```bash
python scripts/governance/lifecycle_report.py
```

**输出**（每 2 周评审时使用）：
```
=== GAF 治理体系生命周期报告 ===

【Cheatsheet 状态】
  总行数: 87 行 (OK, < 120 行警告阈值)
  过时条目: 3 条 (last_used > 30 天)
  → 建议归档: Shell heredoc (30 天未使用)

【N## 规则状态】
  活跃: 52 条
  休眠: 3 条 (N155, N162, N178 — 90 天零触发)
  归档: 0 条
  → 建议退役: N178 (URL 拼接版本号, 代码已改用环境变量)

【Lessons 状态】
  活跃: 12 个 (OK, ≤ 15 上限)
  休眠: 8 个 (90 天无 --query 命中)
  归档: 39 个

【扫描模式状态】
  活跃模式: 6 条
  零命中模式: 1 条 (N191 action_type — 60 天零命中)
  → 建议移除: action_type 扫描模式

【Session Traces】
  活跃: 20 个
  压缩归档: 45 个
  永久删除: 78 个
```

---

## 实施步骤

### Phase 1: 思维链外显 + 软环节硬化（~3h）

**Step 1.1: 创建思维链追踪日志机制**
- 在 `gaf-orchestrator/SKILL.md` 闭环步骤追加每任务写 thinking trace
- 在 `ai-operating-handbook.md` 追加 trace 说明
- 创建 `.ai-memory/session-traces/` 目录 + 清理脚本

**Step 1.2: 定义关键决策点内联标注格式**
- `ai-operating-handbook.md` Part 1 追加「决策点标注规范」
- 定义 4 种标注类型

**Step 1.3: 添加 pre-commit 验证（R9 + R10）**
- `gaf_governance_batch.py` 新增 R9（反思检查验证）+ R10（trace 验证）
- 创建 `_reflection_checks.json` 输出规范

**Step 1.4: 添加硬编码模式扫描（R11）**
- 新增 `scripts/scan_hardcoded_patterns.py`
- 与 ai-operating-handbook.md 映射表对齐
- 集成到 `gaf_init.sh` 步骤 4.6

### Phase 2: Evidence 简化 + 信息必达（~3h）

**Step 2.1: 创建 ai-cheatsheet.md**
- 提取 59 个 lessons 高频要点 + env-hardrules 核心摘要
- 按主题分组写入
- 每条目带 `last_used` / `trigger_count` 元数据

**Step 2.2: 更新 L2 硬加载**
- `ai-operating-handbook.md` L2 段追加 cheatsheet.md
- `gaf-orchestrator/SKILL.md` L2 Hooks 追加 cheatsheet.md

**Step 2.3: 简化 evidence 写入规则**
- `gaf-orchestrator/SKILL.md` 闭环步骤 5：仅出错时写 evidence
- `ai-operating-handbook.md` Part 2：更新写入纪律

**Step 2.4: 迁移 lessons + 精简 failure-modes**
- 评估 59 个 lessons → 保留 ≤ 15 个高价值
- failure-modes.md 从 55+ 条精简到 ≤ 20 条

### Phase 3: 分级自动化 + 执行率追踪（~2h）

**Step 3.1: 创建 check_change_scope.py**
- 实现小/中/大修改的客观判定
- 集成到 pre-commit hook R11

**Step 3.2: 创建 check_lesson_level.py**
- 实现 L0/L1 自动分级判定

**Step 3.3: 创建 execution_rate.py**
- 自动统计每条规则的执行率
- 生成形式化治理报告

### Phase 4: Pre-commit 优化 + 验证（~2h）

**Step 4.1: 将 eslint/ruff 升级到 pre-commit stage**
- 修改 `.pre-commit-config.yaml`
- 验证自动修复效果

**Step 4.2: 端到端验证**
- 跑 1 个正常任务 → 验证 thinking trace + 无 unnecessary evidence
- 跑 1 个 bug_fix → 验证 evidence + cheatsheet 追加 + 硬编码扫描
- 跑 1 个中修改 → 验证分级判定 + 七维度验证
- 验证 cheatsheet.md 在 L2 加载

**Step 4.3: 更新文档**
- 更新 `docs/architecture/` 反映新管道
- 更新 `project_rules.md` 相关章节

### Phase 5: 生命周期管理 + 自动退役（~2h）

**Step 5.1: 创建 cheatsheet 膨胀控制**
- 新增 `scripts/governance/cleanup_cheatsheet.py`
- 实现条目级 `last_used` 元数据和过期检测
- 集成到 `gaf_init.sh` 步骤 4.7

**Step 5.2: 创建 N## 规则退役机制**
- 新增 `scripts/governance/retire_rules.py`
- 实现零触发期/低执行率/代码消失/重复规则 4 个退役触发器
- 三态生命周期（Active → Dormant → Archived）

**Step 5.3: 创建 lessons 退役机制**
- 实现 L3 lessons 自动退役（90 天无 `--query` 命中 / trigger_count=0 / >300 行）
- 硬上限：L3 活跃 ≤ 15 个

**Step 5.4: 创建扫描模式退役机制**
- `scan_hardcoded_patterns.py` 增加 `last_hit` 元数据
- `hit_count=0` + 90 天 → 自动移除

**Step 5.5: 创建 traces 膨胀控制**
- 新增 `scripts/governance/cleanup_traces.py`
- 三级保留（20 活跃 + 80 压缩 + 100 删除）

**Step 5.6: 创建退役总览脚本**
- 新增 `scripts/governance/lifecycle_report.py`
- 输出完整的治理体系健康度报告
- 每 2 周评审时自动运行

---

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Lessons 迁移丢失教训 | 低价值归档，AI 需要时找不到 | 保留 L3 按需加载，归档仍可 `--query` 命中 |
| Cheatsheet 膨胀 | 关键信息淹没 | 三级硬指标 (120/150 行警告/强制) + 条目级过期检测 |
| 七维度验证阻塞 commit | AI 必须跑完整检查才能 commit | 分级豁免：小修改仅需双调试视角 |
| thinking trace 增加 token 开销 | 每对话 ~500 tokens | ≤ 200 行/会话，自动清理旧 traces |
| 分级脚本误判 | 小修改误判为大修改 → 多跑检查 | 脚本输出 JSON，AI 可申诉（需在 trace 记录申诉理由） |
| 硬编码扫描误报 | 正常字符串匹配为硬编码 | 扫描结果仅作提醒（WARNING），不阻塞 commit |
| eslint/ruff 升级增加 commit 时间 | pre-commit 变慢 | 仅升级有自动修复能力的 hook，< 5s |
| N## 规则过度退役 | 活跃规则被误归档 | 退役需人工审批 + 三态可逆 (Active→Dormant 可恢复) |
| Cheatsheet 过时条目提醒干扰 | AI 频繁看到过时警告 | 连续 2 次提醒仍未使用才归档，单次提醒即可忽略 |
| 清理脚本误删 traces | 有价值的 trace 被提前删除 | 压缩归档保留摘要，活跃期 20 个，压缩期 80 个 |
| 退役节奏与实际需求错配 | 90 天零触发太短/太长 | 90 天为默认值，可在 lifecycle_report 中调整 |

---

## 成功标准

| 指标 | 改造前 | 改造后目标 |
|------|--------|-----------|
| AI 必读文件数 (L2) | 2 个 | 3 个 (+cheatsheet.md) |
| AI 每任务 evidence 写入 | 必写 1 份 | 仅出错时写 |
| Lessons 总数 | 59 | ≤ 15 (深度参考) |
| failure-modes.md 行数 | 169 | ≤ 80 |
| AI 启动关键信息可达率 | ~15% (仅 L0) | ~85% (L0 + cheatsheet) |
| 七维度评估可验证率 | 0% (AI 自报) | 100% (pre-commit 强制) |
| 中/小修改判定 | AI 自判 | 脚本客观判定 |
| 硬编码模式检出率 | 0% | 100% (git diff 扫描) |
| 规则执行率可量化 | 否 | 是 (每 2 周报告) |
| Commit 时间增加 | 基准 | ≤ 15% (有自动修复 hook 升级) |
| Cheatsheet 行数 | N/A (原不存在) | ≤ 120 行 (警告), ≤ 150 行 (强制) |
| N## 规则退役 | 手动 (无自动) | 半自动 (脚本扫描 + 人工审批) |
| L3 Lessons 退役 | 无机制 | 自动 (90 天零触发 → Dormant) |
| Session traces 保留 | 无限增长 | 三级 (20 活跃 + 80 压缩 + 100 删除) |
| 治理规则僵尸化 | 无检测 | 90 天零触发自动标记 |

---

## 问题覆盖映射

| 问题 # | 描述 | 严重性 | 解决方案 | 实施阶段 |
|--------|------|--------|----------|----------|
| P0-1 | Evidence 管道写了没人读 | P0 | 方案二：简化为 2 层 + cheatsheet.md | Phase 2 |
| P0-2 | AI 思维链完全隐藏 | P0 | 方案一：thinking trace + 内联标注 | Phase 1 |
| P1-3 | 关键治理检查软执行 | P1 | 方案三 3.1：pre-commit R9 验证 | Phase 1 |
| P1-4 | 规模分级 AI 自判 | P1 | 方案四 4.1：check_change_scope.py | Phase 3 |
| P1-5 | 规则文档 5 层跳转 | P1 | 方案二 2.2：cheatsheet.md 集中 | Phase 2 |
| P2-6 | L3 循环触发模糊 | P2 | 方案二 + 五：信息必达降低依赖 | Phase 2 + 3 |
| P2-7 | Evidence 沉淀自动化不足 | P2 | 方案三 3.2：R10 trace 验证 + 方案二简化 | Phase 1 + 2 |
| P2-8 | 症状映射软触发 | P2 | 方案三 3.3：scan_hardcoded_patterns.py | Phase 1 |
| P3-9 | Pre-commit 二阶段 | P3 | 方案六：eslint/ruff 升级 | Phase 4 |
| P3-10 | L0/L1 分级 AI 自判 | P3 | 方案四 4.2：check_lesson_level.py | Phase 3 |
| P3-11 | 执行率无量化 | P3 | 方案五：execution_rate.py | Phase 3 |
| P2-12 | 文件长期膨胀无控制 | P2 | 方案七 7.2-7.6：cheatsheet/traces/lessons 膨胀控制 | Phase 5 |
| P2-13 | 长期不触发规则无退役 | P2 | 方案七 7.1/7.3-7.5：三态生命周期 + 自动退役 | Phase 5 |

---

## 实施验证 (2026-08-06)

### 全部 Phase 完成状态

| Phase | 状态 | 关键产出 |
|-------|------|----------|
| Phase 1: 思维链外显 + 软环节硬化 | ✅ | thinking trace 机制 + R9/R10/R11 pre-commit hooks |
| Phase 2: Evidence 简化 + 信息必达 | ✅ | ai-cheatsheet.md (29 条目) + L2 3 文件硬加载 |
| Phase 3: 分级自动化 + 执行率追踪 | ✅ | check_change_scope.py + check_lesson_level.py + execution_rate.py |
| Phase 4: Pre-commit 优化 | ✅ | eslint/ruff/mypy 升级 pre-commit + auto-fix |
| Phase 5: 生命周期管理 | ✅ | 5 个治理脚本 + 健康度报告 (A 级 85.5%) |

### 最终数据

| 维度 | 数值 |
|------|------|
| Cheatsheet 条目 | 29 (全活跃) |
| N## 规则 | 45 active + 24 dormant + 8 retired |
| L3 Lessons | 15 active + 66 archived |
| 扫描模式 | 6 (全活跃, 有命中) |
| 预提交 Hooks | 10 pre-commit + 1 manual |
| 健康度 | A (85.5%) |

### 新增脚本清单

| 脚本 | 功能 |
|------|------|
| `scripts/governance/check_change_scope.py` | 客观判定修改规模 |
| `scripts/governance/check_lesson_level.py` | L0/L1 自动分级 |
| `scripts/governance/execution_rate.py` | 执行率统计 |
| `scripts/governance/cleanup_cheatsheet.py` | Cheatsheet 膨胀控制 |
| `scripts/governance/retire_rules.py` | N## 自动退役 |
| `scripts/governance/retire_lessons.py` | Lessons 自动退役 |
| `scripts/governance/lifecycle_report.py` | 健康度报告 |
| `scripts/governance/audit_governance.py` | 统一审计入口 |
| `scripts/governance/scan_hardcoded_patterns.py` | 硬编码扫描 (持久化) |
| `scripts/governance/cleanup_traces.py` | Trace 三级保留 |
| `scripts/hooks/check_reflection_evidence.py` | R9 反思验证 |
| `scripts/hooks/check_thinking_trace.py` | R10 思维链验证 |

### 更新文件

- `.pre-commit-config.yaml` — lint hooks 升级到 pre-commit
- `scripts/hooks/gaf_governance_batch.py` — 新增 R9/R10/R11
- `.trae/skills/gaf-orchestrator/SKILL.md` — thinking trace + evidence 简化
- `.ai-memory/meta/ai-operating-handbook.md` — L2 3 文件硬加载
- `docs/architecture/overview.md` — 新增 §14 AI 治理体系架构
- `.ai-memory/meta/failure-modes.md` — N## 索引更新 (归档 lesson 链接)
