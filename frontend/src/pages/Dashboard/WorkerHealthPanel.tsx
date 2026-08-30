/**
 * Worker health panel component
 * Displays CPU / memory / FPS for each Worker, highlights abnormal values, and updates via WebSocket
 */
import { useMemo, useEffect, useCallback, useRef, memo } from 'react';
// migration-test-marker
import { Card, Tag, Progress, Empty, Spin, theme as antTheme } from 'antd';
import type { GlobalToken } from 'antd/es/theme/interface';
import { DesktopOutlined, WarningFilled, CheckCircleFilled } from '@ant-design/icons';
import { useDeviceStore } from '@/stores/useDeviceStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useTranslation, getLocale } from '@/i18n';
import type { Worker, Device } from '@/types/models';

// TD-294 Phase 1: STATUS_COLOR moved to function so it can resolve antd theme tokens.
function getStatusColor(token: GlobalToken): Record<string, string> {
  return {
    online: token.colorSuccess,
    offline: token.colorTextQuaternary,
    busy: token.colorPrimary,
    idle: token.colorWarning,
  };
}

/** Extract numeric stat from device.device_stats, falling back to agent fields. */
function getStat(agent: Worker, device: Device | undefined, key: 'cpu' | 'memory' | 'fps'): number | null {
  if (key === 'cpu') {
    const deviceValue = (device?.device_stats as Record<string, unknown> | undefined)?.cpu;
    if (typeof deviceValue === 'number') return deviceValue;
    if (typeof agent.cpu_usage === 'number') return agent.cpu_usage;
    return null;
  }
  if (key === 'memory') {
    const deviceValue = (device?.device_stats as Record<string, unknown> | undefined)?.memory;
    if (typeof deviceValue === 'number') return deviceValue;
    if (typeof agent.memory_usage === 'number') return agent.memory_usage;
    return null;
  }
  const deviceFps = (device?.device_stats as Record<string, unknown> | undefined)?.fps;
  if (typeof deviceFps === 'number') return deviceFps;
  if (typeof agent.screenshot_fps === 'number') return agent.screenshot_fps;
  return device ? (device.screenshot_fps ?? null) : null;
}

function isAbnormal(agent: Worker, device?: Device): boolean {
  const cpu = getStat(agent, device, 'cpu');
  const memory = getStat(agent, device, 'memory');
  if (cpu !== null && cpu > 90) return true;
  if (memory !== null && memory > 90) return true;
  const fps = getStat(agent, device, 'fps');
  if (fps !== null && fps > 0 && fps < 10) return true;
  return false;
}

function getHealthColor(agent: Worker, device: Device | undefined, token: GlobalToken): string {
  if (isAbnormal(agent, device)) return token.colorError;
  if (agent.status === 'online') return token.colorSuccess;
  return token.colorTextQuaternary;
}

interface StatProgressProps {
  value: number;
  threshold?: number;
}

/** Memoized progress stat so only the bar re-renders when the value changes. */
const StatProgress = memo(function StatProgress({ value, threshold = 90 }: StatProgressProps) {
  const { token } = antTheme.useToken();
  return (
    <Progress
      percent={Math.round(value)}
      size="small"
      strokeColor={value > threshold ? token.colorError : undefined}
      format={(p) => `${p}%`}
    />
  );
});

interface StatValueProps {
  value: number;
}

/** Memoized plain value stat so only the number re-renders. */
const StatValue = memo(function StatValue({ value }: StatValueProps) {
  const { token } = antTheme.useToken();
  const color = value > 0 && value < 10 ? token.colorError : value > 0 ? token.colorSuccess : token.colorTextQuaternary;
  return (
    <span className="gaf-text-md gaf-font-semibold" style={{ color }}>
      {value >= 0 ? `${value.toFixed(1)} FPS` : '-'}
    </span>
  );
});

interface WorkerCardProps {
  agent: Worker;
  devices: Device[];
}

/** Compare only the fields that affect rendering to keep the card stable. */
function workerCardPropsEqual(prev: WorkerCardProps, next: WorkerCardProps): boolean {
  if (prev.agent.id !== next.agent.id) return false;
  const agentFields: (keyof Worker)[] = [
    'agent_id',
    'status',
    'hostname',
    'cpu_usage',
    'memory_usage',
    'screenshot_fps',
    'last_heartbeat',
  ];
  for (const f of agentFields) {
    if (prev.agent[f] !== next.agent[f]) return false;
  }
  // Compare the device list (one Worker = one machine may own MANY windows /
  // emulator instances — see docs/architecture/overview.md §Worker/Device).
  const prevSig = deviceSummary(prev.devices);
  const nextSig = deviceSummary(next.devices);
  return prevSig === nextSig;
}

/** Serialize a device list into a stable render-signature string. */
function deviceSummary(devices: Device[]): string {
  return devices
    .map((d) => {
      const stats = d.device_stats as Record<string, unknown> | undefined;
      return [
        d.id,
        d.status,
        d.name,
        typeof stats?.cpu === 'number' ? stats.cpu : null,
        typeof stats?.memory === 'number' ? stats.memory : null,
        typeof stats?.fps === 'number' ? stats.fps : null,
      ].join(':');
    })
    .join('|');
}

/** Memoized agent card to avoid re-rendering the whole card on every refresh. */
const WorkerCard = memo(function WorkerCard({ agent, devices }: WorkerCardProps) {
  const t = useTranslation();
  const { token } = antTheme.useToken();
  const STATUS_COLOR = getStatusColor(token);
  // Stats are per-agent; fall back to the first window's metrics when the
  // agent carries no aggregate fields (existing behavior).
  const firstDevice = devices[0];
  const abnormal = isAbnormal(agent, firstDevice);
  const borderColor = getHealthColor(agent, firstDevice, token);

  const STATUS_LABEL: Record<string, string> = {
    online: t('dashboard.agent_status_online'),
    offline: t('dashboard.agent_status_offline'),
    busy: t('dashboard.agent_status_busy'),
    idle: t('dashboard.status_idle'),
  };

  const cpu = getStat(agent, firstDevice, 'cpu');
  const memory = getStat(agent, firstDevice, 'memory');
  const fps = getStat(agent, firstDevice, 'fps');

  return (
    <div
      className="gaf-py-md gaf-px-lg gaf-mb-sm gaf-radius-lg"
      style={{
        border: `1px solid ${borderColor}`,
        background: abnormal ? token.colorErrorBg : token.colorBgContainer,
        transition: 'border-color 0.3s, background 0.3s',
      }}
    >
      <div className="gaf-flex-between gaf-mb-sm">
        <div className="gaf-flex-center gaf-gap-sm">
          <DesktopOutlined className="gaf-text-md" style={{ color: borderColor }} />
          <div className="gaf-flex-col">
            <strong>{agent.hostname || agent.agent_id}</strong>
            {/* One Worker = one machine that owns ALL its windows (PC windows +
                emulator instances) — list every device, not just the first. */}
            {devices.length > 0 && (
              <div className="gaf-flex" style={{ gap: 4, flexWrap: 'wrap' }}>
                {devices.map((d) => (
                  <Tag
                    key={d.id}
                    className="gaf-text-xs"
                    color={d.status === 'online' ? 'green' : 'default'}
                    style={{ marginInlineEnd: 0 }}
                  >
                    {d.name}
                  </Tag>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="gaf-flex-center" style={{ gap: 6 }}>
          {abnormal ? (
            <WarningFilled style={{ color: token.colorError }} />
          ) : (
            <CheckCircleFilled style={{ color: token.colorSuccess }} />
          )}
          <Tag color={(agent.status && STATUS_COLOR[agent.status]) || 'default'}>
            {(agent.status && STATUS_LABEL[agent.status]) || agent.status}
          </Tag>
        </div>
      </div>

      <div className="gaf-gap-md" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr' }}>
        <div>
          <div className="gaf-text-xs" style={{ color: token.colorTextSecondary, marginBottom: 2 }}>
            {t('dashboard.cpu_label')}
          </div>
          {cpu !== null && cpu >= 0 ? (
            <StatProgress value={cpu} />
          ) : (
            <span className="gaf-text-xs" style={{ color: token.colorTextQuaternary }}>
              {t('dashboard.no_data')}
            </span>
          )}
        </div>
        <div>
          <div className="gaf-text-xs" style={{ color: token.colorTextSecondary, marginBottom: 2 }}>
            {t('dashboard.memory_label')}
          </div>
          {memory !== null && memory >= 0 ? (
            <StatProgress value={memory} />
          ) : (
            <span className="gaf-text-xs" style={{ color: token.colorTextQuaternary }}>
              {t('dashboard.no_data')}
            </span>
          )}
        </div>
        <div>
          <div className="gaf-text-xs" style={{ color: token.colorTextSecondary, marginBottom: 2 }}>
            {t('dashboard.fps_label')}
          </div>
          {fps !== null && fps >= 0 ? (
            <StatValue value={fps} />
          ) : (
            <span className="gaf-text-xs" style={{ color: token.colorTextQuaternary }}>
              {t('dashboard.no_data')}
            </span>
          )}
        </div>
      </div>

      {agent.last_heartbeat && (
        <div className="gaf-text-xxs" style={{ color: token.colorTextTertiary, marginTop: 6 }}>
          {t('dashboard.heartbeat')}: {new Date(agent.last_heartbeat).toLocaleTimeString(getLocale())}
        </div>
      )}
    </div>
  );
}, workerCardPropsEqual);

/** Collect ALL devices (windows / emulator instances) owned by this agent.
 *
 * Model (docs/architecture/overview.md): one machine runs one Worker process
 * and discovers every window on it — PC windows AND emulator instances are all
 * registered as Device rows under that Worker.
 */
function findWorkerDevices(agent: Worker, devices: Device[]): Device[] {
  return devices.filter(
    (d) => d.agent === agent.id || d.agent_info?.id === agent.id || d.agent_info?.agent_id === agent.agent_id,
  );
}

export function WorkerHealthPanel() {
  const t = useTranslation();
  const { agents, devices, loading, fetchAgents, fetchDevices } = useDeviceStore();
  const initialLoadRef = useRef(false);

  const refresh = useCallback(() => {
    fetchAgents();
    fetchDevices();
  }, [fetchAgents, fetchDevices]);

  useEffect(() => {
    refresh();
    initialLoadRef.current = true;
    // Safety-net poll: 60s (down from 10s). Real-time updates are handled
    // by the agent_heartbeat / agent_status WS subscriptions below.
    const interval = setInterval(refresh, 60000);
    return () => clearInterval(interval);
  }, [refresh]);

  const lastFetchRef = useRef<number>(0);
  const throttledRefresh = useCallback(() => {
    const now = Date.now();
    if (now - lastFetchRef.current < 5000) return;
    lastFetchRef.current = now;
    refresh();
  }, [refresh]);

  useWebSocket('agent_heartbeat', throttledRefresh);
  useWebSocket('agent_status', throttledRefresh);

  const onlineCount = useMemo(() => agents.filter((a) => a.status !== 'offline').length, [agents]);
  const abnormalCount = useMemo(
    () => agents.filter((a) => isAbnormal(a, findWorkerDevices(a, devices)[0])).length,
    [agents, devices],
  );

  const agentList = useMemo(
    () =>
      [...agents].sort((a, b) => {
        const order: Record<string, number> = { online: 0, busy: 1, idle: 2, offline: 3 };
        return ((a.status && order[a.status]) ?? 9) - ((b.status && order[b.status]) ?? 9);
      }),
    [agents],
  );

  const content = useMemo(() => {
    if (agentList.length === 0) {
      return <Empty description={t('dashboard.empty_agents')} image={Empty.PRESENTED_IMAGE_SIMPLE} />;
    }
    return agentList.map((agent) => (
      <WorkerCard key={agent.id} agent={agent} devices={findWorkerDevices(agent, devices)} />
    ));
  }, [agentList, devices, t]);

  return (
    <Card
      title={
        <div className="gaf-flex-center gaf-gap-md">
          <span>{t('dashboard.widget_device_status')}</span>
          <Tag color="green">{t('dashboard.online_count', { count: onlineCount })}</Tag>
          {abnormalCount > 0 && <Tag color="red">{t('dashboard.abnormal_count', { count: abnormalCount })}</Tag>}
        </div>
      }
    >
      {loading && !initialLoadRef.current ? (
        <Spin className="gaf-display-block" style={{ margin: '24px auto' }} />
      ) : (
        content
      )}
    </Card>
  );
}

export default WorkerHealthPanel;
