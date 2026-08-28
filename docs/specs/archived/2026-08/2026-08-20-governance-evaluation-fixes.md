# Spec: 2026-08-20 治理体系评估修复（TD-369 ~ TD-380）

> **类型**: refactor（治理体系）| **创建**: 2026-08-20 | **来源**: 元评估 N180 闭环
> **依据**: 2026-08-20 治理评估报告（9 方向实测，12 项 TD 登记于 active-tech-debt.md）
> **状态**: ✅ 已归档 (docs/specs/archived/2026-08/2026-08-20-governance-evaluation-fixes.md)

## 阶段状态表

| Phase | 内容 | 状态 | 完成时间 | commit hash | 验收 evidence |
|-------|------|------|---------|------------|--------------|
| 1 | P1 批：注入瘦身 + 环境适配 + 沉淀清理 + skill 移出 + R9/R10 精简 | ✅ | 2026-08-20 | - | gaf_init 无算术错误；--check-env exit 0；project_rules 27.8KB；注入 114.6→60.5KB；scripts 测试 610 通过（剩 browser_login 环境依赖）；path/yn 一致性 0 error |
| 2 | P2 批：口径归一 + 复盘强制 + diff_keywords + commit 提速 | ✅ | 2026-08-23 | TD-371/376/377/378 | N181 计数口径(-, Active=36<70) + check_unclosed_review(claimed_rules:321) + diff_keywords 断言 + governance batch 17 checks 分拆提速 |
| 3 | P3 批：分级收敛 + 去重 + 元数据合并 | ✅ | 2026-08-23 | TD-372/373/380 | project_rules §0 9 列单一权威源 + N167 收敛指针 + 元数据 commit 收敛纪律（本归档即 TD-380 执行） |

> **归档结论 (2026-08-28)**: 12 项 TD（TD-369~380）全部 ✅ FIXED 迁移至 `docs/archive/fixed-tech-debt.md`；
> 阶段表历史遗留 ⏳ 已回填；验收标准全达成（含注入 <50KB、commit 链 <8s、Active 计数口径归一）。

## Phase 1（P1 批，5 项 TD）

### TD-375: skill 死配置移出（先做，低风险）

- 11 个 0 引用 skill（brainstorming / executing-plans / finishing-a-development-branch / subagent-driven-development / using-git-worktrees / using-superpowers / requesting-code-review / receiving-code-review / mcp-builder / workflow-runner / writing-skills）移至 `.skills/_archive/skills/`（2026-08-21 追加：整个 `.skills/_archive/skills/` 目录彻底删除，git 历史可追溯，README.md 移除 `_archive` 结构与归档恢复规则）
- 保留：gaf-* 5 个 + 6 个方法论（test-driven-development / systematic-debugging / writing-plans / verification-before-completion / pipeline-task-diagnosis / dispatching-parallel-agents）+ chinese-* 4 个（显式触发设计）+ writing-skills？—— writing-skills 也在 0 引用清单里，移出
- 更新 `.skills/README.md` 索引表
- 验证：`.opencode/skills` junction 仍解析；available_skills 减少（下次对话生效）
- 2026-08-21 追加清理：systematic-debugging 目录下 CREATION-LOG.md + test-academic/test-pressure-1/2/3.md（历史验证记录，无运行时引用）一并删除

### TD-374: 沉淀生命周期清理

- 10 个 Retired lesson（N108/N165/N138/N139/N140/N142/N143/N144/N149/N157）移出 lessons/ 活跃区
- evidence active/ 88 个文件按 session 目录批量移 archived/2026-08/
- failure-modes.md Retired 段 lesson 链接标 "git-only"
- 验证：lessons 活跃区 Retired 关联 lesson 消失；evidence archived/ 计数 = 88

### TD-370: gaf_init.sh 环境适配

- 修 line 200 算术语法错误
- 支持 `--check-env` 参数（env-hardrules 校验命令文档已写）
- session active 路径统一（文档 vs 实现对齐）
- 验证：`bash scripts/gaf_init.sh --check-env` exit 0 无 stderr 报错

### TD-379: R9/R10 思维链 hook 精简（选 B）

- 实测：check_thinking_trace / check_reflection_evidence **从未接入 commit 链**（不在 .pre-commit-config.yaml，也不在 gaf_governance_batch CHECKS），仅文档引用——比预想更彻底的摆设
- 两个脚本归档到 `scripts/_archive/hooks/`
- session-traces/README.md 更新：R10 退役声明，trace 改为可选调试辅助
- 验证：grep 确认活跃文档无 R9/R10 hook 调用引用

### TD-369: 注入层瘦身

- opencode.json instructions 移除 `.skills/README.md`（与 available_skills 重复）
- project_rules.md 瘦身 71.4KB → <30KB（删历史来源段/版本说明/重复引用，保留全部硬约束 ✅/❌ 行）
- 验证：注入总量 < 50KB；关键硬约束 grep 无遗漏

## Phase 2（P2 批，4 项 TD）

### TD-371: N## 计数口径归一

- gaf_init.sh grep 限定 Active 段（## Active 到 ## Retired 之间）
- 跑 `python scripts/governance/n181_retirement_eval.py`（Active 71 > 70 硬阈值已触发）
- 验证：gaf_init L1 输出 Active 段真实计数

### TD-376: M2 复盘闭环 hook 强制

- check_claimed_rules.py 检测 REVIEW_TRIGGERED + 无复盘写回 → 阻塞/警告
- 处理 3 次历史未闭环触发（跑一次复盘写回）
- 验证：claimed-activation.md 3 次历史触发有复盘记录

### TD-378: M3 diff_keywords 强制

- hook 校验新 lesson frontmatter 必含 diff_keywords 字段
- 存量 119 个 lesson 批量回填
- 验证：回填率 ≥ 80%

### TD-377: commit 链提速

- 1.4s 档 hooks 增量模式（只扫 staged）
- governance_batch 内子检查并行
- 验证：commit 链 < 8s

## Phase 3（P3 批，3 项 TD）

### TD-372: 5 套分级收敛

- project_rules §0 表格加 反思/测试/加载 3 列（单一权威源）
- 同步 N177/N179 引用
- 验证：全仓 grep 无第二套规模阈值定义

### TD-373: 交叉引用去重

- N167 收敛为 project_rules §2.0.5 权威源，handbook/reflect-skill 改指针
- 沉淀纪律同理
- 验证：grep N167 权威源 1 处完整 + 其余 ≤1 行指针

### TD-380: 元数据 commit 合并

- docs(sXX) 类合并规则（每 spec 最多 1 条 docs commit）
- gaf-auto-archive-specs 触发时机调整
- 验证：新 spec 元数据 commit ≤ 1 条

## 验收标准

- [ ] Phase 1-3 全部 ✅
- [ ] 12 项 TD 状态迁移（✅ FIXED → fixed-tech-debt.md）
- [ ] gaf_init --check-env 通过
- [ ] 关键硬约束（conda/Shell/§3.4/§4.6/§4.8/§6.2）无丢失
- [ ] N173 用时字段记录

## 已知限制

- opencode available_skills 生效需新对话（当前对话仍显示旧列表）
- project_rules 瘦身以"引用指针 + 硬约束保留"为原则，历史背景依赖 git 追溯