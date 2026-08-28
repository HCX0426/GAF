# s37 models.ts 拆分 — Problem

## 问题

- `frontend/src/types/models.ts` 1926 行（150 声明：109 interface + 36 type + 5 const），TD-365 大文件清单第 4 项。
- 单文件承载 10 个域（auth/task/common/llm/recovery/debug/schedule/device/pipeline/monitor），新增类型需在 1926 行文件中定位，域边界模糊。
- 97 个引用方文件、100 个不同符号依赖该文件。

## 拆分方案（spec 2026-08-18-s37-models-ts-split）

- `models.ts` → `models/` 目录：10 个域文件 + `index.ts` barrel（`export * from './<域>'`）。
- `@/types/models` 目录解析自动落到 index.ts，**97 引用方零改动**。
- 24 处跨域引用生成 `import type`（2 循环：task.ScheduledTask ↔ schedule.TaskEditorMode，TS type 循环安全）。

## 验证标准

- `npx tsc -b --noEmit` 0 errors（与基线 HEAD 一致，基线 0 errors）
- `npm run build` 通过
- `npm run lint` models/ 0 errors（164 errors 均为未触及文件的预存项）
- `npm test` 346 passed + Login.test.tsx 1 个预存异步 error（基线 HEAD 同样 1 error，非 s37 引入）