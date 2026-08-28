---
maintainer: manual
source: 2026-08-21 config/scripts 整理对话
load_when: [askuserquestion, 自决, autonomy, 清理任务, 删除文件, 配置同步, 机制扩展]
priority: high
symptom: [kb:askuser-overreach, askuserquestion-overuse, N206]
solution: 判定档位 — 可恢复清理/机制扩展/计划内任务 → 自决不问; 仅跨机器 push/不可逆删除/N167 4 类硬场景/规则未覆盖歧义 → AskUserQuestion
diff_keywords: ["AskUserQuestion", "自决", "autonomy", "cleanup", "delete", "删除", "清理", "确认"]
related_files:
  - .skills/rules/project_rules.md
  - .ai-memory/meta/ai-operating-handbook.md
  - .ai-memory/meta/yn-matrices/archived-yn-matrices/_ai-autonomy.md
created_by: AI
topic: ai-autonomy
last_updated: 2026-08-24
---


# N206 — AskUserQuestion 过度使用 (可自决误判为不可逆授权)

## Problem（症状 / 触发条件）

2026-08-21 配置一致性 + scripts/ 整理任务中, AI 连续发起 2 次 AskUserQuestion:

1. "scripts/ 的 4 项修正怎么执行？" (全部执行 / 只修登记 / 先只评估)
2. "版本号 / env 模板等纯手动同步点，是否也要治理？" (暂不治理 / 加校验 hook)

两次均属于规则已授权自决的范围 — 用户质疑 "哪些是你觉得你可以决定的，规则文档还是工作流没写吗"。

触发条件: 涉及删除/移动 git 追踪文件、清理类任务、机制扩展 (hook) 时, AI 触发"删除/不可逆"心理防御, 把可恢复操作抬到"需授权"档位。

## 根因

- **档位误判**: 规则 §3.5 明确"本地文件删除: 可自决，git 追踪可恢复"，但 AI 把 git mv / 删副本当成"不可逆"→ 询问
- **N193 任务归属未落实**: 清理/整理类问题是实现中发现的，应自动纳入当前任务，不抛给用户
- **AskUserQuestion 触发条件被放宽**: handbook §141 仅限 4 场景 (规则未覆盖歧义 / 不可逆授权 / 评分不满足 / 4 类硬场景)，实际执行被放宽

## Solution（判定档位标准）

**自决（不问用户）**:
- 清理/整理/归档类任务（git 追踪文件删除、git mv、副本去重、README 登记）
- 机制内扩展（扩展现有 hook 检查项）
- 计划内任务推进（§3.6）/ spec 内自决（N109）/ 优先级自决
- N167 评分满足自决阈值的架构方案

**必须 AskUserQuestion（仅这 4 类）**:
1. 跨工作区/跨机器: `git push` 远程 / `pull --rebase` 跨分支 / `remote add`
2. 不可逆删除: `branch -D` / `tag -d` / `stash drop` / `clean -f` / API DELETE / DB DROP
3. N167 4 类硬场景: FK 变更 / schema 迁移 / 业务语义 / 不可逆
4. 规则未覆盖的真正歧义

**自检一句话**: "这个操作 git 能恢复吗？能 → 自决；跨机器/不可逆/业务语义 → 问"

## Recurrence (2026-08-24) — 沉淀动作也不该问

**场景**: 元评估类任务复盘时, 识别出两个"误判断点" (TD-381 已退役 / TD-382 已实施) 后, 向用户问 "需要我帮你处理那 2 个脚本改动吗" 和 "要沉淀这条教训吗 ?".

**根因**: 把"沉淀与否"抬高为需用户裁决 — 但 §3.8 判定标准是 AI 自决 (1 问: "下次对话 AI 是否需遵守? → 是 → 立即落盘"), N172 明确规定 "应该沉淀 = 同回复内立即调工具 Write/Edit". 问"要不要沉淀"本身就是 AskUserQuestion 过度.

**约束**: 
- ❌ 问用户 "要不要沉淀" / "是否补充 lesson" → ✅ 自检 1 问成立则同回复内立即落盘
- ❌ 反思后把"沉淀决定"抛给用户拍板 → ✅ 提前细化到 §3.8 硬约束后 AI 自决
- ✅ 元评估/复盘类任务结束点默认先跑 §3.8 判定, 成立即 Write/Edit, 非必要不沉淀

## Recurrence (2026-08-24 #2) — 明显 bug 修复也不该问

**场景**: 排查出两个明确缺陷 (agent 启动慢 ~2min: ADB 端口串行扫描; backend 设备忙 eager retry 阻塞请求 90s) 并定位根因后, 向用户问 "要我把这两个修掉吗?" / "你想用哪种?" / "先修哪个?".

**根因**: 明显缺陷 (可复现、有根因、修复方案明确) 属于"机制内修复"和"自决范围" — 项目规则 §3.6 计划内任务完全自治, bug 修复驱动任务本就该直接修; 把"是否修"问用户 = 把修复权外抛, 与 N193 任务归属、N109 决策自决同源.

**约束**: 
- ❌ 修复类任务修完 bug 后问 "要修吗" / "要不要处理那项?" → ✅ 直接修 + 验证 + commit, 汇报时陈述已修
- ✅ 自检: "缺陷可复现? 根因明确? 修复方案在现有架构内?" 三个都成立 → 自决修, 不问
- ✅ 汇报时给"已修+验证证据", 而非"要不要修的选项清单"; 只有方案存在真实取舍 (用户资源/不可逆/业务语义) 才给选项
