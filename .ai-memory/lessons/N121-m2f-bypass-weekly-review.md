---
id: N121
source: GAF/.ai-memory/lessons/N121-m2f-bypass-weekly-review.md
load_when:
- 每周复盘 bypass 模式
- 发现同类 bypass 反复出现
- 需要把绕过转化为 lessons 或工具修复
priority: medium
symptom:
- bypass:weekly:missing
- audit-log:unreviewed
- workaround:recurring
solution: 每周跑一次 `bypass_weekly_review.py`, 统计 `.gaf_audit.log` 高频 bypass reason, 写入
  `bypass-patterns.md`, 对 >=3 次的 reason 提议修工具/写 lesson
diff_keywords: ["bypass", "weekly", "review", "bypass_weekly_review", "missing"]
related_files:
- scripts/lessons/bypass_weekly_review.py
- scripts/tests/test_bypass_weekly_review.py
created_by: AI
date: 2026-06-17
last_updated: 2026-06-17
level: L1
n_id: N121
topic: workflow
---






# N121: bypass 模式无每周复盘 → 同类绕过反复发生 (M2.F 闭环, 2026-06-17)



## 症状



- `.gaf_audit.log` 写了 BYPASS 记录, 但没人每周 review

- 同一个 bypass reason 反复出现 (如 hook bug / sync 回滚 / timeout 傻等)

- 绕过变永久, 后续 AI 和人类都忘记当初为什么 bypass

- 无法区分 "一次性应急" vs "需要修工具的系统性问题"



## 根因



- **审计只写不看**: `gaf_audit.log` 是 append-only 审计, 缺周期性聚合

- **转化决策缺位**: BYPASS 后没有机制决定 "继续观察" / "修工具" / "写 lesson"

- **review 周期模糊**: 什么时候该 review? 靠人记起, 容易漏



## 修复方案



1. 新增 `scripts/lessons/bypass_weekly_review.py`

   - 扫 `.gaf_audit.log` 最近 7 天 (默认)

   - 统计高频 bypass reason (top 5)

   - 生成 markdown 复盘段落, 追加到 `.ai-memory/meta/failure-modes.md`

2. 新增 8 个 pytest 用例覆盖解析/过滤/聚合/写入/dry-run/垃圾行容忍

3. 转化决策阈值: 同一 reason >=3 次 → **提议修工具/写 lesson**; <3 次 → **继续观察**

4. 5 层分发: lesson + arch #43 + failure-modes N121 + SKILL §3.2 ⑮ + rules §5.12 + spec/tasks.md



## 使用方式



```bash

# 默认 7 天

python GAF/scripts/lessons/bypass_weekly_review.py



# 干跑看输出

python GAF/scripts/lessons/bypass_weekly_review.py --dry-run --days 30



# 测试

pytest GAF/scripts/tests/test_bypass_weekly_review.py -v -p no:django

```



## 验证



- `pytest scripts/tests/test_bypass_weekly_review.py -v -p no:django` → 8/8 passed

- `python scripts/lessons/bypass_weekly_review.py --dry-run --days 30` → 正确读取 2 条 BYPASS 记录



## 关联



- failure-modes N121 (新)

- architecture-mistakes.md #43 N121

- .trae/rules/project_rules.md §5.12

- .trae/skills/gaf-reflect-and-evolve/SKILL.md §3.2 ⑮

- docs/specs/legacy-trae/build-gaf-knowledge-system/tasks.md §3.6
