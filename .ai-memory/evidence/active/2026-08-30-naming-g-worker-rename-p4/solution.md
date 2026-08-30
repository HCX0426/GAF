# solution.md — P4 执行与 Y/N 检查 (commit 8ff7889)

## 变更
- protocol.AgentSession → WorkerSession (models.py / serializers WorkerSessionSerializer+List / views WorkerSessionViewSet / admin / services / consumers / quota 注释 / urls basename 'protocol-session' 保留; db_table protocol_agentsession → protocol_workersession)
- 迁移 protocol.0004_rename_agentsession_to_workersession = RenameModel + AlterModelTable (from-scratch 安全: 无跨 app 后置依赖)
- AgentConsumer → WorkerConsumer (consumers.py class + routing.as_asgi + 16 protocol 测试 + monitors/views.py + workers/agent_runtime.py 注释 + api-contract.md L285 + docs/reference/data-flow.md 符号)
- settings AGENT_2_ENUM: ProtocolAgentSessionStatusEnum → WorkerSessionStatusEnum, 指向 protocol.models.WorkerSession.Status
- gaf_ai AgentSession 保留 + OQ-10 docstring 注明 AI 归属 (C-3 P3)
- naming-c-agentsession-context.md 补建 (N151/N167/N173)

## N167 评分 (refactor 权重: 重点 1,7; 标准 2,4; 豁免 3,5,6)
A (改名) = 1:9 / 2:9 / 3:8 / 4:7 / 5:5 / 6:8 / 7:8 = 54; B (仅文档拆分保留) = 37; A 领先 17 ≥5, self-approved。反向论证: B 保留双 AgentSession 碰撞 (dim2 归一失败, 3 年后仍需迁移且二次成本更高), 且 settings 枚举歧义长期留存; dim7 B 无模型收口, 文档漂移风险持续。

## Y/N (select 清单 N166/N167/N117/N124/N112/N128)
- N167: 7 维评分已填 (上)。dim4 不全满: 前端类型/文案 P6 未做, 记录。
- N112 跨层: 帧契约/URL/FK field 保留, 仅 schema 名漂移 (P6 收口), slice 772 passed — Y。
- N128 诚实状态: 无新功能声称, 全部实测 — Y。
- N117/N124: 不适用 — Y/N/A。
- N166: 无新增 L3-A; 残留项均已归 P6/P8/F-5。

## 遗留 (明确归属)
- frontend api.generated.ts ProtocolAgentSessionStatusEnum + 旧 AgentSession(protocol) 类型 → naming-g P6 重生成
- consumers.py → worker_consumers.py → naming-f F-5
- data-flow/architecture docs prose 的 Worker 语义 → naming-d/P8 sweeps