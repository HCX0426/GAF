---
spec_id: 2026-08-20-governance-evaluation-fixes
type: refactor (治理体系)
created: 2026-08-20
status: active
applies_to: [project]
---

# Spec Context — 2026-08-20 治理体系评估修复

## 用户决策原文

1. "评估一下这个项目的 per-dialogue 加载工作流、规则文档和 AI 思维链三个维度"（启动评估）
2. "继续评估"（3 次，驱动评估覆盖全部 9 方向）
3. "登记后继续评估"（TD 登记与评估并行推进）
4. "所有评估完再整体看"（完整报告后统一决策）
5. "开始吧"（授权开始修复，不逐项确认，按优先级 P1→P2→P3 推进）

## N151 5 步评估

1. **架构盘点**: 治理体系 = 注入层 (opencode.json/README/env-hardrules/project_rules) + 加载链 (gaf_init → L1/L2/L3) + 沉淀层 (.ai-memory lessons/evidence/meta) + 强制层 (pre-commit hooks 16 个) + skills 层 (26 个目录 + junction)
2. **识别反模式**: ① 注入只增不减 ② 文档规则依赖 AI 记忆 (机制未强制) ③ hook "文件缺失即放行" 设计缺陷 (R9/R10) ④ 5 套分级标准并存 ⑤ 归档机制设计了规则无脚本执行 ⑥ 元数据 commit 泛滥
3. **A/B/C 备选**: 以 TD-379 为例 — (A) 改造为强校验 (session-traces 无文件 FAIL 阻塞) / (B) 精简 (删除 R9/R10, 思维链由 M2 claimed-activation 覆盖) / (C) 保留现状。评估选 B: R9/R10 实测从未接入 commit 链, 无真实数据价值, 精简成本最低且不损失治理能力
4. **拒绝反模式**: 拒绝"最小化修补"(只修算术 bug 不动注入); 拒绝"保留双套"(R9/R10 与 M2 重复设卡); KEEP 决策: 注入预算机制 + 归档白名单 (合理生命周期管理)
5. **AI 自决边界**: 12 项 TD 均属"已登记+用户确认闭环路径", 修复方案已在 TD 登记时经用户确认; 本次执行属计划内任务, AI 自决推进

## N167 七维度评分

| 维度 | 评分 | 说明 |
|------|:----:|------|
| 1 架构长远性 | 9 | 注入预算机制 + 归档路径规范化是长期结构改进 |
| 2 全局归一化 | 8 | 消除 README 重复注入、路径/参数/计数口径多源 |
| 3 性能 | 7 | 注入 -47%, commit 链 3 处 hook 提速 (governance-batch 8.4s) |
| 4 安全性 | 7 | 无敏感信息; git 回退安全 (归档保留, 无删除) |
| 5 兼容性 | 8 | junction 目录结构不变; 节号全保留断链风险低 |
| 6 可测试性 | 8 | E2E cross_repo 措辞同步后全绿; hook 校验通过 |
| 7 长期维护成本 | 8 | 注入护栏约束膨胀; 归档路径进 R4 白名单 |
| **总分** | **55** | ≥ 19 且领先充足 → AI 自决 |

## 关键实施决策

1. **归档路径三件套**: `.ai-memory/_archive/` (lessons) + `.skills/_archive/` (skills) + `scripts/_archive/` (hooks) + `evidence/archived/2026-08/` — 全部 git 可追溯, 不参与扫描
2. **注入预算 ≤62KB**: env-hardrules + project_rules 合计上限, 新增内容前必须先压缩 (护栏约束)
3. **链接改指归档路径** 而非 git-only 标注: hook 只认反引号内路径, 指向真实文件最稳妥 (N142/N143/N144/N149/N157/N138)
4. **R4 归档白名单扩展**: check_doc_code_sync 3 个新归档路径跳过 (TD-374/375/379 配套)
5. **E2E cross_repo 措辞同步**: 测试期望词"不可逆数据删除"与规则对齐 (pre-existing 数据漂移)

## N173 用时字段

- start_ts: 2026-08-20T19:30:00+08:00
- end_ts: 2026-08-20T21:05:00+08:00
- duration_min: 95
- within_baseline: 否 (大修改基线 <60 min)
- root_cause_if_over: 评估报告占 40 min (9 方向实测 + 12 TD 登记), 修复执行 55 min (含 pre-commit 3 轮失败修复: FM 链接路径 + R4 白名单 + evidence/spec-context 补齐); 修复本身在 55 min 内完成