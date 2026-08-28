---
maintainer: manual
source: GAF/.ai-memory/evidence/active/2026-08-28-e2e-high-prio-fix/
created_by: AI
last_updated: 2026-08-28
---
## Verification（验证）

$ cd frontend; npx tsc --noEmit
$ cd frontend; npx eslint src/pages/Ops/Executions/analytics/DailySummaryCarousel.tsx src/pages/Accounts/components/AccountRotationRules.tsx src/pages/System/FeatureFlagsPage.tsx
$ cd frontend; npx vitest run --reporter=dot

预期：
- tsc: exit 0，无类型错误。
- eslint: no errors (0 errors, 7 pre-existing warnings)。
- vitest: Test Files 47 passed, Tests 366 passed。
- npm run build: 成功，无 SyntaxError/Unexpected token。
- 无头浏览器复测 5 页 (monitors/feature-flags/game-accounts/notifications/dashboard):
  事件 tab 3 条告警加载、rollout % 后缀、轮换秒数+秒后缀、通知正文渲染，全部无崩溃、无 antd 弃用告警。