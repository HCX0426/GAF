/**
 * App entry component — GAF V2
 * 9 route groups: Dashboard, GameProfiles, Tasks, Devices, Resources, Accounts, Ops, AI, System
 *
 * Code-splitting strategy (TD-025):
 * - Eager: auth flow (Login/OAuthCallback/Setup) + app shell (ErrorBoundary/AuthGuard/
 *   AppLayout/WebSocketProvider/i18n/theme) — needed before any route can render.
 * - Lazy: every page-level route is wrapped in <Suspense> via the <Lazy> helper so each
 *   page ships as its own chunk and only loads on navigation.
 */
import { useState, useEffect, lazy, Suspense } from 'react';
import type { ReactNode } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, App as AntApp, Spin } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import enUS from 'antd/locale/en_US';
import jaJP from 'antd/locale/ja_JP';
import koKR from 'antd/locale/ko_KR';
import ErrorBoundary from '@/components/Common/ErrorBoundary';
import PageErrorBoundary from '@/components/Common/PageErrorBoundary';
import AuthGuard from '@/components/Guards/AuthGuard';
import AppLayout from '@/components/Layout/AppLayout';
import { WebSocketProvider } from '@/providers/WebSocketProvider';
import { useLocale, resolveLocale, type RealLocale } from '@/i18n';
// Auth flow pages stay eager — they render before the SPA shell mounts and must not
// wait on a dynamic import (especially on first visit / hard reload to /login).
import LoginPage from '@/pages/Login';
import OAuthCallbackPage from '@/pages/OAuthCallback';
import SetupPage from '@/pages/Setup';
import { getStoredTheme, getAntdThemeConfig, subscribeTheme } from '@/theme';
import type { ThemeMode } from '@/theme';

// --- Lazy page imports (each becomes its own chunk via dynamic import) ---
const DashboardPage = lazy(() => import('@/pages/Dashboard'));
const TaskListPage = lazy(() => import('@/pages/Tasks'));
const TaskEditorPage = lazy(() => import('@/pages/Tasks/Editor').then((m) => ({ default: m.TaskEditorPage })));
const RecordingsPage = lazy(() => import('@/pages/Tasks/TaskStudio/RecordingsPage'));
const PipelineEditorPage = lazy(() =>
  import('@/pages/Tasks/PipelineEditor/PipelineEditorPage').then((m) => ({
    default: m.PipelineEditorPage,
  })),
);
const DevicesPage = lazy(() => import('@/pages/Devices/DeviceCenterPage'));
const EmulatorManagementPage = lazy(() => import('@/pages/Devices/EmulatorManagementPage'));
const WindowManagementPage = lazy(() => import('@/pages/Devices/WindowManagementPage'));
const AdbLogViewerPage = lazy(() => import('@/pages/Devices/AdbLogViewerPage'));
const ResourcesPage = lazy(() => import('@/pages/Resources'));
const MonitorsPage = lazy(() => import('@/pages/Ops/Monitors'));
const ExecutionsPage = lazy(() => import('@/pages/Ops/Executions'));
const ScheduledTasksPage = lazy(() => import('@/pages/Ops/ScheduledTasks'));
const DagEditorPage = lazy(() => import('@/pages/Ops/ScheduledTasks/DagEditorPage'));
const GameAccountsPage = lazy(() => import('@/pages/Accounts'));
const UserManagePage = lazy(() => import('@/pages/Accounts/UserManagePage'));
const NotificationsPage = lazy(() => import('@/pages/System/Notifications'));
const AnalyticsDashboardPage = lazy(() => import('@/pages/Ops/AnalyticsDashboard'));
const SLADashboard = lazy(() => import('@/pages/Ops/SLADashboard'));
const TemplateAnnotationPage = lazy(() => import('@/pages/Resources/TemplateAnnotation'));
const MarketplacePage = lazy(() => import('@/pages/Tasks/Marketplace'));
const PluginsPage = lazy(() => import('@/pages/System/Plugins'));
const ExecutionReplayPage = lazy(() => import('@/pages/Ops/ExecutionReplay'));
const SystemSettingsPage = lazy(() => import('@/pages/System/SystemSettings'));
const ServicesPage = lazy(() => import('@/pages/System/ServicesPage'));
const ConfigManagementPage = lazy(() => import('@/pages/System/ConfigManagementPage'));
const BackupPage = lazy(() => import('@/pages/Ops/Backup'));
const TemplateEffectivenessPage = lazy(() => import('@/pages/Resources/TemplateEffectiveness'));
const UnattendedControlPage = lazy(() => import('@/pages/Ops/UnattendedControlPage'));
/** AI sub-pages — independent routes under /ai/* */
const AiAssistantPanel = lazy(() => import('@/pages/AI/AiAssistantPanel'));
const QAPanel = lazy(() => import('@/pages/AI/QAPanel'));
const LogAnalysisPanel = lazy(() => import('@/pages/AI/LogAnalysisPanel'));
const AIUsageDashboard = lazy(() => import('@/pages/AI/AIUsageDashboard'));
const CustomSkillEditor = lazy(() => import('@/pages/AI/CustomSkillEditor'));
const AnomalyPatternPanel = lazy(() => import('@/pages/AI/AnomalyPatternPanel'));
const AiConfigPage = lazy(() => import('@/pages/AI/AiConfigPage'));
const SkillMarketPage = lazy(() => import('@/pages/AI/SkillMarket'));
// Spec v3 §2.5.1: GameProfile promoted to top-level menu (/game-profiles).
// The list page lives at /pages/GameProfiles/index.tsx (moved from /pages/System).
const GameProfilesPage = lazy(() => import('@/pages/GameProfiles'));
// Spec v3 §2.5.2: GameProfile detail page with 6 tabs.
const GameProfileDetailPage = lazy(() => import('@/pages/GameProfiles/DetailPage'));
const ApiKeysPage = lazy(() => import('@/pages/System/ApiKeysPage'));
const FeatureFlagsPage = lazy(() => import('@/pages/System/FeatureFlagsPage'));
const AuditLogPage = lazy(() => import('@/pages/System/AuditLogPage'));
const LogCenterPage = lazy(() => import('@/pages/Ops/Logs/LogCenterPage'));

/** Mapping from real GAF locale to Ant Design locale bundle. */
const antdLocaleMap: Record<RealLocale, typeof zhCN> = {
  'zh-CN': zhCN,
  'en-US': enUS,
  'ja-JP': jaJP,
  'ko-KR': koKR,
};

/** Full-height centered spinner shown while a lazy page chunk loads. */
function PageFallback() {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '40vh',
        width: '100%',
      }}
      aria-busy="true"
      aria-live="polite"
    >
      <Spin size="large" />
    </div>
  );
}

/** Wrap a lazy page element in a Suspense boundary (chunk loading) AND a
 *  PageErrorBoundary (chunk fetch failure / render throw) so a single page's
 *  failure is contained and does not blank the whole app. PageErrorBoundary
 *  differentiates chunk-load failures from render errors and offers
 *  page-local retry + go-home recovery without touching sibling routes. */
function Lazy({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<PageFallback />}>
      <PageErrorBoundary>{children}</PageErrorBoundary>
    </Suspense>
  );
}

/** app root component, wrapped with AntApp to provide global message/notification/modal context */
export default function App() {
  const [themeMode, setThemeMode] = useState<ThemeMode>(getStoredTheme);
  const locale = useLocale();

  useEffect(() => {
    return subscribeTheme((mode) => {
      setThemeMode(mode);
    });
  }, []);

  const themeConfig = getAntdThemeConfig(themeMode);
  const antdLocale = antdLocaleMap[resolveLocale(locale)];

  return (
    <ConfigProvider locale={antdLocale} theme={themeConfig}>
      <AntApp message={{ duration: 5, maxCount: 3 }} notification={{ top: 80, duration: 4.5 }}>
        <ErrorBoundary>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/auth/callback" element={<OAuthCallbackPage />} />
              <Route path="/setup" element={<SetupPage />} />
              <Route
                path="/"
                element={
                  <AuthGuard>
                    <WebSocketProvider>
                      <AppLayout />
                    </WebSocketProvider>
                  </AuthGuard>
                }
              >
                <Route index element={<Navigate to="/dashboard" replace />} />

                {/* 工作台 */}
                <Route
                  path="dashboard"
                  element={
                    <Lazy>
                      <DashboardPage />
                    </Lazy>
                  }
                />

                {/* 游戏档案 — Spec v3 §2.5: top-level menu */}
                <Route
                  path="game-profiles"
                  element={
                    <Lazy>
                      <GameProfilesPage />
                    </Lazy>
                  }
                />
                <Route
                  path="game-profiles/:id"
                  element={
                    <Lazy>
                      <GameProfileDetailPage />
                    </Lazy>
                  }
                />

                {/* 任务 */}
                <Route
                  path="tasks"
                  element={
                    <Lazy>
                      <TaskListPage />
                    </Lazy>
                  }
                />
                <Route
                  path="tasks/:taskId/edit"
                  element={
                    <Lazy>
                      <TaskEditorPage />
                    </Lazy>
                  }
                />
                <Route
                  path="tasks/pipeline"
                  element={
                    <Lazy>
                      <PipelineEditorPage />
                    </Lazy>
                  }
                />
                <Route
                  path="tasks/pipeline/:id"
                  element={
                    <Lazy>
                      <PipelineEditorPage />
                    </Lazy>
                  }
                />
                <Route
                  path="tasks/recordings"
                  element={
                    <Lazy>
                      <RecordingsPage />
                    </Lazy>
                  }
                />
                <Route
                  path="tasks/marketplace"
                  element={
                    <Lazy>
                      <MarketplacePage />
                    </Lazy>
                  }
                />

                {/* 设备 */}
                <Route
                  path="devices"
                  element={
                    <Lazy>
                      <DevicesPage />
                    </Lazy>
                  }
                />
                <Route
                  path="devices/emulators"
                  element={
                    <Lazy>
                      <EmulatorManagementPage />
                    </Lazy>
                  }
                />
                <Route
                  path="devices/windows"
                  element={
                    <Lazy>
                      <WindowManagementPage />
                    </Lazy>
                  }
                />
                <Route
                  path="devices/adb-logs"
                  element={
                    <Lazy>
                      <AdbLogViewerPage />
                    </Lazy>
                  }
                />
                <Route
                  path="devices/adb-logs/:deviceId"
                  element={
                    <Lazy>
                      <AdbLogViewerPage />
                    </Lazy>
                  }
                />

                {/* 资源 */}
                <Route
                  path="resources"
                  element={
                    <Lazy>
                      <ResourcesPage />
                    </Lazy>
                  }
                />
                <Route
                  path="resources/template-effectiveness"
                  element={
                    <Lazy>
                      <TemplateEffectivenessPage />
                    </Lazy>
                  }
                />
                <Route
                  path="resources/annotation"
                  element={
                    <Lazy>
                      <TemplateAnnotationPage />
                    </Lazy>
                  }
                />

                {/* 账户 */}
                <Route
                  path="accounts/users"
                  element={
                    <Lazy>
                      <UserManagePage />
                    </Lazy>
                  }
                />
                <Route
                  path="accounts/game-accounts"
                  element={
                    <Lazy>
                      <GameAccountsPage />
                    </Lazy>
                  }
                />

                {/* 运维 */}
                <Route
                  path="ops/executions"
                  element={
                    <Lazy>
                      <ExecutionsPage />
                    </Lazy>
                  }
                />
                <Route
                  path="ops/executions/:executionId/replay"
                  element={
                    <Lazy>
                      <ExecutionReplayPage />
                    </Lazy>
                  }
                />
                <Route
                  path="ops/scheduler"
                  element={
                    <Lazy>
                      <ScheduledTasksPage />
                    </Lazy>
                  }
                />
                <Route
                  path="ops/scheduler/dag"
                  element={
                    <Lazy>
                      <DagEditorPage />
                    </Lazy>
                  }
                />
                <Route
                  path="ops/scheduler/dag/:chainId"
                  element={
                    <Lazy>
                      <DagEditorPage />
                    </Lazy>
                  }
                />
                <Route
                  path="ops/monitors"
                  element={
                    <Lazy>
                      <MonitorsPage />
                    </Lazy>
                  }
                />
                <Route
                  path="ops/analytics"
                  element={
                    <Lazy>
                      <AnalyticsDashboardPage />
                    </Lazy>
                  }
                />
                <Route
                  path="ops/sla"
                  element={
                    <Lazy>
                      <SLADashboard />
                    </Lazy>
                  }
                />
                {/* Normalized: log viewing in /ops/logs (8 tabs incl. archive); LLM analysis in /ai/log-analysis */}
                <Route
                  path="ops/logs"
                  element={
                    <Lazy>
                      <LogCenterPage />
                    </Lazy>
                  }
                />
                <Route
                  path="ops/unattended"
                  element={
                    <Lazy>
                      <UnattendedControlPage />
                    </Lazy>
                  }
                />

                {/* AI — 8 independent sub-pages (config + usage moved here from /system/*) */}
                <Route
                  path="ai/assistant"
                  element={
                    <Lazy>
                      <AiAssistantPanel />
                    </Lazy>
                  }
                />
                <Route
                  path="ai/qa"
                  element={
                    <Lazy>
                      <QAPanel />
                    </Lazy>
                  }
                />
                <Route
                  path="ai/anomaly"
                  element={
                    <Lazy>
                      <AnomalyPatternPanel />
                    </Lazy>
                  }
                />
                <Route
                  path="ai/skill-editor"
                  element={
                    <Lazy>
                      <CustomSkillEditor />
                    </Lazy>
                  }
                />
                <Route
                  path="ai/skill-market"
                  element={
                    <Lazy>
                      <SkillMarketPage />
                    </Lazy>
                  }
                />
                <Route
                  path="ai/log-analysis"
                  element={
                    <Lazy>
                      <LogAnalysisPanel />
                    </Lazy>
                  }
                />
                <Route
                  path="ai/config"
                  element={
                    <Lazy>
                      <AiConfigPage />
                    </Lazy>
                  }
                />
                <Route
                  path="ai/usage"
                  element={
                    <Lazy>
                      <AIUsageDashboard />
                    </Lazy>
                  }
                />

                {/* 系统 */}
                <Route
                  path="system/settings"
                  element={
                    <Lazy>
                      <SystemSettingsPage />
                    </Lazy>
                  }
                />
                {/* spec 2026-08-29-services-management-monitor: 服务管理页 */}
                <Route
                  path="system/services"
                  element={
                    <Lazy>
                      <ServicesPage />
                    </Lazy>
                  }
                />
                <Route
                  path="system/config"
                  element={
                    <Lazy>
                      <ConfigManagementPage />
                    </Lazy>
                  }
                />
                <Route
                  path="system/notifications"
                  element={
                    <Lazy>
                      <NotificationsPage />
                    </Lazy>
                  }
                />
                <Route
                  path="system/plugins"
                  element={
                    <Lazy>
                      <PluginsPage />
                    </Lazy>
                  }
                />
                <Route
                  path="system/backup"
                  element={
                    <Lazy>
                      <BackupPage />
                    </Lazy>
                  }
                />
                <Route
                  path="system/api-keys"
                  element={
                    <Lazy>
                      <ApiKeysPage />
                    </Lazy>
                  }
                />
                <Route
                  path="system/feature-flags"
                  element={
                    <Lazy>
                      <FeatureFlagsPage />
                    </Lazy>
                  }
                />
                <Route
                  path="system/audit-log"
                  element={
                    <Lazy>
                      <AuditLogPage />
                    </Lazy>
                  }
                />
              </Route>
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </BrowserRouter>
        </ErrorBoundary>
      </AntApp>
    </ConfigProvider>
  );
}
