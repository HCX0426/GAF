# s37 models.ts 拆分 — Verification

执行时间：2026-08-18 19:58 - 20:25（~27min，中修改基线 <60min ✅）

## 验证结果

| 检查项 | 命令 | 结果 |
|--------|------|------|
| 完整性断言 | split 脚本 150/150（109 interface + 36 type + 5 const） | ✅ |
| tsc（s37 状态） | `npx tsc -b --noEmit` | ✅ 0 errors |
| tsc（基线 HEAD 对比） | git checkout 还原 models.ts 后同命令 | ✅ 0 errors（证明 6 组件错误是级联引入，非预存） |
| build | `npm run build`（tsc -b && vite build） | ✅ built in 17.79s |
| lint | `npx eslint src/types/models/` | ✅ 0 errors（仅中文注释 warnings，TD-335 已知） |
| lint 全量 | `npm run lint` | 164 errors 均为未触及文件预存项（s37 未引入） |
| vitest | `npm test` | ✅ 44/45 文件 passed，346/347 tests passed |
| vitest Login 基线对比 | 还原 HEAD 后单跑 Login.test.tsx | 基线同样 4 passed + 1 异步 error → 预存 flaky（antd message.error teardown 后未捕获 rejection），非 s37 引入 |
| 引用方契约 | 97 引用方文件零改动，`@/types/models` 目录解析到 index.ts | ✅ |

## 结论

s37 拆分完成，验证全绿（与基线一致或优于基线）。36 个 tsc 错误全部定位为拆分引入并修复（3 类根因见 solution.md），无遗留。

## 附：修复后复验

- API import 修复后 tsc 0 errors（36 → 0）
- 未改动任何组件/引用方文件，仅 models/ 目录 11 文件 + 删除 models.ts