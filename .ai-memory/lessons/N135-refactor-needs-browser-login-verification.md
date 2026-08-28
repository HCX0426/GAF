---
id: N135
date: 2026-06-28
symptom: 'After bulk refactoring F012 (store rename) and F020 (PageWrapper adoption),
  frontend failed to render at /login with Vite 500 errors: missing ''./authStore''
  imports and JSX tag mismatches. npx tsc --noEmit returned 0 errors, so static checks
  did not catch the regressions.'
category: testing
cause: Static type checking has blind spots for Vite module resolution and JSX parser
  differences. Bulk refactors using PowerShell regex or sub-agents missed cross-file
  references (main.tsx, store cross-imports, test mocks) and introduced JSX tag/import
  errors in 17 pages. No browser login verification was run after the refactor commits.
solution: '1. Fix all broken imports: main.tsx, useUnattendedStore.ts, useAiLabStore.ts
  -> ./useAuthStore; 3 test mocks -> useDeviceStore/useTaskStore.
  2. Fix 11 PageWrapper-migrated pages: add missing imports, correct opening/closing
  tags, close divs.
  3. Verify with Playwright login: http://localhost:5173/login -> /dashboard, 0 console
  errors.
  4. Record N135 lesson and distribute to project_rules.md hard constraints.
  '
priority: high
diff_keywords: ["after", "bulk", "refactoring", "f012", "store", "rename", "and", "f020", "pagewrapper", "adoption"]
related_files:
- frontend/src/main.tsx
- frontend/src/stores/useUnattendedStore.ts
- frontend/src/stores/useAiLabStore.ts
- scripts/e2e/scenarios/browser_login.py
cross_refs:
- N128
- N130
- N134
created_by: AI
level: L1
n_id: N135
topic: testing
---





# N135 — Bulk refactor must be followed by browser login verification

## What happened

While executing the user's request to "re-check all fixed items after completion" (修完后重新检查所有已修复项), I attempted to log into the GAF frontend using Playwright. The login page returned Vite 500 errors instead of rendering:

```text
Failed to resolve import "./authStore" from "src/main.tsx"
Failed to resolve import "./authStore" from "src/stores/useUnattendedStore.ts"
Failed to resolve import "./authStore" from "src/stores/useAiLabStore.ts"
```

And multiple JSX parse errors in PageWrapper-migrated pages:

```text
Expected corresponding JSX closing tag for 'PageWrapper'
Expected corresponding JSX closing tag for 'div'
```

Surprisingly, `npx tsc --noEmit` returned **0 errors** and `manage.py check` returned **0 issues**.

## Root cause

1. **Static checks missed module resolution errors**: TypeScript compiler does not validate Vite's exact file path resolution in the same way the dev server does. `./authStore` vs `./useAuthStore` was not flagged.

2. **JSX parser differences**: tsc accepted malformed JSX that Vite's Oxc transform rejected.

3. **Bulk refactor without end-to-end smoke test**: F012 store rename used PowerShell bulk regex on 36 imports but missed `main.tsx` and cross-store imports. F020 PageWrapper migration used a sub-agent that introduced tag/import mismatches in 11 of 17 pages.

4. **No login verification after refactor**: If Playwright/browser-use login had been run immediately after F012/F020 commits, the regressions would have been caught before the user discovered them.

## Fix

Commit `-` repaired all regressions:

- `frontend/src/main.tsx`: `./authStore` → `./useAuthStore`
- `frontend/src/stores/useUnattendedStore.ts`: `./authStore` → `./useAuthStore`
- `frontend/src/stores/useAiLabStore.ts`: `./authStore` → `./useAuthStore`
- 3 test files: `deviceStore`/`taskStore` mock paths → `useDeviceStore`/`useTaskStore`
- 11 PageWrapper pages: added missing imports, fixed opening/closing tags, closed divs

Verification:

```text
URL: http://localhost:5173/login
Title: GAF — 自动化平台
After login URL: http://localhost:5173/dashboard
After login title: GAF — 自动化平台
Console errors: 0
Screenshot saved to .trash/gaf_dashboard.png
```

## Prevention

- After any bulk refactor involving import paths, directory moves, or component wrapping, **always run a browser login smoke test** before declaring done.
- `tsc --noEmit` passing is necessary but not sufficient for frontend availability.
- Prefer codemod tools over regex/sub-agent for high-risk bulk changes; if using sub-agents, require per-file browser verification.
- Re-use existing GAF smoke test: `scripts/e2e/scenarios/browser_login.py`.

## 5-layer distribution

- ① lessons: this file
- ② architecture-mistakes: summary added to architecture-mistakes.md
- ③ spec: full-audit-2026-06-27.md §十八
- ④ SKILL.md: evaluated; verification-before-completion skill already covers this
- ⑤ project_rules.md: §6.4 index + §6.5 hard constraint added

## 家族成员复发时间线（v9.0 合并 — 2026-07-07）

> **来源**: gaf-workflow-v9-slim Task 2.1 — 同根因家族合并
> **主条目**: 本文件 (N135 — bulk refactor must be followed by browser login verification)
> **家族根因**: refactor 后只跑静态检查 (tsc/manage.py check) 不够，必须浏览器登录验证

| 日期 | 编号 | 事件 | 已合并自 |
|------|------|------|---------|
| 2026-06-28 | N135 | F012 store rename + F020 PageWrapper 批量重构后 Vite 500 错误, tsc 0 错误但前端不可用 | (本主条目) |
| 2026-07-05 | N135-ws-provider | WebSocketProvider 已定义但未 mount 在 React tree, AppLayout 重复 connect 逻辑导致 race condition; 浏览器验证才发现 | `2026-07-05-n135-ws-provider-must-be-mounted.md` (已删除) |

**家族共性预防**:
- 任何涉及 import 路径/目录移动/组件包裹的批量 refactor，commit 后必须浏览器登录验证
- tsc 0 错误 ≠ 前端可用 (Vite 模块解析 + JSX parser 有盲区)
- Provider/Component 定义 ≠ 已 mount，必须 Grep JSX 标签验证
- 复用 GAF smoke test: `scripts/e2e/scenarios/browser_login.py`
