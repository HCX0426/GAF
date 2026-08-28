---
source: GAF/.ai-memory/lessons/N142-copy-paste-rename-all-identifiers.md
load_when: [文件复制重命名, 拆分组件, copy-paste refactor, default export 引用错误, ReferenceError 整页崩溃]
priority: high
symptom: [kb:lesson:n142, copy-paste-rename, default-export-mismatch, reference-error, main-tsx-load-failure]
solution: 复制源文件作为新组件时，必须更新所有标识符引用：函数名、export default 引用、interface 名、类型别名。仅改 import 路径不够，default export 中引用的旧函数名会变成 ReferenceError 在运行时炸整个入口模块。
related_files:
  - frontend/src/pages/Resources/TemplateAnnotation/LiveAnnotationTab.tsx
  - frontend/src/pages/Resources/TemplateAnnotation/index.tsx
created_by: AI
date: 2026-07-05
generated: 2026-07-05
level: L1
n_id: N142
topic: cross-layer-sync
---

# N142: 复制-粘贴重命名必须更新所有标识符 (含 default export 引用)

> **触发**: R37-P1 C5 把 `frontend TemplateAnnotationTab (在 frontend/src/pages/Resources/TemplateAnnotation/)` 拆成 `LiveAnnotationTab.tsx` + `TemplateAnnotationTab.tsx` + 新 `index.tsx` wrapper
> **时间**: 2026-07-05 | **commit**: `-` (C6 修复)
> **影响**: ALL routes 崩溃 (不只是 /template-annotation)，main.tsx 加载失败，登录页空白

## 1. 问题 (Problem)

C5 拆分 TemplateAnnotationPage 时，把原 `index.tsx` (816 行) 复制为 `LiveAnnotationTab.tsx`：

- ✅ 改了函数声明：`export function TemplateAnnotationPage()` → `export function LiveAnnotationTab()`
- ❌ 没改 default export 引用：`export default TemplateAnnotationPage;` (line 818) 仍引用旧名

```ts
// LiveAnnotationTab.tsx (复制后)
export function LiveAnnotationTab() { ... }  // line 67 — 改了
// ...
export default TemplateAnnotationPage;       // line 818 — 没改！
```

## 2. 症状 (Symptom)

- `tsc --noEmit` 通过 0 errors (TypeScript 不报运行时未定义引用，因为 `TemplateAnnotationPage` 在 module scope 找不到时退化为 any)
- `npm run dev` 启动无报错 (Vite 不预编译)
- 浏览器打开任何页面 → 空白 + Console: `ReferenceError: TemplateAnnotationPage is not defined`
  - Stack: `at LiveAnnotationTab.tsx:1559:16` (transformed line)
- ALL routes 崩溃 (不只是 /template-annotation)：因为 `App.tsx` import `TemplateAnnotationPage` from `@/pages/TemplateAnnotation` → index.tsx import `LiveAnnotationTab` → LiveAnnotationTab.tsx 顶层 ReferenceError → 整个 module 加载失败 → main.tsx 渲染失败 → `<div id="root"></div>` 空白

## 3. 根因 (Root Cause)

1. **复制-粘贴时只改函数声明，没改 default export 引用**：`export default X` 中的 `X` 是引用，不是声明。改了 `function LiveAnnotationTab()` 但没改 `export default TemplateAnnotationPage`，导致 default export 引用未定义的标识符。
2. **tsc 0 errors 给了假信心**：TypeScript 对 `export default <Identifier>` 中的未定义标识符在某些模式下不报错 (被推为 any)。tsc 通过 ≠ 运行时可用。
3. **Vite HMR 错误信息误导**：浏览器最初报错 `index.tsx does not provide an export named 'default'`，但实际是 LiveAnnotationTab.tsx 的 ReferenceError 导致 index.tsx module 加载失败，default export 没注册。stack trace 才是真因。

## 4. 修复 (Fix)

```diff
- export default TemplateAnnotationPage;
+ export default LiveAnnotationTab;
```

## 5. 验证 (Verification)

- 修复前：浏览器空白，console `[pageerror] ReferenceError: TemplateAnnotationPage is not defined at LiveAnnotationTab.tsx:1559`
- 修复后：Playwright 全 4 页 (/tasks + /resources + /devices + /template-annotation) 0 console errors，Tab 2 渲染 3 个 ant-select

## 6. 教训 (Lesson)

**复制源文件作为新组件时，必须更新所有标识符引用**：
- ✅ 函数声明：`function X()` → `function Y()`
- ✅ Default export 引用：`export default X` → `export default Y`
- ✅ Interface 名：`interface XProps` → `interface YProps` (如适用)
- ✅ 类型别名：`type X = ...` → `type Y = ...` (如适用)
- ✅ 注释中提及旧名 (可选但建议)

**验证清单**：
1. `tsc --noEmit` 通过 ≠ 运行时可用 (TypeScript 不抓运行时 ReferenceError)
2. 改完文件后必跑 Playwright 烟测 (登录页能渲染 = main.tsx 加载成功)
3. 改 default export 时 grep 同名引用：`grep -n "TemplateAnnotationPage" LiveAnnotationTab.tsx` 应该 0 结果 (除了 i18n key)

## 7. 分级分发 (L1 可复用经验 — v8.5 修订)

> **级别判定**: N142 有 Y/N 检查清单价值 (复制后 grep 旧名 + Playwright 烟测), 但不是 AI 全局硬约束 → **L1 (3 层)**
> **修订历史**: 初版误判为 L2 (5 层), v8.5 修订降级为 L1, 移除 ③ spec/tasks + ⑤ project_rules 索引行

| 层 | 路径 | 内容 | L1 |
|:--:|------|------|:--:|
| ① lessons | `.ai-memory/lessons/N142-copy-paste-rename-all-identifiers.md` (本文件) | 完整教训 | ✅ |
| ② architecture-mistakes | `.ai-memory/summaries/architecture-mistakes.md` | 摘要：复制-粘贴重命名必须更新所有标识符 | ✅ |
| ③ spec/tasks | — (L1 不进 spec/tasks) | — | — |
| ④ yn-matrices | `.ai-memory/meta/yn-matrices.md` §6 ㉖ | Y/N 矩阵: 复制后 grep 旧名 + Playwright 烟测 | ✅ |
| ⑤ project_rules | — (L1 不进 §6.4 索引表) | — | — |
