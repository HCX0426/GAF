# solution.md — P6 solution walkthrough (naming-g P6: frontend type regen + copy sweep)

## P6.1 类型重生成
- `npm run generate:api-types`(frontend/,repo-root node_modules,spectacular+openapi-typescript 7.13,可离线)→ `src/types/api.generated.ts` 1027+/1046-:ProtocolAgentSessionStatusEnum 移除,新增 Worker/WorkerRequest/WorkerSession(+List/Request)/WorkerSessionStatusEnum/WorkerToken{Create,List,Response};AgentHeartbeatStatusEnum 保留(后端该枚举未改名)。
- `types/models/auth.ts`: `export type Agent = API.components['schemas']['Worker']`。消费方类型级改名:api/agents.ts(fetchAgents/fetchAgent/generateAgentToken/deleteAgent 签名用 Worker,URL /agents/ 不变)、hooks/useAgentsQuery.ts、stores/useDeviceStore.ts(`agents: Worker[]`)、useDeviceStore.test.ts、pages/Dashboard/AgentHealthPanel.tsx(`keyof Worker`);api/ai.ts AgentSession 不动。

## P6.2 文案 sweep(仅前端,用户范围)
- 手法: 词边界正则 `(?<![A-Za-z0-9_])Agent(?![A-Za-z0-9_])` → 'Worker',字节级 utf-8 读写。
- 排除 8 文件:api.generated.ts(后端 docstring 派生,等命名-d prose 后重生成)、api/ai.ts+LogAnalysisPanel.tsx+ailab.ts+ai.test.ts(AI 域)、auditLog.ts(后端 resource='agent' 契约 label)、accounts.ts+reportFrontendError.ts('User-Agent' 浏览器 UA)。
- 覆盖 122 处/30 文件: i18n locale zh/en/ja/ko(settings 17/devices 16/dashboard 11/analytics 8/sla 7/logCenter 4/monitors 4/taskStudio 4/deviceCenter 4/executions 3)、组件/页面 UI 文案+注释(UnattendedStrategyPanel×2/UnattendedStrategySettings×3/SystemSettings×2/DeviceDetailPanel×2/Dashboard index×2+test×2/AnalyticsDashboard×4/SLADashboard×1/Executions×1/PipelineEditorPage×1/DeviceCenterPage×0+DeviceOperationPanel 无关)、docstring/api 注释(api/agents×1/api/ops×1/api/settings×2/api-paths.test×1/ws-events×5/useDeviceStore×2+test×1/models auth×3/device×1)。
- 关键保护: locale 键名与配置键(settings.agent_debug_*,auto_restart_agent)全小写不受词边界影响;标识符 fetchAgents/useAgentsQuery/AgentHealthPanel/fetchAgentDebug 保留为符号(命名-e P2 处理)。

## 未做(明确延后)
- 符号重命名: fetchAgents/useAgentsQuery/AgentHealthPanel/useDeviceStore.agents/agent_debug 配置键 → 命名-e P2(证据.md 载明边界)。
- backend/docs prose: auditLog resource label、后端 docstring、架构文档叙事 → 命名-d/e。