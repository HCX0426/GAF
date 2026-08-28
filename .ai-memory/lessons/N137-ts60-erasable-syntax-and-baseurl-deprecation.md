---
date: 2026-06-30
symptom: [version-compat, frontend-tooling, erasableSyntaxOnly, enum, baseUrl, ignoreDeprecations, TypeScript 6.0]
solution: TS 6.0 migration — erasableSyntaxOnly forbids enum (use const object + union type); baseUrl deprecated (use relative paths without baseUrl, remove ignoreDeprecations root cause)
diff_keywords: ["tsconfig", "app", "tsconfig.app", "node", "tsconfig.node", "errorhandler", "version", "compat", "version-compat", "tech", "stack", "tech-stack"]
related_files:
  - frontend/tsconfig.app.json
  - frontend/tsconfig.node.json
  - frontend/src/utils/errorHandler.ts
  - docs/reference/version-compat.md
  - docs/reference/tech-stack.md
created_by: AI
priority: high
cross_refs: []
l2_candidate: true
level: L1
n_id: N137
topic: version-compat
---


# N137 — TS 6.0 erasableSyntaxOnly + baseUrl Deprecation

## Symptom (症状)

Two distinct TS 6.0 migration errors surfaced when the frontend tsconfig enabled
`erasableSyntaxOnly` and the IDE flagged `ignoreDeprecations`:

1. **`erasableSyntaxOnly` rejects `enum`**: `export enum ErrorType { ... }` at
   `frontend/src/utils/errorHandler.ts:14` produced
   `启用 'erasableSyntaxOnly' 时，不允许使用此语法` (TS 5.8+).
2. **`ignoreDeprecations: "6.0"` reported invalid by IDE**: The IDE showed
   `"--ignoreDeprecations"的值无效` on `frontend/tsconfig.app.json:9`, even
   though `tsc 6.0.3` accepts the value. Root cause: `baseUrl: "."` is
   deprecated in TS 6.0, which is why `ignoreDeprecations` was needed at all.

## Root Cause (根因)

- **erasableSyntaxOnly (TS 5.8+)**: Disallows syntax that emits runtime code —
  `enum`, `namespace` with runtime code, parameter properties in constructors.
  `enum` generates a reverse-mapping object at runtime, so it is rejected.
- **baseUrl deprecation (TS 6.0)**: `baseUrl` is deprecated. `paths` can now
  use relative patterns (e.g. `"./src/*"`) without `baseUrl`, resolved relative
  to the tsconfig file location. `ignoreDeprecations: "6.0"` was an escape hatch
  for the deprecated `baseUrl`; the IDE (bundling TS 5.x) didn't recognize `"6.0"`
  as a valid value and reported it invalid.

## Fix (修复)

1. **enum → const object + union type** (`errorHandler.ts`):
   ```ts
   export const ErrorType = {
     NETWORK: 'network',
     AUTH: 'auth',
     SERVER: 'server',
     CLIENT: 'client',
     TIMEOUT: 'timeout',
     UNKNOWN: 'unknown',
   } as const;
   export type ErrorType = (typeof ErrorType)[keyof typeof ErrorType];
   ```
   Fully erasable (no runtime code beyond the plain object). Preserves both
   value access (`ErrorType.NETWORK`) and type usage (`type: ErrorType`).
   All 4 consumers (Login, Marketplace, Resources, errorHandler itself) remained
   compatible — no caller changes needed.

2. **Remove baseUrl + ignoreDeprecations** (`tsconfig.app.json`):
   ```jsonc
   // BEFORE
   "ignoreDeprecations": "6.0",
   "baseUrl": ".",
   "paths": { "@/*": ["src/*"] }

   // AFTER
   "paths": { "@/*": ["./src/*"] }
   ```
   Remove the deprecated option (root cause) instead of bumping the escape
   hatch. Verified: 110 files import from `@/` and all resolve; only 1
   pre-existing stale test import (`Devices/index`) remains, unrelated.

## Prevention (预防)

- When enabling `erasableSyntaxOnly`, audit all `enum` declarations and convert
  to `const` object + `as const` + union type. `enum` is the most common offender.
- When TS reports a deprecated option, prefer **removing the deprecated option**
  over adding/raising `ignoreDeprecations`. Escape hatches accumulate tech debt.
- TS 6.0+: `paths` works without `baseUrl` — use relative patterns like
  `"./src/*"`. Don't add `baseUrl` back for new tsconfigs.
- IDE bundled TS may lag workspace TS. If the IDE reports a config value invalid
  but `npx tsc` accepts it, the IDE is using an older bundled TS — either ignore
  (if the option is being removed anyway) or set `typescript.tsdk` in
  `.vscode/settings.json` to the workspace TS.

## Evidence (3 步)

- **Problem**: `errorHandler.ts:14` enum rejected by erasableSyntaxOnly;
  `tsconfig.app.json:9` ignoreDeprecations flagged invalid by IDE.
- **Solution**: enum → const object + union type; removed baseUrl + ignoreDeprecations,
  switched paths to relative `./src/*`. Commit `-`.
- **Verification**: `npx tsc --version` → 6.0.3; `npx tsc --noEmit -p tsconfig.app.json`
  reports no config-level errors; 110/110 `@/` imports resolve (1 pre-existing
  stale test import unrelated).

## Related

- `docs/reference/version-compat.md` §2.4 (TypeScript 6.0) — updated with these specifics.
- `docs/reference/tech-stack.md` — Frontend uses TypeScript 6.0.
