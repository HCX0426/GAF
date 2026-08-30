# problem.md — P5 reflection (naming-g P5: G-8 agent_runtime -> worker_runtime, G-12 AgentSelector -> WorkerSelector)

任务: P5 = 其余后端符号。G-9 AgentViewSet 在 P1 已完成 (crud.py:38 class WorkerViewSet, views re-export 已 Worker, 无残留) — 实做减为 G-8 + G-12 + tasks 选 Worker。

范围边界: 仅模块改名 + 符号;健康检查/心跳逻辑零改动;`agent_runtime` 语义 (TD-217 backend 自启 worker 管理器) 与 C-3 `protocol WorkerSession` 无耦合。

风险: agent_runtime 被多处懒加载 (apps ready 启动、crud.py lazy import、worker/src 注释);tasks 选择器被 dispatch_task 热路径依赖 + 2 个 hook 白名单写死旧测试路径。

验收: tasks+workers 全绿 + backend 切片全绿 + ruff 无新增 + makemigrations --check 干净 + 无跨边界残余。

## 反思 ① 四问
- 做什么? git mv 3 文件 + 17 文件字节级 token 替换 (代码 10 + lessons related_files 3 + 活文档 4)。
- 复用: worker_runtime 内部无 agent_runtime 自引用 (grep 证实);G-9 提前完成,不重做。
- 风险: hook 白名单路径 (check_schema_unification/check_code_rules) 若漏改 → 提交后 hook 崩;懒加载 import 若漏改 → ready() 崩溃。
- 验收: 全达成 (见 verification)。

## 反思 ② A/B/C
- [A] 处理: ruff I001 ×1 (tasks.py 懒加载块 import 排序, --fix)。
- [A] 处理: hook 白名单 2 处旧测试路径改名 (否则提交后 hook 报 FileNotFoundError)。
- [B] 待办(naming-e/P6): 架构文档/注释中的 prose "选 Agent"、"agent 健康探针" 等叙事语仍在 (dispatch-flow:26/141, concurrency-design 描述段) — 属文案 sweep。
- [C] 无。

## 反思 ③ Round
- R1: rename + replace → 255 passed (tasks+workers)。
- R2: 残余 grep → backend/worker/scripts/frontend 全零;ruff 剩 1 条 E402 → HEAD 基线证实预存 (health.py:37, flat 1=1)。
- R3: 全切片 987 passed → commit 323ef94 → 工作树干净。
- 终止: 无新增 A 类。

## 反思 ④ 状态标记
Y — G-8/G-9/G-12 后端符号全 Worker 化;frontend 无 AgentSelector;残余仅 prose 叙事 (P6)。