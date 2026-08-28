---
date: 2026-06-14
symptom:
- spec:overengineering
- 过度设计
- spec-膨胀
- meta-recursion
- scope-creep
solution: v9 限行 + 零和博弈（删 1 加 1）
related_files:
- .trae/rules/project_rules.md
created_by: AI
priority: medium
diff_keywords: ["spec", "overengineering", "scope-creep", "line-limit"]
---



# Spec 自身膨胀失控

## 症状

- v7 1650 行 → v8 限 1500 → v8.1 限 2100 → v8.2 实际 2252 行
- 每次升级加 6-11 个新节，从不删除旧节
- 漏洞分析历史无限增长（v7 §0.7-§0.10 → v8.2 §0.6 5 个子节）

## 根因

- "AI 自我治理"模块空想，砍了 A.26-A.29 后仍新增 dashboard 等模块
- spec 演化没有"零和博弈"机制
- 元分析（漏洞修复路径）当 spec 内容写

## 解决步骤

1. v9 限行 1500（v8.2 的 2100 放宽是错误）
2. 任何 v9 修订必须删 1 旧节才能加 1 新节
3. 元分析（漏洞修复）移出 spec.md，归档到 `appendices/changelog/`

## 验证

- spec.md 行数 ≤ 1500
- 修订 diff 中 `+` 行数 ≤ `-` 行数

## 预防

- 行数检测加 pre-commit hook
- 任何 PR 改 spec.md > 100 行需单独标注
