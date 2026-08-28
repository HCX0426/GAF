# spec-39: docs/ 内容同步 + 规则冲突修复 (合并用户两项要求)

> **来源**: 用户反馈 "spec-38 完成后要把这两个文件夹里的内容都更新下,目前这些代码或者架构变更都没有更新对应的文档" + "检查规则文档是否有冲突的地方,不要只看单人项目,最重要是考虑长期维护性,以及文档的膨胀性"
> **本 spec 范围**: ① docs/ + .ai-memory/ 内容反映最新代码/架构 (C-038 重命名 + C-048 WS 删除 + C-045 AuditLog + C-063 ExecutionConsumer 删除) ② 规则文档冲突修复 (计数统一 + 乱码 + frontmatter 差异化)
> **状态**: ✅ Done (2026-07-19, 9 Phase 全部完成, N176 规则 hash 待下次 spec 一并回填)
> **关键设计决策**: §2.0.5 N167 维度 1 架构长远性 + 维度 7 长期维护成本双优先 — 文档过期会持续误导 AI; 计数硬编码会因代码增长必然过期, 必须改用动态计数

## 阶段状态表

| Phase | 内容 | 优先级 | 行数估计 | 状态 | 完成时间 | Commit | 验收 evidence |
|:-----:|------|:------:|:--------:|:----:|:--------:|:------:|--------------|
| 1 | .ai-memory/data-flow.md 全文重写 (P0-1) — Django 5.2 + 22 app + 90+ pages + 27 api client + 37 nodes + 5 active WS + tracing/middleware.py 路径 + C-045 AuditLog + C-063 删除说明 | P0 | ~80 行重写 | ✅ | 2026-07-19 | - | 全文重写 357 行, 7 处过期全修复; 新登记 TD-281 (macOS/Linux 状态标记不一致) |
| 2 | docs/general/design/architecture-overview.md §9 + §13.1 修复 (P0-2) — 22 app 计数 + device_bridge 非 Django app 标注 + AuditLog 114 接入点 + executions REST only + /ws/protocol/agents/ 路径 | P0 | ~30 行更新 | ✅ | 2026-07-19 | - | §9.5 device_bridge 标纯 Python 包 + §9 标题改 22 app + §13.1 新增 C-045 AuditLog 条目 + 路径 /ws/agent/ → /ws/protocol/agents/ |
| 3 | docs/standards/api-contract.md §9 + §16 修复 (P0-3) — /ws/agents/ 删除 + 5 active WS + AuditLog API 契约 | P0 | ~40 行更新 | ✅ | 2026-07-19 | - | §9.1 重写 5 active WS + 4 已删除端点说明 + §16 标 C-045 + last_updated 2026-07-19 |
| 4 | docs/general/design/gaf-features-overview.md §八 + 附录 B 修复 (P0-4) — ai/→gaf_ai/ + macOS/Linux 路径校正 + 附录 B 加实现位置列 | P0 | ~20 行更新 | ✅ | 2026-07-19 | - | §八 ai/→gaf_ai/ (C-038) + 附录 B macOS/Linux "(待实现)"→"P-028 ✅, backend/device_bridge/platforms/" + 加实现位置列 |
| 5 | architecture-mistakes.md P0-3 (CJK 乱码 #47 段) + P0-4 (#28 重复段) 修复 | P0 | ~30 行修复 | ✅ | 2026-07-19 | - | #47 CJK 乱码全修复 (PowerShell non-UTF8 redirect 导致) + #28 删除重复段 (L783-827 = L737-781 复制, ~45 行) |
| 6 | 计数统一 (P0-1 规则 + P0-2 规则 + P2-3) — N##/docs 计数改动态 + 删除硬编码 | P0 | ~10 行更新 | ✅ | 2026-07-19 | - | rules §0/§6.4 三处硬编码 (46 docs/7 sub-file/43 条) 改动态; failure-modes.md 归档评估段改动态 |
| 7 | frontmatter 字段差异化 (P0-5) — 按 maintainer 模式差异化必填字段 | P1 | ~15 行更新 | ✅ | 2026-07-19 | - | .ai-memory/README.md §1 重写: 三模式表 (auto=4/derived-manual=9/manual=8) + 3 套模板; 新登记 TD-282 (check_lessons_updated.py 待差异化) |
| 8 | P1 修复 — tech-stack.md §4 + GAF-optimal-solution.md §七 + version-compat.md §0 日期 + auto-kb 重生成 | P1 | ~20 行更新 | ✅ | 2026-07-19 | - | tech-stack.md §4 路径漂移修复 + GAF-optimal-solution.md macOS/Linux 路径补全 + version-compat.md §0 日期 2026-07-19 + sync_ai_memory.py regenerated=4 skipped=107 conflict=0 (5.42s) |
| 9 | 全量回归 + commit + C-067 + TD (如有) | P2 | - | ✅ | 2026-07-19 | (N176 规则待下次 spec 一并回填) | 5 sync/check 脚本全过 (4.83s/5.33s/4.55s/4.43s/6.36s); C-067 落地 completed-features.md; 新登记 TD-281+TD-282; 新沉淀 N176 (单对话批量 spec 单 commit) |

**总计**: 9 Phase, ~245 行 diff (4 文件 P0 重写 + 5 文件 P0 修复 + 4 文件 P1 更新 + 4 auto-kb 重生成)

## Phase 详细计划

### Phase 1: data-flow.md 全文重写 (P0-1)

**问题**: `.ai-memory/data-flow.md` 是 L2/L3 hard-load 文档, 7 处过期会直接误导 AI:
1. Django 版本: 4.2 → 5.2
2. App 数量: 20 → 24
3. 前端页面: 11 → 31+
4. Pipeline 节点: 15 → 37
5. WS 端点: `/ws/agents/` (已删 C-048) → `/ws/protocol/agents/`
6. 中间件路径: `tasks/trace_middleware.py` → `tracing/middleware.py` (C-025 2026-07-09 迁移)
7. 已知问题 N91/N86/N58 多数已闭环

**修复**: 全文重写, 更新所有过期字段 + 添加 C-045 AuditLog + C-063 ExecutionConsumer 删除说明

### Phase 2: architecture-overview.md §9 + §13.1 修复 (P0-2)

**问题**: `docs/general/design/architecture-overview.md` last_updated 2026-07-14, 未同步 C-038 (`backend/ai/`→`gaf_ai/` + `backend/core/`→`gaf_core/` 2026-07-15) + C-045 AuditLog + C-063

**修复**:
- §9.1/§9.3/其他: `ai/` → `gaf_ai/`
- §9.5: `core/` → `gaf_core/`
- §9.2: executions app 标注 REST only, WS 部分已迁移
- §13.1: 新增 AuditLog 114 接入点条目

### Phase 3: api-contract.md §9 + §16 修复 (P0-3)

**问题**: `docs/standards/api-contract.md` last_updated 2026-07-02, 未同步 C-048 + C-045

**修复**:
- §9 WebSocket 端点表: 删除 `/ws/agents/`, 列出 5 个 active WS 端点
- §16: 新增 AuditLog API 契约 (POST/GET 路径 + 字段 schema)

### Phase 4: gaf-features-overview.md §八 + 附录 B 修复 (P0-4)

**问题**: `docs/general/design/gaf-features-overview.md` last_updated 2026-07-13, 未同步 C-038 + C-045 + P-028 macOS/Linux 完成

**修复**:
- §八: `ai/` → `gaf_ai/`, 新增 AuditLog 段
- §附录 B: macOS/Linux "待实现" → ✅ (与 completed-features.md P-028 一致)

### Phase 5: architecture-mistakes.md 乱码 + 重复段修复 (P0-3 规则 + P0-4 规则)

**问题**: `.ai-memory/summaries/architecture-mistakes.md`:
- L1895-1905+: #47 N118 段 CJK 乱码 (binary-safe append 副作用)
- L770-782 vs L819-827: #28 段内容重复

**修复**:
- #47 N118: 从 git history 恢复或重写, 跑 UTF-8 验证
- #28: 删除 L819-827 重复段

### Phase 6: 计数统一 (P0-1 规则 + P0-2 规则 + P2-3)

**问题**: 同一规则多处定义且数值矛盾
- N## Active 计数: failure-modes.md (50) vs gaf-orchestrator/SKILL.md (51) vs gaf-knowledge-base/SKILL.md (50+)
- docs/ 文件数计数: project_rules.md L81 (46) vs gaf-knowledge-base/SKILL.md L19/L59/L93 (36)
- Dormant 计数: gaf-orchestrator/SKILL.md (13) vs failure-modes.md (11)

**修复**:
- 全部改用动态计数 (由 sync_ai_memory.py / sync_docs_index.py / gaf_init.sh grep 自动统计)
- 删除硬编码数字, 改为 "见 docs-index.md 动态索引" 或 "由 gaf_init.sh grep 自动统计"

### Phase 7: frontmatter 字段差异化 (P0-5)

**问题**: `.ai-memory/README.md` L58-72 (9 字段全必填) vs L31-33 (3 种 maintainer 模式)
- `source` / `load_when` / `symptom` / `solution` / `related_files` 在 manual 模式下不适用
- 但 README 仍标必填

**修复**: 按模式差异化必填字段:
- `auto`: 全 9 字段
- `derived-manual`: 7 字段 (source 可选)
- `manual`: 4 字段 (maintainer/priority/created_by/generated)

### Phase 8: P1 修复

- tech-stack.md §4: `agent/src/devices/{windows,macos,linux,adb}/` → `agent/src/platforms/{windows,linux,macos}/` + `agent/src/devices/adb/`
- GAF-optimal-solution.md §七: 日期 2026-06-21 → 2026-07-19, 补 spec-29~38 摘要
- version-compat.md §0: 快照日期 2026-06-16 → 2026-07-19
- 4 auto-kb 重生成: `sync_ai_memory.py --regenerate`

### Phase 9: 全量回归 + commit + C-067

- 跑 5 个 sync/check 脚本
- commit (单 commit, spec 粒度)
- C-067 落地到 completed-features.md
- spec 状态表更新 + commit hash 回填

## N167 七维度评分

| 维度 | 评分 | 理由 |
|------|:---:|------|
| 1. 架构长远性 | 5/5 | 修过期文档 + 改动态计数, 3-5 年内不会因代码增长过期 |
| 2. 全局归一化 | 5/5 | 计数统一为动态, frontmatter 字段按模式归一化 |
| 3. 新旧兼容 | 5/5 | 单人项目, 一次性切换, 无过渡逻辑 |
| 4. 现有业务完善 | 4/5 | 修复 4 P0 + 6 P1 + 5 规则冲突, 覆盖 90% 过期点 |
| 5. 性能 | 3/5 | 文档修改不影响性能, sync 脚本已有 |
| 6. 安全 | 3/5 | 文档修改不涉及安全 |
| 7. 长期维护成本 | 5/5 | 动态计数 + frontmatter 差异化降低长期维护成本, 看长期受益不看一次性成本 |

**总分**: 30/35 (≥ 19 且维度 1+7 双 5/5, AI 自决执行)

## 验收标准

- [ ] 4 P0 文件过期内容全部修复 (data-flow.md + architecture-overview.md + api-contract.md + gaf-features-overview.md)
- [ ] architecture-mistakes.md 乱码 + 重复段修复
- [ ] 5 处规则计数统一为动态
- [ ] frontmatter 字段按模式差异化
- [ ] 4 auto-kb 重生成 (sync_ai_memory.py --regenerate)
- [ ] 5 sync/check 脚本全过
- [ ] C-067 落地到 completed-features.md
- [ ] commit hash 回填

## 后续 spec-40 (大修改, 单独开)

用户要求 "长期维护性 + 文档膨胀性" 强化, spec-39 仅覆盖 P0/P1 修复。以下大修改留 spec-40:
- architecture-mistakes.md 2940 行拆分 (需 N151 5 步评估)
- 5 层分发术语残留全仓库批量替换 (20 文件)
- spec 粒度 commit 三处描述合并 (§3.4/§4.9/§4.10)
- L3 循环 9→7 维度映射简化
- _workflow.md 609 行拆分
- _misc.md 4 主题拆分
- 单人项目过度约束规则简化 (spec 粒度 commit 各 Phase 暂存 / N175 subagent 落地检查 Y/N 矩阵 / 季度首日 review)
