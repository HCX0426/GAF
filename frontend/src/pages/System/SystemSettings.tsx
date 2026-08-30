/**
 * System Settings page
 * Tabs: data cleanup, config import/export, diagnostic pack, language, debug, etc.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Tabs,
  Card,
  InputNumber,
  Slider,
  Button,
  Popconfirm,
  Upload,
  Spin,
  Typography,
  App,
  Select,
  Switch,
  Divider,
  Tag,
  Alert,
  Space,
  Input,
} from 'antd';
import {
  DownloadOutlined,
  UploadOutlined,
  SettingOutlined,
  CloudServerOutlined,
  BugOutlined,
  CameraOutlined,
  FileTextOutlined,
  SafetyCertificateOutlined,
  DesktopOutlined,
  AppstoreOutlined,
} from '@ant-design/icons';
import type { UploadFile } from 'antd';
import LanguageSwitcher from '@/i18n/LanguageSwitcher';
import {
  fetchTaskStats,
  cleanupData,
  generateDiagnosticPack,
  fetchAgentDebug,
  updateAgentDebug,
  fetchWindowBackgroundWait,
  updateWindowBackgroundWait,
  type TaskStats,
  type AgentDebugConfig,
  type WindowBackgroundWaitConfig,
} from '@/api/settings';
import InfraHealthPanel from '@/components/Settings/InfraHealthPanel';
import DangerConfirmSettings from '@/components/Settings/DangerConfirmSettings';
import SecuritySettings from '@/components/Settings/SecuritySettings';
import DeviceSessionPanel from '@/components/Settings/DeviceSessionPanel';
import { classifyError } from '@/utils/errorHandler';
import { useTranslation } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';
import type { ReactNode } from 'react';

const { Text } = Typography;

interface TabItemDef {
  key: string;
  labelKey: string;
  icon: ReactNode;
}

const TAB_ITEMS: TabItemDef[] = [
  { key: 'cleanup', labelKey: 'settings.tab_cleanup', icon: <CloudServerOutlined /> },
  { key: 'config', labelKey: 'settings.tab_config', icon: <SettingOutlined /> },
  { key: 'diagnostic', labelKey: 'settings.tab_diagnostic', icon: <DownloadOutlined /> },
  { key: 'debug', labelKey: 'settings.tab_debug', icon: <BugOutlined /> },
  { key: 'language', labelKey: 'settings.tab_language', icon: <SettingOutlined /> },
  { key: 'infra', labelKey: 'settings.tab_infra', icon: <SettingOutlined /> },
  { key: 'danger', labelKey: 'settings.tab_danger', icon: <SettingOutlined /> },
  { key: 'security', labelKey: 'settings.tab_security', icon: <SafetyCertificateOutlined /> },
  { key: 'devices', labelKey: 'settings.tab_devices', icon: <DesktopOutlined /> },
];

/** Data Cleanup Tab */
function DataCleanupTab() {
  const { message } = App.useApp();
  const t = useTranslation();
  const [executionDays, setExecutionDays] = useState(30);
  const [screenshotGB, setScreenshotGB] = useState(10);
  const [logDays, setLogDays] = useState(7);
  const [stats, setStats] = useState<TaskStats | null>(null);
  const [loadingStats, setLoadingStats] = useState(false);
  const [cleaning, setCleaning] = useState(false);

  const fetchStats = useCallback(async (signal?: AbortSignal) => {
    setLoadingStats(true);
    try {
      const data = await fetchTaskStats({ signal });
      if (!signal?.aborted) {
        setStats(data);
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError' && !(err instanceof Error && err.name === 'CanceledError')) {
        /* backend not ready */
      }
    } finally {
      if (!signal?.aborted) setLoadingStats(false);
    }
  }, []);

  /** skip StrictMode test mount to avoid spurious ERR_ABORTED */
  const statsIsRealMountRef = useRef(false);
  useEffect(() => {
    if (!statsIsRealMountRef.current) {
      statsIsRealMountRef.current = true;
      return;
    }
    const controller = new AbortController();
    fetchStats(controller.signal);
    return () => {
      // Do not abort on unmount to avoid ERR_ABORTED in DevTools
    };
  }, [fetchStats]);

  const handleClean = async () => {
    setCleaning(true);
    try {
      await cleanupData({
        execution_retention_days: executionDays,
        screenshot_retention_gb: screenshotGB,
        log_retention_days: logDays,
      });
      message.success(t('settings.cleanup_done'));
      fetchStats();
    } catch {
      message.error(t('settings.cleanup_request_failed'));
    } finally {
      setCleaning(false);
    }
  };

  return (
    <div style={{ maxWidth: 600 }}>
      <Card title={t('settings.cleanup_current_data')} className="gaf-mb-lg">
        {loadingStats ? (
          <Spin />
        ) : (
          <div>
            <Text>{t('settings.cleanup_executions', { count: stats?.total_executions ?? '-' })}</Text>
            <br />
            <Text>{t('settings.cleanup_screenshots', { count: stats?.total_screenshots ?? '-' })}</Text>
            <br />
            <Text>{t('settings.cleanup_logs', { count: stats?.total_logs ?? '-' })}</Text>
          </div>
        )}
      </Card>

      <Card title={t('settings.cleanup_strategy')} className="gaf-mb-lg">
        <div className="gaf-mb-lg">
          <Text>{t('settings.cleanup_exec_days')}</Text>
          <InputNumber
            min={1}
            max={365}
            value={executionDays}
            onChange={(v) => setExecutionDays(v ?? 30)}
            className="gaf-w-full gaf-mt-xs"
          />
        </div>
        <div className="gaf-mb-lg">
          <Text>{t('settings.cleanup_screenshot_gb', { count: screenshotGB })}</Text>
          <Slider min={1} max={100} value={screenshotGB} onChange={setScreenshotGB} />
        </div>
        <div className="gaf-mb-lg">
          <Text>{t('settings.cleanup_log_days')}</Text>
          <InputNumber
            min={1}
            max={365}
            value={logDays}
            onChange={(v) => setLogDays(v ?? 7)}
            className="gaf-w-full gaf-mt-xs"
          />
        </div>
      </Card>

      <Popconfirm title={t('settings.cleanup_confirm')} onConfirm={handleClean}>
        <Button type="primary" danger loading={cleaning}>
          {t('settings.cleanup_btn')}
        </Button>
      </Popconfirm>
    </div>
  );
}

/** Config Import/Export Tab */
function ConfigTab() {
  const { message } = App.useApp();
  const t = useTranslation();
  const [importing, setImporting] = useState(false);

  const handleExport = () => {
    const config = {
      version: '1.0',
      exported_at: new Date().toISOString(),
      platform: 'GAF',
      settings: {
        execution_retention_days: 30,
        screenshot_retention_gb: 10,
        log_retention_days: 7,
      },
    };
    const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `settings_${new Date().toISOString().slice(0, 10)}.gafconfig`;
    a.click();
    URL.revokeObjectURL(url);
    message.success(t('settings.config_exported'));
  };

  const handleImport = async (file: UploadFile) => {
    setImporting(true);
    try {
      const text = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as string);
        reader.onerror = reject;
        if (file.originFileObj) {
          reader.readAsText(file.originFileObj);
        }
      });
      const parsed = JSON.parse(text);
      message.success(
        t('settings.config_imported', { version: parsed.version || t('settings.config_version_unknown') }),
      );
    } catch {
      message.error(t('settings.config_parse_failed'));
    } finally {
      setImporting(false);
    }
    return false;
  };

  return (
    <div style={{ maxWidth: 600 }}>
      <Card title={t('settings.config_export_title')} className="gaf-mb-lg">
        <Text type="secondary" className="gaf-mb-md gaf-display-block">
          {t('settings.config_export_desc')}
        </Text>
        <Button type="primary" icon={<DownloadOutlined />} onClick={handleExport}>
          {t('settings.config_export_btn')}
        </Button>
      </Card>

      <Card title={t('settings.config_import_title')}>
        <Text type="secondary" className="gaf-mb-md gaf-display-block">
          {t('settings.config_import_desc')}
        </Text>
        <Upload accept=".gafconfig,.json" maxCount={1} beforeUpload={handleImport} showUploadList={false}>
          <Button icon={<UploadOutlined />} loading={importing}>
            {t('settings.config_import_btn')}
          </Button>
        </Upload>
      </Card>
    </div>
  );
}

/** Diagnostic Pack Tab */
function DiagnosticTab() {
  const { message } = App.useApp();
  const t = useTranslation();
  const [generating, setGenerating] = useState(false);
  const [packReady, setPackReady] = useState(false);
  const [packUrl, setPackUrl] = useState('');

  const handleGenerate = async () => {
    setGenerating(true);
    message.loading({ content: t('settings.diag_collecting'), key: 'diag', duration: 0 });
    try {
      const blob = await generateDiagnosticPack();
      const url = URL.createObjectURL(blob);
      setPackUrl(url);
      setPackReady(true);
      message.success({ content: t('settings.diag_success'), key: 'diag' });
    } catch (err: unknown) {
      const classified = classifyError(err);
      message.error({ content: t('settings.diag_backend_not_ready', { message: classified.message }), key: 'diag' });
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = () => {
    if (!packUrl) return;
    const a = document.createElement('a');
    a.href = packUrl;
    a.download = `diagnostic_${new Date().toISOString().slice(0, 10)}.zip`;
    a.click();
    message.success(t('settings.diag_downloading'));
  };

  return (
    <div style={{ maxWidth: 600 }}>
      <Card title={t('settings.diag_generate_title')} className="gaf-mb-lg">
        <Text type="secondary" className="gaf-mb-md gaf-display-block">
          {t('settings.diag_generate_desc')}
        </Text>
        <Button type="primary" icon={<DownloadOutlined />} loading={generating} onClick={handleGenerate}>
          {t('settings.diag_generate_btn')}
        </Button>
      </Card>

      {packReady && (
        <Card title={t('settings.diag_download_title')}>
          <Button icon={<DownloadOutlined />} onClick={handleDownload}>
            {t('settings.diag_download_btn')}
          </Button>
        </Card>
      )}
    </div>
  );
}

/** Language Settings Tab */
function LanguageTab() {
  const t = useTranslation();
  return (
    <div style={{ maxWidth: 600 }}>
      <Card title={t('settings.lang_title')}>
        <div className="gaf-flex-center gaf-gap-md gaf-mb-lg">
          <Text>{t('settings.lang_current')}</Text>
          <LanguageSwitcher />
        </div>
        <Text type="secondary">{t('settings.lang_supported')}</Text>
      </Card>
    </div>
  );
}

/** Debug settings interface stored in localStorage */
interface DebugConfig {
  logLevel: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR';
  enableScreenshotOverlay: boolean;
  enablePerformanceTracing: boolean;
  enableVerboseLogging: boolean;
  consoleLogToServer: boolean;
  maxTraceEntries: number;
}

const DEBUG_STORAGE_KEY = 'gaf_debug_settings';

const DEFAULT_DEBUG_CONFIG: DebugConfig = {
  logLevel: 'INFO',
  enableScreenshotOverlay: false,
  enablePerformanceTracing: false,
  enableVerboseLogging: false,
  consoleLogToServer: false,
  maxTraceEntries: 100,
};

/**
 * Load debug config from localStorage with fallback to defaults
 */
function loadDebugConfig(): DebugConfig {
  try {
    const raw = localStorage.getItem(DEBUG_STORAGE_KEY);
    if (raw) return { ...DEFAULT_DEBUG_CONFIG, ...JSON.parse(raw) };
  } catch {
    /* ignore */
  }
  return { ...DEFAULT_DEBUG_CONFIG };
}

/**
 * Save debug config to localStorage
 */
function saveDebugConfig(cfg: DebugConfig): void {
  try {
    localStorage.setItem(DEBUG_STORAGE_KEY, JSON.stringify(cfg));
  } catch {
    /* ignore */
  }
}

/** Debug Settings Tab — I1 */
function DebugSettingsTab() {
  const { message } = App.useApp();
  const t = useTranslation();
  const [config, setConfig] = useState<DebugConfig>(loadDebugConfig);
  const [saving, setSaving] = useState(false);
  /** Track the save delay timer so it can be cleaned up on unmount */
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Worker debug mode state (backend AppSettings, not localStorage)
  const [agentDebug, setAgentDebug] = useState<AgentDebugConfig>({ enabled: false, dir: 'debug' });
  const [agentDebugLoading, setAgentDebugLoading] = useState(false);
  const [agentDebugSaving, setAgentDebugSaving] = useState(false);

  // Window background wait state (backend AppSettings singleton upsert)
  const [windowBgWait, setWindowBgWait] = useState<WindowBackgroundWaitConfig>({
    enabled: false,
    timeout_seconds: 1800,
    check_interval_ms: 500,
  });
  const [windowBgWaitLoading, setWindowBgWaitLoading] = useState(false);
  const [windowBgWaitSaving, setWindowBgWaitSaving] = useState(false);

  /** Fetch agent debug config from backend on mount */
  useEffect(() => {
    let cancelled = false;
    setAgentDebugLoading(true);
    fetchAgentDebug()
      .then((cfg) => {
        if (!cancelled) setAgentDebug(cfg);
      })
      .catch((err) => {
        // spec35 #12: backend may be unavailable; keep defaults. Log the
        // failure so protocol drift is debuggable.
        console.warn('[SystemSettings] fetchAgentDebug failed:', err);
      })
      .finally(() => {
        if (!cancelled) setAgentDebugLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /** Save agent debug config to backend */
  const handleSaveAgentDebug = async () => {
    setAgentDebugSaving(true);
    try {
      const updated = await updateAgentDebug(agentDebug);
      setAgentDebug(updated);
      message.success(t('settings.agent_debug_saved'));
    } catch (err) {
      message.error(classifyError(err).message);
    } finally {
      setAgentDebugSaving(false);
    }
  };

  /** Fetch window background wait config from backend on mount */
  useEffect(() => {
    let cancelled = false;
    setWindowBgWaitLoading(true);
    fetchWindowBackgroundWait()
      .then((cfg) => {
        if (!cancelled) setWindowBgWait(cfg);
      })
      .catch((err) => {
        // spec35 #12: backend may be unavailable; keep defaults. Log the
        // failure so protocol drift is debuggable.
        console.warn('[SystemSettings] fetchWindowBackgroundWait failed:', err);
      })
      .finally(() => {
        if (!cancelled) setWindowBgWaitLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /** Save window background wait config to backend */
  const handleSaveWindowBgWait = async () => {
    setWindowBgWaitSaving(true);
    try {
      const updated = await updateWindowBackgroundWait(windowBgWait);
      setWindowBgWait(updated);
      message.success(t('settings.window_bg_wait_saved'));
    } catch (err) {
      message.error(classifyError(err).message);
    } finally {
      setWindowBgWaitSaving(false);
    }
  };

  /** Clear any pending save timer on unmount */
  useEffect(() => {
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, []);

  /** Update a single config field and persist immediately */
  const updateField = useCallback(<K extends keyof DebugConfig>(key: K, value: DebugConfig[K]) => {
    setConfig((prev) => {
      const next = { ...prev, [key]: value };
      saveDebugConfig(next);
      return next;
    });
  }, []);

  /** Handle batch save for all settings */
  const handleSaveAll = async () => {
    setSaving(true);
    message.loading({ content: t('settings.debug_saving'), key: 'debug-save', duration: 0 });
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    await new Promise<void>((resolve) => {
      saveTimerRef.current = setTimeout(resolve, 500);
    });
    saveDebugConfig(config);
    message.success({ content: t('settings.debug_saved'), key: 'debug-save' });
    setSaving(false);
  };

  /** Reset all debug settings to defaults */
  const handleReset = () => {
    setConfig({ ...DEFAULT_DEBUG_CONFIG });
    saveDebugConfig(DEFAULT_DEBUG_CONFIG);
    message.info(t('settings.debug_reset_done'));
  };

  const logLevelOptions = [
    { label: <Tag color="blue">DEBUG</Tag>, value: 'DEBUG' },
    { label: <Tag color="green">INFO</Tag>, value: 'INFO' },
    { label: <Tag color="orange">WARNING</Tag>, value: 'WARNING' },
    { label: <Tag color="red">ERROR</Tag>, value: 'ERROR' },
  ];

  return (
    <div style={{ maxWidth: 700 }}>
      <Alert
        type="info"
        showIcon
        icon={<BugOutlined />}
        title={t('settings.debug_alert_title')}
        description={t('settings.debug_alert_desc')}
        className="gaf-mb-lg"
      />

      {/* Log Level Section */}
      <Card
        title={
          <>
            <FileTextOutlined /> {t('settings.debug_log_level_title')}
          </>
        }
        className="gaf-mb-lg"
      >
        <Space orientation="vertical" size="middle" className="gaf-w-full">
          <div>
            <Text>{t('settings.debug_log_level_desc')}</Text>
            <Select
              value={config.logLevel}
              onChange={(v) => updateField('logLevel', v)}
              options={logLevelOptions}
              className="gaf-w-full gaf-mt-xs"
            />
            <Text type="secondary" className="gaf-mt-xs gaf-display-block">
              {t('settings.debug_log_level_help')}
            </Text>
          </div>

          <div className="gaf-flex-between">
            <div>
              <Text>{t('settings.debug_verbose')}</Text>
              <br />
              <Text type="secondary" className="gaf-text-xs">
                {t('settings.debug_verbose_desc')}
              </Text>
            </div>
            <Switch checked={config.enableVerboseLogging} onChange={(v) => updateField('enableVerboseLogging', v)} />
          </div>

          <div className="gaf-flex-between">
            <div>
              <Text>{t('settings.debug_report')}</Text>
              <br />
              <Text type="secondary" className="gaf-text-xs">
                {t('settings.debug_report_desc')}
              </Text>
            </div>
            <Switch checked={config.consoleLogToServer} onChange={(v) => updateField('consoleLogToServer', v)} />
          </div>
        </Space>
      </Card>

      {/* Screenshot & Tracing Section */}
      <Card
        title={
          <>
            <CameraOutlined /> {t('settings.debug_screenshot_title')}
          </>
        }
        className="gaf-mb-lg"
      >
        <Space orientation="vertical" size="middle" className="gaf-w-full">
          <div className="gaf-flex-between">
            <div>
              <Text>{t('settings.debug_screenshot_overlay')}</Text>
              <br />
              <Text type="secondary" className="gaf-text-xs">
                {t('settings.debug_screenshot_overlay_desc')}
              </Text>
            </div>
            <Switch
              checked={config.enableScreenshotOverlay}
              onChange={(v) => updateField('enableScreenshotOverlay', v)}
            />
          </div>

          <div className="gaf-flex-between">
            <div>
              <Text>{t('settings.debug_perf_trace')}</Text>
              <br />
              <Text type="secondary" className="gaf-text-xs">
                {t('settings.debug_perf_trace_desc')}
              </Text>
            </div>
            <Switch
              checked={config.enablePerformanceTracing}
              onChange={(v) => updateField('enablePerformanceTracing', v)}
            />
          </div>

          <div>
            <Text>{t('settings.debug_max_entries')}</Text>
            <InputNumber
              min={10}
              max={10000}
              step={10}
              value={config.maxTraceEntries}
              onChange={(v) => updateField('maxTraceEntries', v ?? 100)}
              className="gaf-w-full gaf-mt-xs"
            />
          </div>
        </Space>
      </Card>

      {/* Worker Debug Mode Section (backend AppSettings) */}
      <Card
        title={
          <>
            <BugOutlined /> {t('settings.agent_debug_title')}
          </>
        }
        className="gaf-mb-lg"
        loading={agentDebugLoading}
      >
        <Space orientation="vertical" size="middle" className="gaf-w-full">
          <Alert type="info" showIcon description={t('settings.agent_debug_desc')} className="gaf-mb-sm" />
          <div className="gaf-flex-between">
            <div>
              <Text>{t('settings.agent_debug_enable')}</Text>
              <br />
              <Text type="secondary" className="gaf-text-xs">
                {t('settings.agent_debug_enable_desc')}
              </Text>
            </div>
            <Switch checked={agentDebug.enabled} onChange={(v) => setAgentDebug((prev) => ({ ...prev, enabled: v }))} />
          </div>
          <div>
            <Text>{t('settings.agent_debug_dir')}</Text>
            <br />
            <Text type="secondary" className="gaf-text-xs">
              {t('settings.agent_debug_dir_desc')}
            </Text>
            <Input
              value={agentDebug.dir}
              onChange={(e) => setAgentDebug((prev) => ({ ...prev, dir: e.target.value }))}
              placeholder="debug"
              className="gaf-mt-xs"
            />
          </div>
          <Button type="primary" icon={<SettingOutlined />} loading={agentDebugSaving} onClick={handleSaveAgentDebug}>
            {t('settings.agent_debug_save')}
          </Button>
        </Space>
      </Card>

      {/* Window Background Wait Section (backend AppSettings) */}
      <Card
        title={
          <>
            <AppstoreOutlined /> {t('settings.window_bg_wait_title')}
          </>
        }
        className="gaf-mb-lg"
        loading={windowBgWaitLoading}
      >
        <Space orientation="vertical" size="middle" className="gaf-w-full">
          <Alert type="info" showIcon description={t('settings.window_bg_wait_desc')} className="gaf-mb-sm" />
          <div className="gaf-flex-between">
            <div>
              <Text>{t('settings.window_bg_wait_enable')}</Text>
              <br />
              <Text type="secondary" className="gaf-text-xs">
                {t('settings.window_bg_wait_enable_desc')}
              </Text>
            </div>
            <Switch
              checked={windowBgWait.enabled}
              onChange={(v) => setWindowBgWait((prev) => ({ ...prev, enabled: v }))}
            />
          </div>
          <div>
            <Text>{t('settings.window_bg_wait_timeout')}</Text>
            <InputNumber
              min={0}
              max={86400}
              step={60}
              value={windowBgWait.timeout_seconds}
              onChange={(v) => setWindowBgWait((prev) => ({ ...prev, timeout_seconds: v ?? 1800 }))}
              className="gaf-w-full gaf-mt-xs"
            />
          </div>
          <div>
            <Text>{t('settings.window_bg_wait_interval')}</Text>
            <InputNumber
              min={100}
              max={5000}
              step={100}
              value={windowBgWait.check_interval_ms}
              onChange={(v) => setWindowBgWait((prev) => ({ ...prev, check_interval_ms: v ?? 500 }))}
              className="gaf-w-full gaf-mt-xs"
            />
          </div>
          <Button
            type="primary"
            icon={<SettingOutlined />}
            loading={windowBgWaitSaving}
            onClick={handleSaveWindowBgWait}
          >
            {t('settings.window_bg_wait_save')}
          </Button>
        </Space>
      </Card>

      {/* Actions */}
      <Divider />
      <Space>
        <Button type="primary" icon={<SettingOutlined />} loading={saving} onClick={handleSaveAll}>
          {t('settings.debug_save')}
        </Button>
        <Popconfirm title={t('settings.debug_reset_confirm')} onConfirm={handleReset}>
          <Button>{t('settings.debug_reset_btn')}</Button>
        </Popconfirm>
      </Space>
    </div>
  );
}

/** System Settings page */
export function SystemSettingsPage() {
  const t = useTranslation();
  return (
    <PageWrapper title={t('settings.page_title')}>
      <Tabs
        defaultActiveKey="cleanup"
        items={TAB_ITEMS.map((item) => ({
          key: item.key,
          label: (
            <span>
              {item.icon} {t(item.labelKey)}
            </span>
          ),
          children: (() => {
            switch (item.key) {
              case 'cleanup':
                return <DataCleanupTab />;
              case 'config':
                return <ConfigTab />;
              case 'diagnostic':
                return <DiagnosticTab />;
              case 'debug':
                return <DebugSettingsTab />;
              case 'language':
                return <LanguageTab />;
              case 'infra':
                return <InfraHealthPanel />;
              case 'danger':
                return <DangerConfirmSettings />;
              case 'security':
                return <SecuritySettings />;
              case 'devices':
                return <DeviceSessionPanel />;
              default:
                return null;
            }
          })(),
        }))}
      />
    </PageWrapper>
  );
}

export default SystemSettingsPage;
