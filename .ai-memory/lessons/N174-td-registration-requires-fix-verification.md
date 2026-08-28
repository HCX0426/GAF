---
date: 2026-07-18
topic: [workflow]
priority: high
cross_refs: [N173, §4.8, §4.9]
status: active
created_by: AI
trigger: 三维评估发现 TD-129/130 修复方向反转 (TD 原方案 "保留 last_error 删 error_message" 错了, 实际 error_message 有 25+ 写入点)
symptom: [td-fix-direction-reversed, 41-percent-wontfix-rate, td-registration-no-grep-verification]
solution: TD 登记必填 "修复方案验证" 字段 — 至少 1 个 grep 命令验证修复方向 (避免 TD-129/130 反转重演); 41% wontfix 率说明 TD 登记时未充分盘点现有实现
diff_keywords: [td-fix, fix-verification, grep-check, wontfix]
related_files:
  - .trae/rules/project_rules.md
  - .ai-memory/meta/ai-operating-handbook.md
  - .ai-memory/meta/failure-modes.md
  - .ai-memory/meta/yn-matrices/archived-yn-matrices/_workflow-spec.md
  - docs/project-status.md
---

# N174 — TD 登记必填"修复方案验证"字段

> **家族**: workflow (与 N173 spec/plan 用时测量同族, 都是"AI 自检机制")
> **L1 分级**: L1-中 (新 AI 行为反模式 + 流程环节, 3 层分发: lesson + rules + handbook)

## 1. 症状 (三维评估发现)

TD-129/130 修复方向反转:
- **TD-129 原方案**: "保留 last_error, 删 error_message" — 反转: 实际 last_error 0 写入, error_message 25+ 写入
- **TD-130 原方案**: "保留 metadata, 删 extra_info" — 反转: 实际 metadata 0 使用, extra_info 有使用

**wontfix 比例**: 本会话 17 个 TD 处理中 7 个 wontfix (41%), 其中 3 个是修复方向反转 (TD-128/129/130)

## 2. 根因

TD 登记时未强制 grep 验证修复方案:
- 登记者凭印象写"保留 X 删 Y", 未跑 `grep -r "X\|Y" backend/` 验证哪个字段实际有写入/读取
- 后续 wontfix 评估时才发现方案错了, 浪费评估时间

## 3. 修复方案

### TD 登记必填字段 (active.md 模板新增)

```markdown
### TD-XXX: [标题]
- **症状**: ...
- **根因**: ...
- **修复方案**: ...
- **修复方案验证**: <!-- 至少 1 个 grep 命令验证修复方向 -->
  - `grep -r "<字段A>" backend/` → N matches (写入点)
  - `grep -r "<字段B>" backend/` → 0 matches (死字段)
- **影响**: ...
- **何时修**: ...
- **登记时间**: ...
```

### AI 自检 (登记 TD 时跑)

1. 写完"修复方案"后, 立即跑 grep 验证关键字段的使用情况
2. grep 结果写入"修复方案验证"字段
3. 如果 grep 结果与修复方案矛盾, 立即调整修复方案

## 4. Y/N 检查矩阵

| # | 检查项 | Y/N |
|:-:|--------|:---:|
| 1 | TD 登记时是否跑 grep 验证修复方案? | ☐ |
| 2 | grep 结果是否写入"修复方案验证"字段? | ☐ |
| 3 | grep 结果与修复方案矛盾时是否调整方案? | ☐ |
| 4 | wontfix 评估时是否先核查"修复方案验证"字段? | ☐ |

## 5. 与现有规则的关系

- §4.8 技术债务登记: 补充"修复方案验证"必填字段
- N173 spec/plan 用时测量: TD 登记也属于"plan"范畴, 应测用时 + 验证修复方向
- §2.0 三原则 (扩展性/逻辑正确性/命名正确性): "逻辑正确性"要求 TD 修复方案必须逻辑自洽

## 6. 验证 evidence

- 本 lesson 文件创建: `workflow_2026-07-18-n174-td-registration-requires-fix-verification.md`
- failure-modes.md §Active 追加 N174 索引行
- ai-operating-handbook.md Part 2 追加 N174 行为红线
- project_rules.md §4.8 追加 N174 强化约束
- yn-matrices/_workflow-spec.md §N174 追加 Y/N 矩阵

## 7. 相关文件路径

- `d:\code\GAF\.trae\rules\project_rules.md` §4.8 (技术债务登记)
- `d:\code\GAF\.ai-memory\meta\ai-operating-handbook.md` Part 2 (AI 行为红线)
- `d:\code\GAF\.ai-memory\meta\failure-modes.md` §Active (N## 索引)
- `d:\code\GAF\.ai-memory\meta\yn-matrices\_workflow.md` (Y/N 矩阵)
- `d:\code\GAF\docs\archive\active-tech-debt.md` (TD 登记模板)
