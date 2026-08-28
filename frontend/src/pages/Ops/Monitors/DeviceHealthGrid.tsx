import { useEffect, useState, useCallback } from 'react';
import { Card, Progress, Tag, Statistic, Row, Col, Spin, Empty, theme } from 'antd';
import type { GlobalToken } from 'antd/es/theme/interface';
import { fetchDeviceHealth as fetchDeviceHealthRaw } from '@/api/monitors';
import { useTranslation } from '@/i18n';

/** device health status enum */
type DeviceStatus = 'healthy' | 'warning' | 'critical' | 'offline';

/** single device health data structure */
interface DeviceHealth {
  id: string;
  name: string;
  status: DeviceStatus;
  health_score: number;
  cpu_usage: number;
  memory_usage: number;
  disk_usage: number;
  latency_ms: number;
  fps: number;
  frame_time_ms: number;
}

/** API return device health list structure — after end return { devices: [...] } */
interface DeviceHealthResponse {
  devices?: DeviceHealth[];
  results?: DeviceHealth[];
}

/** from after end response mapping to before end DeviceHealth format */
function mapBackendToDeviceHealth(raw: Record<string, unknown>): DeviceHealth {
  return {
    id: (raw.id as string) || (raw.name as string) || 'unknown',
    name: (raw.name as string) || 'Unknown',
    status: (raw.status as DeviceStatus) || 'offline',
    health_score: (raw.score as number) ?? (raw.health_score as number) ?? 0,
    cpu_usage: (raw.cpu as number) ?? (raw.cpu_usage as number) ?? 0,
    memory_usage: (raw.memory as number) ?? (raw.memory_usage as number) ?? 0,
    disk_usage: (raw.disk as number) ?? (raw.disk_usage as number) ?? 0,
    latency_ms: (raw.network_latency as number) ?? (raw.latency_ms as number) ?? 0,
    fps: (raw.fps as number) ?? 0,
    frame_time_ms: (raw.frame_time as number) ?? (raw.frame_time_ms as number) ?? 0,
  };
}

/** auto refresh interval (ms) */
const REFRESH_INTERVAL = 30_000;

/** health status to corresponding Tag color mapping */
const STATUS_TAG_COLOR_MAP: Record<DeviceStatus, string> = {
  healthy: 'success',
  warning: 'warning',
  critical: 'error',
  offline: 'default',
};

/** Map a device status to its localized label (uses i18n at call site). */
function statusLabelKey(status: DeviceStatus): string {
  if (status === 'healthy') return 'monitors.device_status_healthy';
  if (status === 'warning') return 'monitors.device_status_warning';
  return 'monitors.device_status_critical';
}

/**
 * map device status to its border color using design tokens
 * healthy → success / warning → warning / critical → error
 */
function getStatusBorderColor(status: DeviceStatus, token: GlobalToken): string {
  if (status === 'healthy') return token.colorSuccess;
  if (status === 'warning') return token.colorWarning;
  return token.colorError;
}

/**
 * based on use rate percentage return dashboard color
 * < 60% green / 60~80% orange / >= 80% red
 * @param value use rate percentage (0-100)
 * @param token antd design token
 * @returns corresponding color value
 */
function getGaugeColor(value: number, token: GlobalToken): string {
  if (value < 60) return token.colorSuccess;
  if (value < 80) return token.colorWarning;
  return token.colorError;
}

/**
 * based on health score return progress bar color
 * >= 80 green / 50~79 orange / < 50 red
 * @param score health score (0-100)
 * @param token antd design token
 * @returns corresponding color value
 */
function getHealthScoreColor(score: number, token: GlobalToken): string {
  if (score >= 80) return token.colorSuccess;
  if (score >= 50) return token.colorWarning;
  return token.colorError;
}

/**
 * from after end get all device health data
 * @returns device health data array, fail when return empty array
 */
async function loadDeviceHealth(): Promise<DeviceHealth[]> {
  try {
    const raw = (await fetchDeviceHealthRaw()) as DeviceHealthResponse;
    const list = raw.devices ?? raw.results ?? [];
    return list.map((item) => mapBackendToDeviceHealth(item as unknown as Record<string, unknown>));
  } catch {
    return [];
  }
}

/**
 * single device health card child component
 *
 * show single device complete health info:
 * - device name and status Tag
 * - circular health score progress ring
 * - CPU/ inside storage / disk / latency four mini dashboards (Progress dashboard)
 * - bottom FPS and frame time stats
 *
 * card border color based on device status dynamic change:
 * - healthy → green border
 * - warning → yellow border
 * - critical → red border + pulse blink animation
 */
function DeviceCard({ device }: { device: DeviceHealth }) {
  const t = useTranslation();
  const { token } = theme.useToken();
  /** is no at in critical status ( used for controls blink animation ) */
  const isCritical = device.status === 'critical';

  return (
    <Card
      size="small"
      style={{
        borderColor: getStatusBorderColor(device.status, token),
        borderWidth: 2,
        animation: isCritical ? 'criticalPulse 1.5s ease-in-out infinite' : 'none',
      }}
      title={
        <div className="gaf-flex-between">
          <span className="gaf-font-semibold">{device.name}</span>
          <Tag color={STATUS_TAG_COLOR_MAP[device.status]}>{t(statusLabelKey(device.status))}</Tag>
        </div>
      }
    >
      {/* 健康分数圆形进度 */}
      <div className="gaf-mb-md gaf-flex gaf-justify-center">
        <Progress
          type="circle"
          percent={device.health_score}
          size={64}
          strokeColor={getHealthScoreColor(device.health_score, token)}
          format={(percent) => `${percent ?? 0}`}
        />
      </div>

      {/* 四个指标迷你仪表盘 */}
      <Row gutter={[8, 8]}>
        <Col span={12}>
          <div className="gaf-text-center">
            <Progress
              type="dashboard"
              percent={device.cpu_usage}
              size={48}
              strokeColor={getGaugeColor(device.cpu_usage, token)}
              format={(p) => `${p ?? 0}%`}
            />
            <div className="gaf-text-xxs" style={{ color: token.colorTextSecondary, marginTop: 2 }}>
              CPU
            </div>
          </div>
        </Col>
        <Col span={12}>
          <div className="gaf-text-center">
            <Progress
              type="dashboard"
              percent={device.memory_usage}
              size={48}
              strokeColor={getGaugeColor(device.memory_usage, token)}
              format={(p) => `${p ?? 0}%`}
            />
            <div className="gaf-text-xxs" style={{ color: token.colorTextSecondary, marginTop: 2 }}>
              {t('monitors.metric_memory')}
            </div>
          </div>
        </Col>
        <Col span={12}>
          <div className="gaf-text-center">
            <Progress
              type="dashboard"
              percent={device.disk_usage}
              size={48}
              strokeColor={getGaugeColor(device.disk_usage, token)}
              format={(p) => `${p ?? 0}%`}
            />
            <div className="gaf-text-xxs" style={{ color: token.colorTextSecondary, marginTop: 2 }}>
              {t('monitors.metric_disk')}
            </div>
          </div>
        </Col>
        <Col span={12}>
          <div className="gaf-text-center">
            <Progress
              type="dashboard"
              percent={Math.min(device.latency_ms / 2, 100)}
              size={48}
              strokeColor={getGaugeColor(Math.min(device.latency_ms / 2, 100), token)}
              format={() => `${device.latency_ms}ms`}
            />
            <div className="gaf-text-xxs" style={{ color: token.colorTextSecondary, marginTop: 2 }}>
              {t('monitors.metric_latency')}
            </div>
          </div>
        </Col>
      </Row>

      {/* 底部 FPS 和帧耗时 */}
      <div
        className="gaf-mt-md gaf-flex"
        style={{
          paddingTop: 8,
          borderTop: `1px solid ${token.colorBorderSecondary}`,
          justifyContent: 'space-around',
        }}
      >
        <Statistic
          title="FPS"
          value={device.fps > 0 ? device.fps.toFixed(0) : '—'}
          styles={{ content: { fontSize: 14, color: device.fps > 0 ? undefined : token.colorTextTertiary } }}
        />
        <Statistic
          title={t('monitors.metric_frame_time')}
          value={device.frame_time_ms}
          suffix="ms"
          styles={{ content: { fontSize: 14 } }}
        />
      </div>

      {/* Critical 状态脉冲动画样式注入 (C 类保留: keyframes rgba 为 CSS 内联, 无法用 token) */}
      {isCritical && (
        <style>{`
          @keyframes criticalPulse {
            0%, 100% { box-shadow: 0 0 0 0 rgba(255, 77, 79, 0.4); }
            50% { box-shadow: 0 0 0 6px rgba(255, 77, 79, 0); }
          }
        `}</style>
      )}
    </Card>
  );
}

/**
 * device health level grid component
 *
 * with response style grid layout show has device real-time health status:
 * - xs=24 ( mobile single column )
 * - sm=12 ( tablet double column )
 * - lg=6 ( desktop four column )
 *
 * each card includes:
 * - device name + status Tag
 * - circular health score progress ring
 * - CPU / inside storage / disk / latency mini dashboard
 * - bottom FPS and frame time stats
 *
 * card border color encode:
 * - healthy → green (#52c41a)
 * - warning → yellow (#faad14)
 * - critical → red (#ff4d4f) + pulse blink animation
 *
 * every 15 seconds auto poll refresh data.
 * no device when show empty state prompt.
 */
export function DeviceHealthGrid() {
  const t = useTranslation();
  const [devices, setDevices] = useState<DeviceHealth[]>([]);
  const [loading, setLoading] = useState(true);

  /**
   * load device health data and update status
   * use useCallback to avoid reference changes when timer is rebuilt
   */
  const loadData = useCallback(async () => {
    setLoading(true);
    const result = await loadDeviceHealth();
    setDevices(result);
    setLoading(false);
  }, []);

  /**
   * component mount when first load, after every 15 seconds auto refresh;
   * unmount when clear fixed when device
   */
  useEffect(() => {
    loadData();
    const timer = setInterval(loadData, REFRESH_INTERVAL);
    return () => clearInterval(timer);
  }, [loadData]);

  return (
    <Spin spinning={loading}>
      {devices.length === 0 && !loading ? (
        <Empty description={t('monitors.empty_device_health')} />
      ) : (
        <Row gutter={[12, 12]}>
          {devices.map((device) => (
            <Col key={device.id} xs={24} sm={12} lg={6}>
              <DeviceCard device={device} />
            </Col>
          ))}
        </Row>
      )}
    </Spin>
  );
}

export default DeviceHealthGrid;
