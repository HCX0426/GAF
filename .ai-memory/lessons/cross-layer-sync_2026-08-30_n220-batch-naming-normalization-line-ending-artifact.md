---
date: 2026-08-30
symptom: [naming-normalization, batch-rename, agent-worker-rename, line-ending-artifact, lf-crlf, git-status-m-empty-diff, frontend-type-regen, openapi-regen-drift]
solution: 命名/概念归一化批量重命名按"评估稿 spec 级顺序 → 5 层 sweep (符号→目录 git mv→线协议→DB 字段/迁移→前端类型重生成) → 文档"执行; 词边界正则保护标识符与契约键; OpenAPI 重生成暴露既有 drift 当场登记 TD 不掩盖; 批量改写文件可能把 CRLF 转 LF 造成 "git status 显示 M 但 git diff 为空" 的行尾符伪影 — 判断真实改动必须看 `git diff`/`git diff --stat` 内容而非仅凭 status
related_files:
  - docs/analysis/concept-naming-normalization.md
  - backend/workers/services/device_identity.py
  - backend/protocol/consumers.py
  - frontend/src/types/api.generated.ts
  - docs/archive/spec-context/2026-08-29-naming-g-worker-rename-context.md
created_by: AI
priority: high
n_id: N220
level: L1
topic: cross-layer-sync
cross_refs: [N112, N191, N193]
diff_keywords: ["naming", "rename", "Agent", "Worker", "emulator_brand", "line-ending", "CRLF", "LF", "api.generated"]
---

# 命名归一化批量重命名 (A→B→C→G→D/E/F) 方法论 + 行尾符伪影

## 症状（2026-08-29~30, naming 系列 OQ-1~10 全量收口）

概念/命名归一化全量收口: C 批 4 spec 改字段 (Device.emulator→emulator_brand / GameProfile.default_routine→default_task_chain / TaskStep 并入 ExecutionStep / task.assign 帧名)、G 批 Agent→Worker 全局重命名 (44 源码 + 16 迁移 + 30 前端 + 122 文案)、D/E/F 文档收口、OQ-9 设备发现权威统一。

收尾时的隐患: **55 个文件 `git status` 显示 M, 但 `git diff HEAD -- <file>` 内容为空** — 3-pass 字节级批量替换 (utf-8 读写) 把 CRLF 行尾转成了 LF, `core.autocrlf=true` 下 status 判定为脏 (smudge 期望 CRLF vs worktree LF), 而 diff 按 clean 归一化后内容相等 → 0 hunks。

## 根因

1. **批量重写丢行尾**: 字节级 utf-8 读写重写文件时把 `\r\n`→`\n`, content 相同但 line ending 不同; git autocrlf 转换侧 (smudge/clean) 看待两个方向结果不一致 → status 与 diff 结论矛盾。
2. **真值重生成暴露存量 drift**: `npm run generate:api-types` 重生成 api.generated.ts 后, 旧 schema 不再掩盖前端既有引用漂移 (head mid-state 快照含旧字段) → 11 条 tsc error 现身, 其中 2 条为新暴露 (naming-c 前端未同步) → TD-422。

## 解决方案（N220）

### 1. 执行顺序（评估稿 spec 级顺序定序）
A(低危/删死代码) → B(内部改名) → C(字段/前端可感知) → G(全局符号 Agent→Worker) → D/E(文档) → F(device_bridge) → OQ-9(权威统一)。C 批字段改名用 migration `RenameField` 保数据, 线协议键同步改。

### 2. 5 层 sweep 顺序
① 符号/类名 → ② 目录 `git mv` (agent/ → worker/) → ③ 线协议帧/consumer/路由 → ④ DB 字段 + 迁移 + FK 字符串 → ⑤ 前端类型 (`generate:api-types` 重生成) + 组件字段。每层独立 commit + evidence (P3/P4/P5/P6 各自 problem/solution/verification)。

### 3. 词边界正则保护标识符/契约键
`(?<![A-Za-z0-9_])Agent(?![A-Za-z0-9_])` 全词替换 → 保留 `fetchAgents/useAgentsQuery/AgentHealthPanel/agent_debug_*` 等标识符与契约键 (小写键名天然免伤) + 显式排除 AI 域 (AgentSession/LogAnalysisPanel) 与 User-Agent 字符串。

### 4. 真值重生成 = 暴露问题工具, 不是掩盖工具
重生成后 tsc 新错误 = 前端真实未同步, 当场登记 TD (不掩盖/不回退生成文件): TD-422 归各 naming-c spec 前端阶段, 由后续前端 sweeps 清零。

### 5. 行尾符伪影判定（防误判工作树脏）
- 大批量改写文件后: 用 `git diff --stat` / `git diff HEAD -- <file>` 看**内容 diff**; 若为空 = 非真实改动, status 的 M 为 autocrlf 行尾转换产物。
- 提交前 `git add` 后 `git diff --cached --stat` 复核; 空内容 diff 的文件不会改变任何逻辑, 属环境噪音。

## 验证

- naming-g P7: 受影响域 614 passed + worker 2278 passed + 前端 tsc 11 errors 全归 TD-422 (0 属 G) → 验收成立。
- `npx tsc -b` (2026-08-30) 退出码 0 → TD-422 清零; `git status` 55 M 文件 `git diff` 全空 → 确认行尾符伪影非真实改动。
- all naming specs archived + 评估稿 `docs/analysis/concept-naming-normalization.md` full 通过。

## 泛化原则

- **跨层契约变更必须 5 层同步** (N112 后端字段→前端 4 步配套的放大版): 字段/协议/前端/迁移/文档缺一层即 drift。
- **工具批量改写文件后, 用内容 diff 判断真实改动, 不要只信 status**: line-ending 噪声与真实改动要分开核验。
- **重生成真值产物 (OpenAPI/typegen) 只暴露问题, 不制造问题**: 暴露出的 drift 是历史欠账, 当场登记 TD 并归属责任 spec, 才是治本 (N193 任务归属硬约束)。