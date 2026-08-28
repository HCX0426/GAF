# Problem: AI 治理执行率靠记忆而非机制

## 触发背景
用户要求对比 GAF 治理体系与 TEST_SFCAPI_LANGUAGE 项目 (D:\code\environment\桌面项目),
识别 GAF 缺失的"确定性机制". 对比结论 (2026-08-15):

- GAF 赢: 知识资产 (144 lessons + spec/TD/evidence 治理 + 13 项 governance checks)
- TEST 赢 3 个确定性机制:
  1. **AST 代码铁律门禁** — 代码层无门禁, 静默吞错 (N182/N183)、SQL 拼接、schema
     残留 (max_wait) 全靠人工 review, 无 pre-commit 强制
  2. **声称-激活率回执** — AI commit message 声称遵循 N## 规则但无 diff 证据,
     无法区分"真实应用" vs "形式合规" (TEST v3.4 positive_rate 主指标)
  3. **diff 触发式教训检索** — 教训只在"主动 load"时出现 (gaf-lesson-router),
     复发靠记忆; 无"下次踩坑自动提示"机制

## 用户决策
- M1: 客观硬规则阻断 (R001/R004 error) + 其余警告 (R002/R003/R005)
- M1: 起步 5 条规则全上 (R001-R005)
- M2: post-commit WARN-only + 记录 .ai-memory/ops/claimed-activation.md
- M3: 精选 15 条高频 N## 回填 diff_keywords (清单经用户批准)
- "开始吧"

## 根因
治理体系有"规则文档"但缺"执行机制" — 文档约束靠 AI 自觉, 执行率不稳定
(N189 治理形式化判定维度). 需把"自觉遵守"升级为"机制强制/自动提示".