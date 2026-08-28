---
id: N131
date: 2026-06-22
symptom: AI cannot log into the local GAF frontend automatically; Windows env lacks
  bash/browser-use CLI; first Playwright run surfaces a 404 on /api/v2/init/status/
category: testing
cause: Browser automation toolchain not declared in project deps; frontend LoginPage
  uses client.get('/init/status/') while the backend endpoint lives under /api/v2/accounts/init/status/
solution: '1. Add playwright to pyproject.toml [project.optional-dependencies] dev.
  2. Run `python -m playwright install chromium` (downloads ~300 MB to `%LOCALAPPDATA%\ms-playwright`).
  3. Use Playwright sync API to fill `input[autocomplete="username"]`, `input[autocomplete="current-password"]`,
  click `button[type="submit"]`, wait for URL **/dashboard, and capture console errors
  / page exceptions.
  4. Fix frontend path: `client.get(''/init/status/'')` → `client.get(''/accounts/init/status/'')`
  because the global axios client has baseURL `/api/v2/` and the Django endpoint is
  mounted at `accounts.urls`.
  5. Wire the scenario into `scripts/e2e/run_all.py` as `browser_login` and add it
  to `scripts/e2e/conftest.py::SCENARIO_NAMES`.
  '
priority: high
diff_keywords: ["cannot", "log", "into", "the", "local", "gaf", "frontend", "automatically", "windows", "env", "lacks"]
related_files:
- pyproject.toml
- frontend/src/pages/Login/index.tsx
- scripts/e2e/scenarios/browser_login.py
- scripts/e2e/run_all.py
- scripts/e2e/conftest.py
cross_refs:
- N118
- N122
created_by: AI
level: L1
n_id: N131
topic: browser-automation
---




# N131 — Browser automation toolchain + frontend path mismatch

## What happened

The user asked the AI to log into the GAF frontend and read console information to drive improvements. The Windows dev box had no `bash.exe`, no `browser-use` CLI, and no `playwright`/`selenium`. The only available tool was Python's `webbrowser` module, which can open a URL but cannot interact with the page.

After installing Playwright and Chromium, the first automated login succeeded but exposed two console errors:

```text
Failed to load resource: the server responded with a status of 404 (Not Found)
http://127.0.0.1:5173/api/v2/init/status/:0
```

The backend endpoint actually exists at `/api/v2/accounts/init/status/`, but the login page called `client.get('/init/status/')` with the global axios client whose `baseURL` is `/api/v2`.

## Fix

- Added `playwright>=1.40,<2.0` to `pyproject.toml` dev dependencies.
- Installed Chromium via Playwright's browser manager.
- Fixed the frontend URL: `/init/status/` → `/accounts/init/status/`.
- Created `scripts/e2e/scenarios/browser_login.py` and registered it in the e2e runner.

## Takeaways

1. **Do not assume browser automation is available.** On Windows, `bash` and `browser-use` may be missing; declare Playwright in project dev deps so the toolchain is reproducible.
2. **Console-reading smoke tests catch path drift.** A 404 on a setup endpoint does not block login (the page falls back to `registerEnabled=true`), but it is a real bug that only appears in a real browser.
3. **Frontend axios paths must match Django URL mounting.** When an endpoint is included under `accounts.urls`, the frontend must request `/accounts/<endpoint>/`, not `/<endpoint>/`.
