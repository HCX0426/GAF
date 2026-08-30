# problem.md — P4 reflection (protocol AgentConsumer -> WorkerConsumer, WS AgentSession -> WorkerSession)

任务: naming-g P4 (G-6/G-14) + naming-c C-3 P1/P3 — protocol WS 消费者与 WS 会话模型改名。

范围边界: 类符号 + 模型/迁移 + 同一批序列化器/视图/admin/services/quota/routing;不碰 on-wire 帧名 (agent.register/heartbeat 为契约)、URL 路径、前端类型 (P6)。consumers.py 文件改名归 naming-f F-5。

风险: 双 AgentSession 模型不同语义 (protocol WS 会话 vs gaf_ai AI 会话) — 必须只改 protocol 域;从零测试库的 late RenameModel 顺序 (P1 教训)。

验收: protocol 284 passed + 切片 772 passed + makemigrations --check 干净 + migrate --plan 无环 + ruff 无新增 + 治理全过。

## 反思 ① 四问
- 做什么? protocol.AgentSession→WorkerSession (模型+迁移+全部引用) + AgentConsumer→WorkerConsumer。
- 复用: gaf_ai AgentSession 原样保留 (AI 域);帧名/URL/audit resource agent_session(FK 字段名)保留。
- 风险: 前端 OpenAPI 类型短期漂移 (P6 重生成);避免二次迁移 → 与 C-3 同改。
- 验收: 见上 (全部达成)。

## 反思 ② A/B/C
- [A] 修复: 脚本误改 migrations 0001/0002 (parts[-3] 判定错误) → git checkout 还原,冻结历史未受损。
- [A] 处理: ruff 7 条 I001 (rename 引发 import 排序) → --fix 归零。
- [B] 待办: 前端 api.generated.ts ProtocolAgentSessionStatusEnum 残留 + WorkerSession 类型 → naming-g P6 重生成 (登记)。
- [C] 无。

## 反思 ③ Round
- R1: 全链改名 + 迁移 → protocol 284 passed;切片 772 passed。
- R2: 检查 ProtocolAgentSessionStatusEnum 残留 → 仅前端生成文件 (P6)。
- R3: commit 遇 C-3 carrier 缺失 → 补建 naming-c-agentsession-context.md → commit 通过。
- 终止: 无新增 A 类。

## 反思 ④ 状态标记
Y — protocol 域 WorkerSession/WorkerConsumer 全绿;gaf_ai AgentSession 保留 (AI 域);前端类型 P6。