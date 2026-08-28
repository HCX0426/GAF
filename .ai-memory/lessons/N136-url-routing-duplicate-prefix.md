---
id: N136
date: 2026-06-29
symptom: Backend tests (agents/tests/) failed with 405/404 on /api/v2/agents/ and
  /api/v2/devices/ because backend/config/urls.py mounted agents.urls at /api/v2/agents/ while
  the app internally defines /agents/ and /devices/ resources, creating doubled paths
  /api/v2/agents/agents/ and /api/v2/agents/devices/. Frontend used doubled paths
  as a workaround, masking the root cause.
category: architecture
cause: 'URL mounting anti-pattern: the Django app name ''agents'' was used as both
  the mount prefix in backend/config/urls.py AND a resource name inside backend/agents/urls.py. This
  created duplicate path segments. The app defines multiple resources (agents, devices,
  device-groups) but was mounted at a single-resource prefix, breaking the contract
  that mount prefix + resource path = final URL with no duplication.'
solution: '1. Mount agents.urls at /api/v2/ (API root) instead of /api/v2/agents/
  in backend/config/urls.py
  2. Update all frontend API paths: /agents/agents/ -> /agents/, /agents/devices/
  -> /devices/, /agents/device-groups/ -> /device-groups/
  3. Update 7 backend docstring path references in agents/views.py
  4. Fix test_token_api.py: /api/v2/auth/agent-tokens/ -> /api/v2/accounts/auth/agent-tokens/
  (missing /accounts/ prefix)
  5. Fix test_device_api.py: device_type ''adb'' -> ''emulator'' (invalid choice value,
  valid: windows/emulator)
  6. Update docs: api-contract.md, backend-conventions.md, data-flow.md
  7. Document URL routing mounting convention in backend-conventions.md §5.2
  8. Document code quality three principles in project_rules.md §2.0
  '
priority: high
diff_keywords: ["backend", "tests", "agents", "failed", "with", "api", "and"]
related_files:
- backend/config/urls.py
- backend/agents/urls.py
- backend/agents/views.py
- backend/agents/tests/test_device_api.py
- backend/agents/tests/test_token_api.py
- frontend/src/api/agents.ts
- frontend/src/api/devices.ts
- docs/standards/backend-conventions.md
- docs/standards/api-contract.md
cross_refs:
- N112
- N129
created_by: AI
level: L1
n_id: N136
topic: api-design
---




# N136 — URL routing duplicate prefix anti-pattern

## What happened

`backend/agents/tests/` had 10+ pre-existing test failures:
- `test_agent_core.py`: 405 on POST `/api/v2/agents/` (Method Not Allowed)
- `test_device_api.py`: 404 on POST `/api/v2/devices/` (Not Found)
- `test_token_api.py`: 404 on `/api/v2/auth/agent-tokens/` (wrong path)

Root investigation revealed `backend/config/urls.py` mounted `agents.urls` at `/api/v2/agents/`:
```python
path(f"{API_PREFIX}/agents/", include("agents.urls")),
```

But `backend/agents/urls.py` internally defines:
```python
router.register(r'agents', AgentViewSet, basename='agent')
router.register(r'devices', DeviceViewSet, basename='device')
```

This created doubled paths: `/api/v2/agents/agents/` and `/api/v2/agents/devices/`.

The frontend had been using these doubled paths (`/agents/agents/`, `/agents/devices/`) as a workaround, so the UI worked but tests hitting the correct paths (`/api/v2/agents/`, `/api/v2/devices/`) failed.

## Root cause

1. **App name = resource name collision**: The Django app is named `agents` and also defines an `agents` resource. Mounting at `/api/v2/agents/` duplicated the path segment.
2. **App defines multiple resources**: The `agents` app defines `agents`, `devices`, and `device-groups` resources, but was mounted as if it only contained one resource.
3. **Frontend workaround masked the bug**: Frontend used doubled paths to match the broken backend, hiding the issue from manual testing.
4. **Test path bugs were pre-existing**: `test_token_api.py` used `/api/v2/auth/` instead of `/api/v2/accounts/auth/`; `test_device_api.py` used invalid `device_type='adb'` (choices: windows/emulator).

## Fix

- Commit `-`: Mount `agents.urls` at `/api/v2/` + update docs/docstrings
- Commit `-`: Align all frontend API paths (6 files)
- Commit `-`: Fix test paths and invalid test data
- Commit `-`: Document mounting convention + code quality principles

Verification: all 41 agents tests pass:
```
======================= 41 passed, 1 warning in 21.75s ========================
```

## Prevention

- ✅ **Mount prefix + resource path = final URL, no duplication**: If app defines `/agents/` resource, don't mount at `/api/v2/agents/`
- ✅ **Multi-resource app → mount at API root**: `path(f"{API_PREFIX}/", include("app.urls"))`
- ✅ **Single-resource app (name = resource) → mount at app name**: `path(f"{API_PREFIX}/tasks/", include("tasks.urls"))`
- ✅ **Fix root cause, not symptoms**: Don't use frontend doubled paths as workaround for backend bug
- ✅ **Test data must use valid choices**: Check model `choices` before using values in tests
- ❌ **Don't use app name as mount prefix when app defines multiple resources**
- ❌ **Don't use doubled paths in frontend to work around backend routing bug**

## 5-layer distribution

- ✅ ① lessons: this file created
- ✅ ② architecture-mistakes: entry added
- ✅ ③ docs: backend-conventions.md §5.2 + api-contract.md paths updated
- ✅ ④ SKILL.md: gaf-lesson-router taxonomy updated
- ✅ ⑤ project_rules.md: §2.0 code quality principles + URL routing convention
