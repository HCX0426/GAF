---
spec: 2026-08-29-naming-c-default-routine
title: 命名归一化 C-2：GameProfile.default_routine → default_task_chain（含端点，执行上下文）
type: B2 大修改载体 (N151/N167/N173)
date: 2026-08-29
start_ts: 2026-08-29T22:38:00+08:00
end_ts: 2026-08-29T22:52:00+08:00
duration_min: 14
within_baseline: true
root_cause_if_over: n/a
---

# Spec Context — C-2 default_routine → default_task_chain

## N151 架构盘点（5 步）

1. **架构盘点**：`GameProfile.default_routine`(gamestate/models.py:53) 为 `TaskChain` FK，"Routine" 掩盖其本质为默认任务链；端点 `default-routine` URL 命名不一致；跨 gamestate/scheduler/pipeline/agents 4 app + 前端共 26 文件。
2. **识别反模式**：FK 名用 "Routine" 而非 "TaskChain"，与 `TaskChain` 模型语义割裂；端点 URL 含 `default-routine`。
3. **A/B/C 备选**：A=仅文档(拒绝)；B=字段+端点改名 `default_task_chain`/`default-task-chain`(采用)；C=保留 `routine` 别名兼容(拒绝：双名漂移)。
4. **七维评分**：见下；总分领先且 ≥19，自决推进。
5. **拒绝双套 / 最小化**：单一 `default_task_chain`；`routine_path`/`dispatch-routine`/`is_default`/`TaskChain` 保持不动。i18n 键 `col_default_routine`→`col_default_task_chain` 同步，避免残留符号。

## N167 七维评估（大修改）

| 维度 | 评分 | 说明 |
|------|------|------|
| 1 架构长远性 | 5 | 字段名与 TaskChain 模型语义一致 |
| 2 全局归一化 | 5 | 后端 4 app + 端点 URL + 前端类型 + i18n 键全栈统一 |
| 3 扩展性 | 4 | FK 语义清晰，下游继承默认任务链无歧义 |
| 4 兼容性 | 4 | `RenameField` 迁移保数据；端点 URL 同步改 |
| 5 可观测性 | 4 | 序列化/响应键一致 |
| 6 测试覆盖 | 4 | 模型/序列化/视图/调度测试全量机械改写 |
| 7 长期维护成本 | 5 | 消除 "routine vs task chain" 认知负担 |
| **总分** | **31** | 领先且 ≥19，自决推进 |

## N173 用时测量

- start_ts: 2026-08-29T22:38:00+08:00
- end_ts: 2026-08-29T22:52:00+08:00
- duration_min: 14
- within_baseline: true（estimated 0.5 day；机械双替换+迁移，<15min 中修改基线）
- root_cause_if_over: n/a
