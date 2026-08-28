---
date: 2026-01-01
maintainer: manual
symptom: [library, version, conflict, compatibility, api-deprecated]
solution: 库版本冲突与废弃 API 映射表 — 历史依赖冲突与解决方案
diff_keywords: ["code", "rules", "code-rules", "architecture", "mistakes", "architecture-mistakes", "failure", "modes", "failure-modes", "always", "library", "version"]
related_files:
  - .ai-memory/summaries/code-rules.md
  - .ai-memory/summaries/architecture-mistakes.md
  - .ai-memory/meta/failure-modes.md
created_by: AI
priority: high
load_when: [always]
source: handwritten
---


# Library Conflicts & Version Incompatibilities

> **MANDATORY: Read this file before every coding task.**
> These are ACTUAL conflicts encountered in GAF development.
> Last updated: 2026-07-18 (TD-184 修复: §1/§3 antd 弃用 API 状态 grep 验证 + 已修复项标注 ✅) | Source: gaf-v2-execution-charter.md reflections

---

## 1. Ant Design v5 Deprecated APIs

> **Status**: 15 files affected across 4 Phases. These WILL cause runtime crashes.
> **TD-184 修复 (2026-07-18)**: grep 实际代码验证各 API 当前状态, 已修复项标 ✅, 仍存在项标 ⚠️

| # | Deprecated API | Correct API | Files Affected | Severity | 当前状态 (2026-07-18 grep) |
|:-:|---------------|------------|---------------|----------|---------|
| 2 | `Space.direction` | `Space.orientation` | EmulatorManagement | 🟡 Deprecation warning | ⚠️ 2 hits in Dashboard (未追踪文件, 待清理) |
| 3 | `Divider.orientation` | `Divider.titlePlacement` | 4 files / 8 places | 🟡 Deprecation warning | ⚠️ 状态未验证（最后确认: 2026-07-18）,需重新 grep 确认 |
| 4 | `Alert.message` | `Alert.title` / `Alert.description` | 10 files / 16 places | 🟡 Deprecation warning | ⚠️ 状态未验证（最后确认: 2026-07-18）,需重新 grep 确认 |
| 5 | `Statistic.valueStyle` | `Statistic.styles.content` | DeviceBenchmark | 🟡 Deprecation warning | ⚠️ 状态未验证（最后确认: 2026-07-18）,需重新 grep 确认 |
| 6 | `Collapse` children API | `Collapse` items API | UnattendedStrategySettings | 🔴 Runtime crash | ⚠️ 状态未验证（最后确认: 2026-07-18）,需重新 grep 确认 |
| 7 | `Drawer.width` | `Drawer.size` | TaskDetailDrawer, AuditLogPage | 🟡 Deprecation warning | ⚠️ 状态未验证（最后确认: 2026-07-18）,需重新 grep 确认 |
| 8 | `Descriptions.labelStyle` | `Descriptions.styles.label` | TaskDetailDrawer | 🟡 Deprecation warning | ⚠️ 状态未验证（最后确认: 2026-07-18）,需重新 grep 确认 |
| 9 | `Input.Group` | `Space.Compact` | CronExpressionEditor | 🟡 Deprecation warning | ⚠️ 状态未验证（最后确认: 2026-07-18）,需重新 grep 确认 |
| 10 | `Input.bordered` | `Input.variant` (borderless/outlined) | ApiKeysPage, GlobalSearchModal | 🟡 Deprecation warning | ⚠️ 状态未验证（最后确认: 2026-07-18）,需重新 grep 确认 |
| 11 | `Modal.confirm()` static | `App.useApp().modal.confirm()` | DeviceGroupManager | 🟡 Deprecation warning | ⚠️ 状态未验证（最后确认: 2026-07-18）,需重新 grep 确认 |
| 12 | `Modal.success()` static | `App.useApp().modal.success()` | UserManagePage | 🟡 Deprecation warning | ⚠️ 状态未验证（最后确认: 2026-07-18）,需重新 grep 确认 |
| 13 | `Card.bodyStyle` | `Card.styles.body` | UnattendedControlBar.tsx | 🟡 Deprecation warning | ⚠️ 1 hit 仍存在 (UnattendedControlBar.tsx:326, 待修复) |

**Rule**: When creating new components, ALWAYS use the NEW API. Never copy old deprecated patterns from existing code.

---

## 2. Ant Design Removed Exports

| # | Removed Export | Replacement | File Where Found |
|:-:|---------------|-------------|-----------------|
| 1 | `TestOutlined` | `PlayCircleOutlined` | AiConfigPage.tsx |
| 2 | `CheckOutlined` | `CheckCircleOutlined` | Notifications/index.tsx, DeviceGroup.tsx |

**Rule**: Always check @ant-design/icons v5 exports before importing. Do not assume icon names exist.

---

## 3. Ant Design List Component

- `antd List` component has been **removed** in current version
- **14 files** crashed with `List is not defined` at runtime
- **Fix**: Replace with plain `div` + `map()` structure
- **当前状态 (2026-07-18 grep, TD-184)**: 3 hits — 1 tracked file (`UnattendedControlBar.tsx` 仍 import + 使用 List) + 2 untracked files; 待后续 spec 修复
- **Rule**: Never use `List` — use `div` with CSS flex/grid

---

## 4. React StrictMode Issues

- **Double-mount** causes spurious `AbortController` aborts on test mount
- Affected 3 polling components with useEffect + fetch
- **Fix**: Use `isRealMountRef` pattern to skip test mount cleanup
- **Rule**: When using AbortController in useEffect, filter out AbortError from StrictMode double-mount

---

## 5. @rc-component/table Internal API

- `useFlattenRecords` returns `getRowKey` that can return `null`
- Causes `bodyChildren` array with null keys → React key warning
- **Fix**: Use `index.toString()` as fallback key
- **Warning**: This is a node_modules patch — lost after `npm install`
- **Rule**: Document patch approach; re-apply if needed after dependency updates

---

## 6. Vite oxc Parser Sensitivity

| Issue | Bad Pattern | Good Pattern |
|-------|------------|-------------|
| Template literals in JSX | `` `text: ${value}` `` | `'text: ' + value` |
| TS type annotation placement | `'dark': T` | `'dark' }: T` |
| Complex NonNullable assertions | `NonNullable<typeof x>` | Direct type assertion |

**Rule**: Avoid template literals in JSX. Use string concatenation.

---

## 7. React Router v7

- Old route `/system/accounts` needs redirect to new path
- Route registration redundancy causes conflicts
- **Rule**: Use direct rendering, avoid nested route registration for same path

---

## 8. DRF / Django Compatibility

- Django UserSerializer requires `username` field on PUT — missing field causes 400
- **Fix**: Use PATCH for partial updates, or include `username` in PUT body
- `django.utils.timezone` must be imported explicitly — not available implicitly
- **Rule**: Always import `timezone` from `django.utils`

---

## 已修复（归档）

> 以下冲突已修复,移出主表归档保留历史。归档时间: 2026-07-22。

| # | Deprecated API | Correct API | Files Affected | Severity | 修复状态 |
|:-:|---------------|------------|---------------|----------|---------|
| 1 | `Modal.destroyOnClose` | `Modal.destroyOnHidden` | 2 files | 🔴 Runtime crash | ✅ FIXED — `destroyOnClose` 0 hits, `destroyOnHidden` 32 hits (全迁移完成, 2026-07-18 TD-184 验证) |
