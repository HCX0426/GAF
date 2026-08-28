# s37 — Split `frontend/src/types/models.ts` (1926 lines) into domain modules (TD-365)

> ✅ 已归档: `docs/specs/archived/2026-08/2026-08-18-s37-models-ts-split.md`
> TD-365 大文件治理 batch 4。s34/s35/s36 已闭环。TS 类型文件拆分——目录 + barrel re-export 模式（与 Python mixin 不同）。

## 状态表

| Phase | 状态 | 完成时间 | commit | 验收 evidence |
|-------|------|---------|--------|--------------|
| P1 结构分析 + spec | ✅ | 2026-08-18 | `-` | 10 域分组表（150 声明全映射） |
| P2 拆分实现 | ✅ | 2026-08-18 | `-` | 150/150 完整性断言 + 11 文件生成 |
| P3 验证 + commit | ✅ | 2026-08-18 | `-` | tsc 0 errors / build ✅ / lint 0 new / vitest 346 passed |
| P4 归档 + TD-365 更新 | ✅ | 2026-08-18 | 见归档 commit | spec 归档 + TD-365 4/9 + N202 ⑭⑮⑯ |

## 背景

- `frontend/src/types/models.ts` 1926 行，150 个声明（109 interface + 36 type + 5 const），纯类型文件无 import（仅 header 注释 L1-92）。
- 97 个引用文件、100 个符号被 import（路径 `@/types/models` 或相对 `../types/models`）。
- **核心策略**：`models.ts` → `models/` 目录（10 个子文件 + `index.ts` barrel `export * from`）→ **引用路径不变**（目录解析自动找 index.ts），97 个引用方零改动。
- 24 处跨域类型引用 → 子文件间 `import type`（含 2 处循环：task.ScheduledTask ↔ schedule.TaskEditorMode——TS 类型擦除后循环安全）。

## P1 结构分析结论

10 域分组（按行号域 + 功能内聚）：

| 子文件 | 声明数 | 行数域 | 内容 |
|--------|-------|--------|------|
| auth.ts | ~24 | L93-198 + L1446-1538 | User/Login/InitStatus/Agent + TOTP/2FA/UserSession/AccountGroup/RotationRule/BulkAction |
| task.ts | ~13 | L197-355 | Task/ExecutionStatus/StepStatus/TaskStep/TaskExecution/ResourcePack/Monitor*/Skill/CustomTask/ScheduledTask |
| common.ts | ~9 | L356-443 | Pagination*/ApiResponse/DashboardStats/WsMessage/ScreenshotResponse/DeviceCommand/GameProfile/TemplateAnnotation |
| llm.ts | ~9 | L444-546 | LlmConfig/ModelEvaluation* |
| recovery.ts | ~12 | L547-659 | Recovery*/NightMode/FrequencyLimit/NotificationPolicy/Cooldown/UnattendedStrategy/AppSettings/SetupRequest |
| debug.ts | ~8 | L660-752 | AnalysisStatus/DebugLog*/ReviewStatus/LLMAnalysisResult/DebugSuggestion/QASession |
| schedule.ts | ~30 | L753-806 + L1539-1744 | TaskStepConfigLegacy/TaskEditorMode/ScheduleType/Notification/Plugin + TaskFolder/TimeWindow/Warmup*/ExecutionPlan*/TodaySchedule*/ConcurrencySchedule/UnattendedSession/PreflightCheck |
| device.ts | ~29 | L807-1103 | AIMessage*/LoginMethod/GameAccount*/Device*/ControlMode/Resolution/AgentInfo/Scan*/ScreenshotTestResult/LockResponse/CompatibilityCheck/DeviceQueryParams |
| pipeline.ts | ~13 | L1104-1445 | PipelineNodeType/GafNode*/NodeCategory/CATEGORY_COLORS/NODE_TYPE_CATEGORY/DEFAULT_NODE_CONFIGS/ICON_KEYS/NODE_TYPE_LIBRARY/Pipeline* |
| monitor.ts | ~17 | L1745-1926 | CellStatus/Matrix*/QueueItem*/ProgressData/ApiKey/FeatureFlag/AuditLog/LogEntry/TaskChain*/Dag* |

跨域引用（24 处）自动生成 `import type`：debug→{auth,schedule} / device→{common,task,auth,pipeline} / monitor→{auth,common,pipeline} / pipeline→device / recovery→auth / schedule→{common,device,task} / task→{schedule,common,auth}。

## P2 拆分实现

- 脚本 `.trash/s37_split_models.py`：
  - AST/正则定位 150 声明边界（上一 decl end+1 → 当前 decl end，保留中间注释）
  - 按域聚合行块 → 子文件；首 decl 不携带 header 注释（L1-92 移入 index.ts 精简版）
  - 跨域引用自动生成 `import type { X } from './<group>'`（去重 + 同域引用不需要）
  - `index.ts`：`export * from './auth'` × 10 + header 注释
  - 5 个 const 依赖在 pipeline 域内（+ICON_KEYS→device）已含
- 文件布局：`frontend/src/types/models/` 目录 + 删除 `models.ts`

## P3 验证

1. `npx tsc --noEmit`（TS 类型检查，基线先跑确认当前 0 错误）
2. `npm run build`（vite build + eslint？确认 scripts）
3. 前端 vitest（若有类型相关测试）
4. 引用方抽查：grep 3 个高频 import 文件确认类型可用（tsc 已覆盖）

## P4 归档

- spec → archived/ + hash 回填；TD-365 更新 4/9；spec-context + N173 + evidence 三件套 + B2 + session

## 验收标准

- [x] models.ts 删除，models/ 目录 11 文件（10 域 + index.ts）
- [x] tsc --noEmit 0 错误（与拆分前一致）
- [x] 97 引用方零改动
- [x] 150 声明完整性（脚本断言）
- [x] index.ts barrel 全覆盖

## Deviation Log

| # | 偏离 | 原因 | 处理 |
|---|------|------|------|
| D1 | API import 未保留 | 拆分分析误判 models.ts "无 import"（声明正则只匹配 type/interface/const，漏 L93 `import type { API }`）→ 14 TS2503 | auth/common/device/task 4 文件补 API import |
| D2 | 假跨域 import 16 个 | refs 正则 `\b名字\b` 匹配注释文本（"migrated to API.components['schemas']['X']"）→ TS6133 | 7 文件删 16 个未用 import |
| D3 | 6 组件级联报错 | TS2503 使 Task/Device 降级 any → DeviceCard/TaskDetailDrawer/DetailPage/TaskFormModal 隐式 any（TS7053/TS7006） | 基线对比证明为级联，API import 修复后消失，组件零改动 |

## 实现产物清单

- 主 commit: `-`（24 files, +2400/-1940）
- 拆分脚本: `.trash/s37_split_models.py`（可复用，未入库）
- N202 lesson: `.ai-memory/lessons/N202-large-file-split-patch-point-contract.md` ⑭⑮⑯ 新增 TS 拆分条目
- spec-context: `docs/archive/spec-context/2026-08-18-s37-models-ts-split-context.md`
- evidence 三件套: `.ai-memory/evidence/active/2026-08-18-s37-models-ts-split/`
- 归档位置: `docs/specs/archived/2026-08/2026-08-18-s37-models-ts-split.md`