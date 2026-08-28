# s37 — models.ts Split (2026-08-18) — spec-context 承载体

> B2 大修改承载体 (TD-342)。对应 spec: `docs/specs/archived/2026-08/2026-08-18-s37-models-ts-split.md`。

## N173 用时字段

- start_ts: 2026-08-18T19:58:00+08:00
- end_ts: 2026-08-18T20:25:00+08:00
- duration_min: 27
- within_baseline: true (中修改基线 15min, 实际 27min —— 因 tsc 36 errors 两轮修复 + 基线对比实验, 见 root_cause)
- root_cause_if_over: 未超中修改 60min 上限但超 15min 基线: (a) 拆分分析误判"无 import"漏 API import → 14 TS2503; (b) refs 正则匹配注释 → 16 TS6133; (c) 6 组件级联报错需基线对比实验判定。若拆分脚本先做 import 保留 + 注释过滤, 可省 ~12min

## 1. 用户决策原文

- 2026-08-18 循环模式（"继续" 强触发延续 + "压缩后继续"）：TD-365 大文件治理按 backend → agent → frontend → scripts 顺序接修，s37 = `frontend/src/types/models.ts`（1926 行，TD-365 剩余 6 个中的 frontend 层第一个）。
- 方法论继承：s36（device.py 拆分）成功模式 + N202 lesson 13 项检查清单。

## 2. N151 5 步法评估

1. **架构盘点**：models.ts 150 声明（109 interface + 36 type + 5 const），10 个域（auth/task/common/llm/recovery/debug/schedule/device/pipeline/monitor）；无 import（唯一 import 为 `import type { API } from '@/types/api'` L93）；97 引用方文件 / 100 符号；24 跨域引用（2 循环：task.ScheduledTask ↔ schedule.TaskEditorMode，TS type 循环安全）。
2. **识别反模式**：单文件 1926 行（TD-365 阈值 2000）——域边界模糊，新增类型难定位。
3. **A/B/C 备选**：
   - A) models/ 目录 + index.ts barrel（10 域文件）—— 引用方零改动，域内聚，TS 目录解析天然支持
   - B) 按域拆成 3-4 个大文件 —— 文件仍大，域边界粗
   - C) 保持现状登记延后 —— 违反循环模式接修指令
4. **拒绝反模式**：C 拒绝（任务明确）；B 拒绝（单文件仍 >500 行，且 barrel 是 TS 标准模式，A 零成本）。
5. **AI 自决**：选 A（总分 57/63，见 §3）。

## 3. N167 七维度评分

| 维度 | A 目录+barrel | B 3-4 大文件 | C 保持 |
|------|-----------|-----------|--------|
| 1 架构长远性 | 10 | 6 | 3 |
| 2 全局归一化 | 9 | 7 | 4 |
| 3 新旧兼容 | 9 | 9 | 10 |
| 4 现有业务完善 | 9 | 9 | 6 |
| 5 性能资源优化 | 8 | 8 | 5 |
| 6 安全合规加固 | 6 | 6 | 5 |
| 7 长期维护成本 | 6 | 6 | 5 |
| 合计 | **57** | 51 | 38 |

A ≥ 19 且领先 ≥ 5 → AI 自决 ✓

## 4. 关键实施决策

| # | 决策 | 背景 | 处理 |
|---|------|------|------|
| D1 | API import 保留 | 拆分分析误判 models.ts "无 import"（声明正则只匹配 type/interface/const），漏 `import type { API } from '@/types/api'`（原 L93）→ 14 TS2503 | auth/common/device/task 4 文件补 API import |
| D2 | 注释过滤 | refs 正则 `\b名字\b` 匹配注释文本（如 "migrated to API.components['schemas']['X']"）→ 16 个假跨域 import（TS6133） | 7 文件删 16 个未用 import |
| D3 | 级联错误判定 | TS2503 使 Task/Device 降级 any → 4 组件文件（DeviceCard/TaskDetailDrawer/DetailPage/TaskFormModal）6 个隐式 any 报错 | 基线对比（git checkout 还原 models.ts）证明预存 0 errors + 修复后 0 errors → 组件零改动 |

## 5. 验证 evidence

- `npx tsc -b --noEmit` = **0 errors**（基线 HEAD 同 0 errors）
- `npm run build` = ✅ built in 17.79s
- `npx eslint src/types/models/` = 0 errors（仅中文注释 warnings，TD-335 已知）
- `npm test` = 44/45 文件 passed / 346/347 tests passed；Login.test.tsx 1 个异步 error 经基线对比为**预存 flaky**（antd message.error teardown 后未捕获 rejection），非 s37 引入
- evidence 三件套: `.ai-memory/evidence/active/2026-08-18-s37-models-ts-split/`

## 6. N193 反思（任务归属）

- D1/D2 根因（import 保留 + 注释过滤）当场修复，无遗留。
- D3 根因（类型级联错误判定）沉淀 N202：拆分后必须跑基线对比区分预存 vs 引入。
- N202 更新项（⑭⑮⑯）：⑭ 拆分脚本保留源文件顶层 import；⑮ 跨域引用扫描排除注释行；⑯ TS 类型解析失败级联效应 + 基线对比法。
- 预存 flaky（Login.test.tsx 异步 error）登记：本任务只验证非引入，修复属另一任务（antd message 测试环境清理），登记 TD-365 备注避免遗漏。