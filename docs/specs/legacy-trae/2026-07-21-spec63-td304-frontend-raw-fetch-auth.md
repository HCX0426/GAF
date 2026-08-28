---
spec_id: spec-63
title: TD-304 前端 raw fetch 鉴权 + URL 漏洞修复 (DailySummaryCarousel + InfraHealthPanel)
status: ✅ done
created: 2026-07-21
completed: 2026-07-21
owner: AI
task_type: bug_fix
td_refs: [TD-304]
---

# spec-63: TD-304 前端 raw fetch 鉴权 + URL 漏洞修复

## 背景

spec-59-E 后 L3-1 全量扫描发现 2 处 raw fetch 绕过 axios client, 导致鉴权 + URL 路由问题:
1. `DailySummaryCarousel.tsx:49` `fetch('/api/unattended/progress/')` 无 Authorization header → 后端 `@permission_classes([IsAuthenticated])` 401 → catch block 静默吞, 组件显示空数据
2. `InfraHealthPanel.tsx:78` `fetch('/api/system/health/')` URL 不存在 (实际路由 `/api/v2/accounts/init/health/`) + 缺 auth → 404 → catch block 静默吞返回 null, 组件显示 "API unavailable"

## 修复方案

### Phase 1: 修 2 处 raw fetch

- [x] 1.1 DailySummaryCarousel.tsx:49 raw fetch → fetch + buildAuthHeaders (保留 fetch 不迁 axios, 最小改动)
- [x] 1.2 InfraHealthPanel.tsx:78 修 URL `/api/system/health/` → `/api/v2/accounts/init/health/` + 加 buildAuthHeaders

### Phase 2: 验证

- [x] 2.1 grep "fetch('/api/" frontend/src/ → 2 处全部带 buildAuthHeaders ✅
- [x] 2.2 grep "system/health" frontend/src/ → 0 处实际 URL 调用 (仅 1 处出现在 TD-304 fix 注释中说明已修正) ✅
- [x] 2.3 前端 tsc 类型检查通过 (修改的 2 文件均未引入新 TS 错误) ✅
- [x] 2.4 pre-commit hook 全过 (commit 时验证) ✅

## 反思 (小修改 < 50 行, 跑 ① 4 问 + ④ 状态标记)

### ① 4 问反思

1. **解决什么问题**: 前端 2 处 raw fetch 绕过 axios client 导致鉴权缺失 (401 静默吞) + URL 路由错误 (404 永远 unavailable)
2. **根因**: H12/F002/F005 修复同模式时遗漏这 2 个文件 (spec-59-E L3-1 ④ 界面层 + ⑨ 集成层扫描发现)
3. **方案选择**: A. raw fetch + buildAuthHeaders (最小改动 2 行) vs B. 迁移到 axios client (改动大需重构) → 选 A, 与 H12 修复保持一致
4. **验证**: grep 0 处遗漏 ✅ + tsc 类型检查 ✅ + pre-commit hook ✅

### ④ 状态标记

- spec-63: 🔄 in_progress → ✅ done
- TD-304: 🔧 待修 → ✅ FIXED (迁移到 fixed.md)
- active.md 顶部计数: 9 → 8
- completed-features.md: C-102 追加
- pending-roadmap.md: P-043 追加
