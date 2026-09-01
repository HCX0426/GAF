---
spec_id: spec-112
title: TD-330 sub-spec 20 — AuditLogPage + LogCenterPage hex color → antd token 治理
created: 2026-07-22
status: ✅ done
commit: '-'
related_td: [TD-330]
related_n: [N167, N151]
depends_on: [spec-111]
blocks: []
priority: P2
size: 小 (2 文件 ~2 hex 治理, ~6 行 diff)
---

# spec-112: TD-330 sub-spec 20 — AuditLogPage + LogCenterPage hex color → antd token 治理

## 背景

TD-330 全局 hex 治理第 20 个 sub-spec。两文件均含 1 处相同 hex `#f5f5f5` (JSON pre 背景):
- `frontend/src/pages/System/AuditLogPage.tsx` L312: `style={{ background: '#f5f5f5', borderRadius: 4, maxHeight: 400, overflow: 'auto' }}`
- `frontend/src/pages/Ops/Logs/LogCenterPage.tsx` L548: `style={{ background: '#f5f5f5', borderRadius: 4, maxHeight: 400, overflow: 'auto' }}`

两文件均未用 useToken(),需添加。

## 治理方案

### A 类 (直接迁移 → antd token)

| 文件 | 行 | 原 hex | 替换 | 说明 |
|---|---|---|---|---|
| AuditLogPage | L312 | `#f5f5f5` | `token.colorFillQuaternary` | 四级填充色 (pre 背景) |
| LogCenterPage | L548 | `#f5f5f5` | `token.colorFillQuaternary` | 四级填充色 (pre 背景) |

注: `#f5f5f5` 在 antd v5 语义层面对应 `colorFillQuaternary` (最浅填充色),与 `colorBgLayout` 略有差异 (后者略偏蓝白)。此处选 colorFillQuaternary 保持 pre 块视觉接近。

### C 类 (保留)

无 C 类保留 (2 hex 全为 antd 语义色对应)。

## 验收标准

- hex color 2 → 0 (2 文件各 1 → 0, 无 C 类保留)
- `npx tsc --noEmit` 0 errors
- 视觉等价 (colorFillQuaternary 与原 #f5f5f5 在默认主题下视觉接近)

## 实施步骤

1. ✅ Phase 1: spec 文件创建
2. ✅ Phase 2: 代码改动 + tsc 检查
3. ✅ Phase 3: commit + N176 hash 回填
