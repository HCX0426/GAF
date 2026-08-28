---
summary: zxcvbn 替换评估 (Phase 4.5) — 评估前端密码强度库 zxcvbn 替换方案, 仅评估未改代码
applies_to: [frontend, security, analysis]
last_updated: 2026-07-12
---

# zxcvbn Replacement Evaluation (Phase 4.5)

> Status: Evaluation only. No code changes made. Recommendation below.

## 1. Current Usage Summary

### Dependencies

`frontend/package.json` declares:

```json
"dependencies": {
  "zxcvbn": "^4.4.2"
},
"devDependencies": {
  "@types/zxcvbn": "^4.4.5"
}
```

### Files that use zxcvbn

| File | Usage |
|------|-------|
| `frontend/src/utils/passwordStrength.ts` | Direct import: `import zxcvbn from 'zxcvbn'`. Calls `zxcvbn(password, userInputs)` and reads `result.score`, `result.feedback.warning`, `result.feedback.suggestions`, `result.crack_times_seconds.offline_slow_hashing_1e4_per_second`. |
| `frontend/src/pages/Login/index.tsx` | Indirect: imports `evaluatePasswordStrength` from `passwordStrength.ts`. Renders a `PasswordStrength` component used in the Register, Change Password, and Reset Password forms. |

### API surface in use

The current code uses the following zxcvbn API:

- `zxcvbn(password: string, userInputs: string[])` — synchronous call returning a result object
- `result.score` — integer 0-4 (weak to strong)
- `result.feedback.warning` — string (may be empty)
- `result.feedback.suggestions` — string array
- `result.crack_times_seconds.offline_slow_hashing_1e4_per_second` — number (seconds)

The `passwordStrength.ts` wrapper translates feedback strings to Chinese and maps the score to a UI level/color/percent. The Login page component consumes the wrapper's `PasswordStrengthResult` interface, not zxcvbn directly.

## 2. Maintenance Status (verified via npm and GitHub)

### zxcvbn (dropbox/zxcvbn)

| Metric | Value | Source |
|--------|-------|--------|
| npm version | 4.4.2 | npmjs.com/package/zxcvbn |
| Last publish | ~9 years ago (circa 2017) | npmjs.com (as of 2026-07-10) |
| Total versions | 23 | npmjs.com |
| npm dependents | 494 | npmjs.com |
| Dependencies | 0 | npmjs.com |
| GitHub commits | 379 | github.com/dropbox/zxcvbn |
| Open issues | 117 | github.com/dropbox/zxcvbn |
| Open pull requests | 25 | github.com/dropbox/zxcvbn |
| License | MIT | npmjs.com / GitHub |

**Assessment**: The package is functionally stable but effectively unmaintained. 117 open issues and 25 open PRs with no recent activity indicate the Dropbox team is no longer actively developing it. The core algorithm (pattern matching, dictionary) is frozen at 2017 data — common passwords and patterns have evolved since then.

### @zxcvbn-ts/core (zxcvbn-ts/zxcvbn)

| Metric | Value | Source |
|--------|-------|--------|
| npm version | 4.1.2 | npmjs.com/package/@zxcvbn-ts/core |
| Last publish | 7 days ago (as of 2026-07-10) | npmjs.com |
| Total versions | 29 | npmjs.com |
| npm dependents | 134 | npmjs.com |
| Weekly downloads | 759,501 | npmjs.com |
| Dependencies | 1 | npmjs.com |
| License | MIT | npmjs.com |
| GitHub repo | github.com/zxcvbn-ts/zxcvbn | npmjs.com |

**Assessment**: Actively maintained. Published within the last week, with 29 versions showing continuous development. 759K weekly downloads demonstrate strong adoption. It is a TypeScript rewrite of the original zxcvbn, inspired by the Dropbox project but maintained by an independent community team.

## 3. Options Comparison

| Criterion | zxcvbn@4.4.2 (keep) | @zxcvbn-ts/core (replace) |
|-----------|---------------------|---------------------------|
| **Maintenance** | Unmaintained (~9 years since last publish) | Actively maintained (published 7 days ago) |
| **TypeScript support** | Requires separate `@types/zxcvbn` package | Native TypeScript, types bundled |
| **API style** | `zxcvbn(password, userInputs)` direct call | `new ZxcvbnFactory(options).check(password)` factory pattern |
| **Dictionary data** | Bundled, frozen at 2017 data | Modular: `@zxcvbn-ts/language-common` + `@zxcvbn-ts/language-en`, updatable independently |
| **Bundle size** | ~400KB unminified, ~130KB minified (single bundle, dictionary included) | Core is smaller; dictionary loaded separately. Total comparable but tree-shakeable |
| **Score API** | `result.score` (0-4) | `result.score` (0-4) — identical |
| **Feedback API** | `result.feedback.warning`, `result.feedback.suggestions` | `result.feedback.warning`, `result.feedback.suggestions` — identical |
| **Crack time API** | `result.crack_times_seconds.offline_slow_hashing_1e4_per_second` | `result.crackTimes.secondsOfflineSlowHashing1e4` (camelCase, different path) |
| **userInputs support** | Yes: `zxcvbn(password, userInputs)` | Yes: configured via `options.dictionary.userInputs` |
| **Migration effort** | None (keep as-is) | Low-medium: update 1 file (`passwordStrength.ts`), install 3 packages |
| **Risk** | Low functional risk (works today), but growing security gap as dictionary ages | Low risk: well-tested, widely adopted, active community |

## 4. Recommendation

**Recommendation: Replace zxcvbn with @zxcvbn-ts/core in a future phase.**

### Reasoning

1. **Security currency**: zxcvbn's dictionary data is frozen at 2017. Common passwords, leaked credential patterns, and keyboard layouts have evolved. @zxcvbn-ts/core maintains updatable language packages that can be refreshed without changing the core library.

2. **Active maintenance**: @zxcvbn-ts/core was published 7 days ago with 29 versions and 759K weekly downloads. Bug fixes and security improvements are ongoing. zxcvbn has 117 open issues and 25 stale PRs with no resolution path.

3. **Low migration cost**: Only `frontend/src/utils/passwordStrength.ts` needs changes. The Login page component consumes the wrapper's `PasswordStrengthResult` interface, not zxcvbn directly, so the component layer is insulated from the API difference.

4. **Native TypeScript**: Eliminates the separate `@types/zxcvbn` devDependency and provides first-class type safety.

5. **Not urgent**: zxcvbn@4.4.2 still functions correctly today. The replacement can be scheduled for a maintenance phase without blocking feature work.

### When NOT to replace

- If the team prefers zero-change stability and accepts the aging dictionary risk, keeping zxcvbn@4.4.2 is a valid short-term decision.
- If bundle size is a hard constraint and the additional language packages (`@zxcvbn-ts/language-common`, `@zxcvbn-ts/language-en`) push the budget over limit, a custom-stripped zxcvbn build might be preferable. (This is unlikely given the current Login page already loads the full zxcvbn bundle.)

## 5. Migration Steps (if replacement is approved)

### Step 1: Install new packages

```bash
cd frontend
npm install @zxcvbn-ts/core @zxcvbn-ts/language-common @zxcvbn-ts/language-en
npm uninstall zxcvbn @types/zxcvbn
```

### Step 2: Update `frontend/src/utils/passwordStrength.ts`

Replace the import and initialization:

```typescript
// Before
import zxcvbn from 'zxcvbn';

// After
import { ZxcvbnFactory } from '@zxcvbn-ts/core';
import * as zxcvbnCommonPackage from '@zxcvbn-ts/language-common';
import * as zxcvbnEnPackage from '@zxcvbn-ts/language-en';

const zxcvbnOptions = {
  dictionary: {
    ...zxcvbnCommonPackage.dictionary,
    ...zxcvbnEnPackage.dictionary,
  },
  graphs: zxcvbnCommonPackage.adjacencyGraphs,
  translations: zxcvbnEnPackage.translations,
};
const zxcvbn = new ZxcvbnFactory(zxcvbnOptions);
```

Update the call site in `evaluatePasswordStrength`:

```typescript
// Before
const result = zxcvbn(password, userInputs);

// After
const result = zxcvbn.check(password);
```

Update the crack time field mapping:

```typescript
// Before
result.crack_times_seconds.offline_slow_hashing_1e4_per_second

// After
result.crackTimes.secondsOfflineSlowHashing1e4
```

The `result.score`, `result.feedback.warning`, and `result.feedback.suggestions` fields are identical and need no changes.

### Step 3: Handle userInputs

The current code passes `userInputs` (e.g., username, email) as the second argument to `zxcvbn()`. In zxcvbn-ts, user inputs are configured via the dictionary options. For per-call user inputs, merge them into the dictionary before creating the factory, or create a new factory per evaluation (acceptable for a login form with infrequent calls):

```typescript
const zxcvbn = new ZxcvbnFactory({
  ...zxcvbnOptions,
  dictionary: {
    ...zxcvbnOptions.dictionary,
    userInputs,
  },
});
const result = zxcvbn.check(password);
```

### Step 4: Verify

- Run `npm run dev` and test the Register / Change Password / Reset Password forms
- Verify the strength bar, label, crack time, and suggestions render correctly
- Run `npx vite build` to confirm no TypeScript errors in the production build
- Test with common passwords (e.g., "password", "12345678") to verify score 0-1
- Test with strong passwords (e.g., "correct-horse-battery-staple") to verify score 4

## 6. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Score values differ for edge-case passwords | Low | Low (0-4 scale is the same) | Run side-by-side comparison on sample passwords before deploying |
| Feedback strings differ (Chinese translation map) | Medium | Low (cosmetic) | Update the `feedbackMap` in `passwordStrength.ts` to match new strings; keep fallback (`return feedbackMap[s] || s`) |
| Bundle size increases from 2 extra language packages | Low | Low | Language packages are tree-shakeable; measure with `npx vite build --analyze` |
| userInputs behavior differs | Medium | Low (only affects username/email matching) | Test with the actual registration form; verify common-name detection still works |
| New package introduces a vulnerability | Very Low | Medium | Run `npm audit` after install; @zxcvbn-ts/core has 1 dependency (pocomath), check its status |

## 7. Summary

| Item | Value |
|------|-------|
| Current package | zxcvbn@4.4.2 (unmaintained, ~9 years since last publish) |
| Recommended replacement | @zxcvbn-ts/core@4.1.2 (actively maintained, published 7 days ago) |
| Migration scope | 1 file (`passwordStrength.ts`), 3 new packages, 2 removed packages |
| Urgency | Low (zxcvbn still works; replacement is a maintenance improvement) |
| Action | Schedule for a future maintenance phase; do not block current feature work |
