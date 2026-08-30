# problem.md — P6 reflection (naming-g P6: frontend type regen + copy sweep)

任务: P6 = 前端执行节点语义 Agent→Worker 统一。用户决策(2026-08-30): P6.2 范围=仅前端文案,backend/docs prose 交由命名-d/e。

范围边界: P6.1 仅类型重生成(schema 名驱动),URL /agents/*、basename protocol-session、字段 agent_id 全保留;P6.2 仅 display 字符串/UI 文案/注释,键名(_agent 后缀)、配置键(agent_debug*/auto_restart_agent)、auditLog resource label 保留。AI 域(api/ai.ts/LogAnalysisPanel/ailab.ts/AgentSession)与浏览器 User-Agent(accounts/reportFrontendError)排除。

风险: ① naive Agent→Worker 全串替换会把 fetchAgents/useAgentsQuery/AgentHealthPanel 等标识符改成 Worker* 导致跨文件 import 断裂;② User-Agent 含 'Agent' 子串,粗替换会污染;③ 测试断言如 Dashboard.test getByText('在线 Agent') 需与文案同步改。

## 反思 ① 四问
- 做什么? P6.1 重生成 api.generated.ts + 消费方类型改名;P6.2 词边界文案 sweep。
- 复用: openapi-typescript 7.13 / spectacular 现有 npm pipeline;locale 键名全小写 → 值字符串大写 'Agent' 可整词安全。
- 风险: 见上三风险,解法=词边界正则 (?<![A-Za-z0-9_])Agent(?![A-Za-z0-9_]) 保标识符、User-Agent 文件排除、测试文案同轮改。
- 验收: tsc 无新增 error(基线 11 全预存)、eslint 无新增、vitest 受影响 5 文件绿、键名完好、工作树干净。

## 反思 ② A/B/C
- [A] 处理: P6.1 消费方类型漂移 7 文件一次改齐;P6.2 122 处/30 文件文案 sweep;Dashboard.test/useDeviceStore.test 断言同步。
- [A] 处理: tsc DeviceDetailPanel 2 条已暴露而非引入 — 以 HEAD 基线 9→11 分账并登 TD-422(P1),交命名-c-device-emulator P前端 清。
- [B] 待办: 符号重命名 fetchAgents/useAgentsQuery/AgentHealthPanel/agent_debug 键的安全别名等 — 属命名-e P2 符号 sweep,证据载明边界。
- [C] LiveAnnotationTab.tsx:696 pre-existing no-useless-assignment(HEAD diff 空,非本任务引入)。

## 反思 ③ Round
- R1: generate:api-types 重生成 1027+/1046- + auth.ts 别名 Worker → tsc 11(全预存)。
- R2: 文案 sweep 脚本执行 122 替换/30 文件 → 残余 word-boundary Agent 计数=0(仅标识符内嵌,scan 证实)。
- R3: key 完好抽查(settings.agent_debug_enable 键在、值 Worker)+ vitest 47 passed + eslint 1(非本次)+ tsc 11 → commit 1c25e92(P6.1) / 395c861(P6.2)。
- 终止: 残余为零、治理钩子通过。

## 反思 ④ 状态标记
Y — P6 全绿:类型 WorkerSessionStatusEnum/Worker(无 ProtocolAgentSessionStatusEnum),文案全 Worker;auditLog 'Agent 客户端' 保留=后端 resource 契约未动(命名-d 改后端时同轮换);符号名待命名-e P2。