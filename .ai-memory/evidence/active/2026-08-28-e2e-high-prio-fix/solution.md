---
maintainer: manual
source: GAF/.ai-memory/evidence/active/2026-08-28-e2e-high-prio-fix/
created_by: AI
last_updated: 2026-08-28
---
## Solution（解决步骤）

1. frontend/src/pages/Ops/Monitors/index.tsx: EventsTab 挂载即 loadEvents + SEVERITY_COLOR_MAP 四色 (P0/P1/P2/P3)。
2. frontend/src/components/Layout/HeaderStatusIndicator.tsx: 429 响应静默忽略；30s 轮询带 AbortController。
3. frontend/src/providers/WebSocketProvider.tsx: 重连失败告警去重 + 恢复自动关闭；根因 token 过期非 bug，保留告警。
4. frontend/src/i18n/locales/tasks.ts: 补齐 zh-CN/en-US/ja-JP 缺失 tasks.* key。
5. frontend/src: Spin.tip->description (ConfigWizard/PreviewPanel/DagEditorPage/PipelineEditorPage/PipelineVersionHistory)；Alert.message->title (NodePropertyPanel/NodeDetailDrawer/LogAnalysisPanel/SpecialtyLogTabs)；notification.message->title (WebSocketProvider)；Carousel.dotPosition->dotPlacement (DailySummaryCarousel)；InputNumber.addonAfter->Space.Compact (AccountRotationRules/FeatureFlagsPage)。
6. frontend/src/components/Dashboard/TrendChart.tsx: ResponsiveContainer minWidth/minHeight=1。
7. backend/notifications/serializers.py: NotificationSerializer 增加 content=CharField(source='body')；frontend 渲染 item.content。
8. npm run build 验证 SyntaxError 消除；Mock/ERR_ABORTED 确认非代码问题（测试 mock、无头环境无模拟器）。