# verification.md — P6 verification evidence (naming-g P6)

## P6.1
- api.generated.ts regenerated: 1027 insertions / 1046 deletions (types/ws-events + auth + consumers).
- `npx tsc -b --force`: 11 errors, ALL pre-existing cross-spec drift — 9 present at HEAD + 2 DeviceDetailPanel emulator→emulator_brand newly exposed by truthful regen (registered TD-422). 0 introduced.
- eslint: 0 errors (3 pre-existing react-hooks/refs warnings).
- B2 acknowledged: is_big=2122 (`.cache/b2_acknowledged.json`).

## P6.2
- Script: word-boundary replace, 122 replacements / 30 files (list in solution.md); excluded 8 files.
- Residual check: word-boundary `Agent` residual = 0 (identifier-embedded only: fetchAgents/useAgentsQuery/AgentHealthPanel/fetchAgentDebug/agents var/activeAgentIdRef — deliberately kept).
- Key integrity: `settings.agent_debug_enable` key unchanged, value now 'Worker 调试模式'; `settings.agent_debug_saved` etc. intact (`_agent` keys untouched).
- vitest (targeted, 5 files): 47 passed, 0 failed — Dashboard.test/Dashboard.test(online + 健康面板 Worker text), SystemSettingsPage.test, useDeviceStore.test, api-paths.test, Devices.test.
- eslint `src --max-warnings=0`: 1 error / 1176 warnings; the single error = `no-useless-assignment` at LiveAnnotationTab.tsx:696 — file untouched by sweep (HEAD diff empty), pre-existing.
- tsc: still 11 errors (identical set), 0 new.
- `git diff HEAD --stat`: 33 files, 125 insertions / 124 deletions (P6.2 commit 395c861).

## Governance
- B2 acknowledged before commit (is_big: True — API 契约文件 api/*.ts docstring 改动触发规则).
- pre-commit + post-commit hooks all Passed; `git log --oneline -1` → 395c861.
- Phase updated: spec P6 ✅; carrier phase G-P7 + decision_log P6.2 entry.