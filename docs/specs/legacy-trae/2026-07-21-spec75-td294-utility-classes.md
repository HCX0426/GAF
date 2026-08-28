---
spec_id: spec-75
title: TD-294 Phase 3a — 扩展 utility class 体系 (Phase 3 前置依赖)
created: 2026-07-21
status: ✅ done
td: TD-294 (Phase 3a/4, 前置依赖)
commit: -
---

# spec-75: TD-294 Phase 3a — 扩展 utility class 体系

## 范围评估 (Phase 3a)

Phase 3 (高密度 inline style → className) 的前置依赖 — subagent 评估 4 文件 109 处 inline style，可迁移 68 处 (62.4%)，但其中 67 处需新增 utility class (B 类)。

本 spec 新增 ~12 个高频 utility class (出现 ≥ 3 次)，为 spec-76 批量替换铺路。

## 新增 class 清单 (按高频排序)

1. `.gaf-h-full` — height: 100% (8+ 次)
2. `.gaf-flex-shrink-0` — flex-shrink: 0 (6+ 次)
3. `.gaf-overflow-y-auto` — overflow-y: auto (5+ 次)
4. `.gaf-whitespace-pre-wrap` — white-space: pre-wrap (5+ 次)
5. `.gaf-text-13` — font-size: 13px (4 次)
6. `.gaf-cursor-pointer` — cursor: pointer (3+ 次)
7. `.gaf-position-relative` — position: relative (3+ 次)
8. `.gaf-w-360` — width: 360px (3 次)
9. `.gaf-radius-sm` — border-radius: 4px (多次)
10. `.gaf-radius-md` — border-radius: 6px (多次)
11. `.gaf-radius-lg` — border-radius: 8px (多次)
12. `.gaf-position-absolute` — position: absolute (2+ 次)

低频 class (1-2 次) 不新增，保留 inline style 更经济。

## 验证

- CSS 语法正确 (无未闭合规则)
- 现有测试不破坏 (utility class 是新增, 不影响现有)

## 后续

- spec-76: 4 文件批量替换 68 处 inline style → className
- spec-77+: Phase 4 (toolbar → gaf-toolbar)
