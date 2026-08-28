# s37 models.ts 拆分 — Solution

## 产物

`frontend/src/types/models/`（11 文件，150/150 声明完整性断言通过）：

| 文件 | 行数 | 域 |
|------|-----|-----|
| auth.ts | 241 | User/Agent/Task/Login/InitStatus 等 |
| task.ts | 187 | TaskStep/TaskExecution/ExecutionStatus/ResourcePack 等 |
| common.ts | 109 | PaginationParams/GameProfile 等 |
| llm.ts | 121 | LLM 对话类型 |
| recovery.ts | 140 | RecoveryConfig 等 |
| debug.ts | 115 | DebugLog 分析状态 |
| schedule.ts | 315 | TaskEditorMode/ScheduleType 等 |
| device.ts | 357 | Device/GameAccount/DeviceType 等 |
| pipeline.ts | 370 | PipelineNodeType/DAG 编辑器类型 |
| monitor.ts | 218 | MonitorEvent/CellStatus 矩阵类型 |
| index.ts | 16 | barrel 汇总 export |

`frontend/src/types/models.ts` 删除。

## 修复的问题（tsc 第一轮 36 errors）

1. **TS2503 Cannot find namespace 'API'（14 errors，4 文件）**：原 models.ts 第 93 行有 `import type { API } from '@/types/api';`，拆分分析误判"无 import"（声明正则只匹配 type/interface/const），生成文件缺失该 import → `API.components['schemas']['X']` 全部解析失败。修复：auth/common/device/task 4 文件补 `import type { API } from '@/types/api';`。
2. **TS2503 级联（6 errors，4 组件文件）**：DeviceCard/TaskDetailDrawer/GameProfiles-DetailPage/TaskFormModal 的隐式 any（TS7053/TS7006）——`Task`/`Device` 类型因 API 命名空间缺失降级为 any → 组件回调参数变 any。API import 补上后全部消失，**组件文件零改动**。
3. **TS6133 unused imports（16 errors，7 文件）**：跨域 `import type` 自动生成时 refs 正则 `\b名字\b` 匹配到注释文本（如 "migrated to API.components['schemas']['X']"）→ 误判引用生成 import。修复：删除 debug(2)/device(4)/monitor(3)/pipeline(1)/recovery(1)/schedule(3)/task(2) 共 16 个未用 import。

## 根因（沉淀 N202 ⑭⑮⑯）

- ⑭ 拆分脚本必须保留源文件的**顶层 import**（TS/JS 文件 import 声明是契约一部分，不是可丢弃的 header）。
- ⑮ 跨域引用扫描必须**排除注释行**（`//` 与 `/* */`），否则注释里的类型名会产生假引用。
- ⑯ 类型解析失败的级联效应：一个模块 TS2503 → 消费者处隐式 any → 远离拆分的组件文件报错；基线对比（git stash/checkout 还原法）可判定预存 vs 引入。