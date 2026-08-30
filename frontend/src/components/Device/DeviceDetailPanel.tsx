/**
 * device detail drawer panel
 * shows device real-time screenshot stream, basic info, action buttons
 * supports both Worker WebSocket screenshot stream and HTTP polling screenshot modes
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import {
  Drawer,
  Descriptions,
  Tag,
  Button,
  Space,
  Typography,
  Divider,
  App,
  Popconfirm,
  theme as antTheme,
} from 'antd';
import {
  CameraOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  DeleteOutlined,
  SaveOutlined,
  LockOutlined,
  UnlockOutlined,
  ScheduleOutlined,
  FileTextOutlined,
  ReloadOutlined,
  InfoCircleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import GafCanvasOverlay from '@/components/Canvas/GafCanvasOverlay';
import { useScreenshotStream } from '@/hooks/useScreenshotStream';
import { useDeviceStore } from '@/stores/useDeviceStore';
import { testScreenshot } from '@/api/devices';
import DeviceOperationPanel from './DeviceOperationPanel';
import DispatchRoutineModal from '@/components/GameProfile/DispatchRoutineModal';
import type { ControlMode, Device, DeviceStatus } from '@/types/models';
import { useTranslation } from '@/i18n';
import { useNavigate } from 'react-router-dom';

interface DeviceDetailPanelProps {
  device: Device | null;
  open: boolean;
  onClose: () => void;
  onDelete?: (device: Device) => void;
}

const TYPE_LABEL_MAP: Record<string, string> = {
  windows: 'Windows',
  emulator: '模拟器',
};

const STATUS_COLOR_MAP: Record<string, string> = {
  online: 'green',
  offline: 'default',
  busy: 'orange',
  error: 'red',
  locked: 'purple',
};

const STATUS_LABEL_MAP: Record<string, string> = {
  online: '在线',
  offline: '离线',
  busy: '忙碌',
  error: '错误',
  locked: '已锁定',
  idle: '空闲',
  running: '运行中',
};

/** Default concrete methods for each control mode (mirrors backend Device.CONTROL_MODE_DEFAULTS).
 *  Used to decide whether screenshot_method / input_method are overrides worth displaying.
 *  Note: 'auto' is a meta-mode (system picks concrete mode), so it has no defaults. */
const CONTROL_MODE_DEFAULTS: Partial<Record<ControlMode, { screenshot: string; input: string }>> = {
  foreground: { screenshot: 'auto', input: 'SendInput' },
  background: { screenshot: 'auto', input: 'PostMessage' },
  pseudo_background: { screenshot: 'printwindow', input: 'PseudoBackground' },
};

/** Return a user-facing label key for a control mode value. */
function getControlModeColor(mode: ControlMode): string {
  if (mode === 'foreground') return 'green';
  if (mode === 'background') return 'blue';
  return 'orange';
}

/**
 * Stats keys already shown in 基本信息 (screenshot_latency_avg_ms, screenshot_method)
 * are excluded from 设备统计 to avoid duplication. Order defines display sequence.
 */
const STAT_DISPLAY_ORDER = ['screenshot_fps', 'total_screenshots', 'cpu', 'memory', 'fps'] as const;

/** Keys hidden from 设备统计 because they already appear in 基本信息. */
const HIDDEN_STAT_KEYS = new Set<string>(['screenshot_latency_avg_ms', 'screenshot_method']);

/** Unit suffix for known numeric stats (rendered after the value). */
const STAT_UNIT_MAP: Record<string, string> = {
  screenshot_fps: ' FPS',
  fps: ' FPS',
  cpu: '%',
  memory: '%',
};

/** screenshot frame data */
interface ScreenshotFrame {
  imageBase64: string;
  width: number;
  height: number;
  timestamp: string;
}

/**
 * device detail drawer
 * left: real-time screenshot stream + right: device basic info + bottom: action bar
 */
export function DeviceDetailPanel({ device, open, onClose, onDelete }: DeviceDetailPanelProps) {
  const { token } = antTheme.useToken();
  const { message } = App.useApp();
  const t = useTranslation();
  const navigate = useNavigate();
  const wsStream = useScreenshotStream();
  const { deleteDevice, lockDevice, unlockDevice, fetchDevices } = useDeviceStore();
  const [saving, setSaving] = useState(false);
  const [locking, setLocking] = useState(false);
  const [coordPickTarget, setCoordPickTarget] = useState<'click' | 'swipeStart' | 'swipeEnd' | null>(null);
  const [selectedCoordinate, setSelectedCoordinate] = useState<{ x: number; y: number } | null>(null);
  const [dispatchOpen, setDispatchOpen] = useState(false);

  const [pollingFrame, setPollingFrame] = useState<ScreenshotFrame | null>(null);
  const [polling, setPolling] = useState(false);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollingLoadingRef = useRef(false);

  /** Prefer WebSocket stream; fall back to HTTP polling when no agent is connected. */
  const isStreaming = wsStream.isStreaming || polling;
  const currentFrame = wsStream.currentFrame || pollingFrame;

  /** HTTP polling screenshot (fallback when no Worker) */
  const pollScreenshot = useCallback(async () => {
    if (!device || pollingLoadingRef.current) return;
    pollingLoadingRef.current = true;
    try {
      const res = await testScreenshot(device.id);
      if (res.success && res.screenshot_base64) {
        setPollingFrame({
          imageBase64: res.screenshot_base64,
          width: res.resolution?.width || 1280,
          height: res.resolution?.height || 720,
          timestamp: new Date().toISOString(),
        });
      }
    } catch {
      // 轮询失败静默忽略 — 下一次轮询会重试
    } finally {
      pollingLoadingRef.current = false;
    }
  }, [device?.id]);

  const startPolling = useCallback(() => {
    setPolling(true);
    pollScreenshot();
    pollingRef.current = setInterval(pollScreenshot, 2000);
  }, [pollScreenshot]);

  const stopPolling = useCallback(() => {
    setPolling(false);
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  /** Start screenshot stream: WebSocket if agent is online, else HTTP polling. */
  const handleStartStream = useCallback(() => {
    const agentId = device?.agent_info?.agent_id;
    if (agentId) {
      wsStream.startStream(agentId);
    } else {
      startPolling();
    }
  }, [device?.agent_info?.agent_id, startPolling, wsStream]);

  /** Stop both WebSocket stream and HTTP polling. */
  const handleStopStream = useCallback(() => {
    wsStream.stopStream();
    stopPolling();
  }, [stopPolling, wsStream]);

  useEffect(() => {
    if (open && device) {
      handleStartStream();
    } else {
      handleStopStream();
    }
    return () => {
      handleStopStream();
    };
  }, [open, device?.id, device?.agent_info?.agent_id, handleStartStream, handleStopStream]);

  /** save current screenshot */
  const handleSaveScreenshot = () => {
    if (!currentFrame) {
      message.warning(t('devices.no_screenshot_to_save'));
      return;
    }
    setSaving(true);
    try {
      // Auto-detect MIME from base64 header: JPEG starts with /9j/, PNG with iVBOR
      const isJpeg = currentFrame.imageBase64.startsWith('/9j/');
      const mime = isJpeg ? 'image/jpeg' : 'image/png';
      const ext = isJpeg ? 'jpg' : 'png';
      const link = document.createElement('a');
      link.download = `screenshot_${device?.name || 'device'}_${Date.now()}.${ext}`;
      link.href = `data:${mime};base64,${currentFrame.imageBase64}`;
      link.click();
      message.success(t('devices.screenshot_saved'));
    } finally {
      setSaving(false);
    }
  };

  /** delete device */
  const handleDelete = async () => {
    if (!device) return;
    try {
      handleStopStream();
      await deleteDevice(device.id);
      message.success(t('devices.device_removed'));
      onDelete?.(device);
      onClose();
    } catch {
      message.error(t('devices.remove_device_failed'));
    }
  };

  /** lock/unlock device */
  const handleToggleLock = async () => {
    if (!device) return;
    setLocking(true);
    try {
      if (device.locked_by_username) {
        await unlockDevice(device.id);
        message.success(t('devices.device_unlocked'));
      } else {
        await lockDevice(device.id);
        message.success(t('devices.device_locked'));
      }
      await fetchDevices();
    } catch {
      message.error(t('devices.operation_failed'));
    } finally {
      setLocking(false);
    }
  };

  /** Handle coordinate pick from canvas click */
  const handleCanvasClick = useCallback(
    (x: number, y: number) => {
      if (!coordPickTarget) return;
      setCoordPickTarget(null);
      setSelectedCoordinate({ x: Math.round(x), y: Math.round(y) });
      message.info(t('devices.coordinate_picked', { x: Math.round(x), y: Math.round(y) }));
    },
    [coordPickTarget, message],
  );

  /** Request coordinate pick from operation panel */
  const handleRequestCoordinatePick = useCallback(
    (target: 'click' | 'swipeStart' | 'swipeEnd') => {
      setCoordPickTarget(target);
      message.info(t('devices.click_target_in_screenshot'));
    },
    [message],
  );

  if (!device) return null;

  const width = device.resolution_width || 1280;
  const height = device.resolution_height || 720;
  // spec-29j Phase 2d: `device.status` is optional in schema (`DeviceStatusEnum | undefined`).
  // Default to 'offline' when missing so `displayStatus` is always a valid index for STATUS_*_MAP.
  // 'locked' remains a frontend-only display state derived from `locked_by_username != null`.
  const displayStatus: DeviceStatus = device.locked_by_username ? 'locked' : (device.status ?? 'offline');

  /** Translatable labels for known device_stats keys. Unknown keys fall back
   *  to the raw key name (so new backend stats remain visible, just untranslated). */
  const STAT_LABEL_MAP: Record<string, string> = {
    screenshot_fps: t('devices.stat_screenshot_fps'),
    total_screenshots: t('devices.stat_total_screenshots'),
    cpu: t('devices.stat_cpu'),
    memory: t('devices.stat_memory'),
    fps: t('devices.stat_fps'),
  };

  /** Build the stats entries to display: ordered known keys first, then any
   *  unknown keys; keys already shown in 基本信息 are excluded to avoid dup. */
  const knownStats = STAT_DISPLAY_ORDER.filter((k) => device.device_stats && k in device.device_stats);
  const allStats = device.device_stats ? Object.keys(device.device_stats) : [];
  const unknownStats = allStats.filter(
    (k) => !STAT_DISPLAY_ORDER.includes(k as (typeof STAT_DISPLAY_ORDER)[number]) && !HIDDEN_STAT_KEYS.has(k),
  );
  const statKeys = [...knownStats, ...unknownStats];
  // spec-29j Phase 2d: `device.device_stats` is now `DeviceStatsSchema` (typed object) instead of
  // `Record<string, unknown>`. Cast to `Record<string, unknown>` for dynamic stat key iteration —
  // `STAT_DISPLAY_ORDER` may include keys outside the 10 declared schema fields (e.g. backend-added
  // diagnostic keys like `agent_pid`), and unknown keys should still render via `unknownStats`.
  const statsRecord = device.device_stats as unknown as Record<string, unknown> | null;
  const statEntries = statKeys
    .map((k) => [k, statsRecord?.[k]] as const)
    .filter(([, v]) => v !== undefined && v !== null);

  /** Format a stat value: numbers get locale formatting + optional unit suffix. */
  const formatStatValue = (statKey: string, value: unknown): string => {
    if (typeof value === 'number') {
      return `${value.toLocaleString()}${STAT_UNIT_MAP[statKey] ?? ''}`;
    }
    return String(value);
  };

  return (
    <Drawer
      title={
        <Space>
          <Typography.Text strong>{device.name}</Typography.Text>
          <Tag color={STATUS_COLOR_MAP[displayStatus]}>{STATUS_LABEL_MAP[displayStatus]}</Tag>
          {device.emulator_brand && <Tag color="blue">{device.emulator_brand}</Tag>}
        </Space>
      }
      placement="right"
      size={900}
      open={open}
      onClose={() => {
        handleStopStream();
        onClose();
      }}
      destroyOnHidden
    >
      <div className="gaf-flex gaf-flex-wrap gaf-gap-xl">
        <div style={{ flex: '1 1 500px', minWidth: 300 }}>
          <Typography.Title level={5} className="gaf-section-title">
            <CameraOutlined aria-hidden="true" /> {t('devices.section_live_screenshot')}
            <Typography.Text type="secondary" className="gaf-text-xs gaf-ml-sm">
              {isStreaming ? t('devices.stream_polling') : t('devices.stream_stopped')}
            </Typography.Text>
          </Typography.Title>
          <div
            style={{
              border: `1px solid ${token.colorBorder}`,
              borderRadius: 8,
              background: token.colorBgLayout,
              overflow: 'hidden',
              height: 400,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {currentFrame ? (
              <GafCanvasOverlay
                width={currentFrame.width || width}
                height={currentFrame.height || height}
                annotations={[]}
                imageBase64={currentFrame.imageBase64}
                style={{
                  maxWidth: '100%',
                  maxHeight: '100%',
                  width: '100%',
                  height: '100%',
                  border: 'none',
                }}
                showCrosshair={coordPickTarget !== null}
                onCanvasClick={handleCanvasClick}
              />
            ) : (
              <div
                className="gaf-flex-center"
                style={{
                  width: '100%',
                  justifyContent: 'center',
                  color: token.colorTextSecondary,
                }}
              >
                <CameraOutlined className="gaf-mr-md" style={{ fontSize: 48 }} />
                <Typography.Text type="secondary">
                  {isStreaming ? '等待截图帧...' : '点击「开始截图」获取实时画面'}
                </Typography.Text>
              </div>
            )}
          </div>

          <div className="gaf-mt-lg gaf-flex gaf-flex-wrap gaf-gap-sm">
            {isStreaming ? (
              <Button icon={<PauseCircleOutlined />} onClick={handleStopStream}>
                停止截图
              </Button>
            ) : (
              <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleStartStream}>
                开始截图
              </Button>
            )}
            {!isStreaming && (
              <Button icon={<ReloadOutlined />} onClick={pollScreenshot}>
                单次截图
              </Button>
            )}
            <Button icon={<SaveOutlined />} onClick={handleSaveScreenshot} loading={saving} disabled={!currentFrame}>
              保存截图
            </Button>
            <Button
              icon={device.locked_by_username ? <UnlockOutlined /> : <LockOutlined />}
              onClick={handleToggleLock}
              loading={locking}
            >
              {device.locked_by_username ? '解锁' : '锁定'}
            </Button>
            <Popconfirm title="确定要移除此设备？" onConfirm={handleDelete} okText="确定" cancelText="取消">
              <Button danger icon={<DeleteOutlined />}>
                移除设备
              </Button>
            </Popconfirm>
            <Button icon={<FileTextOutlined />} onClick={() => navigate(`/devices/adb-logs/${device.id}`)}>
              ADB 日志
            </Button>
            <Button
              type="primary"
              ghost
              icon={<ThunderboltOutlined />}
              onClick={() => setDispatchOpen(true)}
              disabled={!device.game_profile || device.status !== 'online'}
              title={
                !device.game_profile
                  ? t('gameProfiles.tip_no_game_profile')
                  : device.status !== 'online'
                    ? t('gameProfiles.dispatch_device_offline')
                    : undefined
              }
            >
              {t('gameProfiles.btn_dispatch_for_window')}
            </Button>
          </div>

          <Divider />

          <DeviceOperationPanel
            deviceId={device.id}
            deviceName={device.name}
            screenshotWidth={currentFrame?.width || width}
            screenshotHeight={currentFrame?.height || height}
            onRequestCoordinatePick={handleRequestCoordinatePick}
            prefilledCoordinate={selectedCoordinate}
          />
        </div>

        <div style={{ flex: '0 0 280px' }}>
          <Typography.Title level={5} className="gaf-section-title">
            {t('devices.section_basic_info')}
          </Typography.Title>
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label={t('devices.label_device_name')}>{device.name}</Descriptions.Item>
            <Descriptions.Item label={t('devices.label_device_type')}>
              <Tag>{TYPE_LABEL_MAP[device.device_type] || device.device_type}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t('devices.label_status')}>
              <Tag color={STATUS_COLOR_MAP[displayStatus]}>{STATUS_LABEL_MAP[displayStatus]}</Tag>
            </Descriptions.Item>
            {device.adb_serial && (
              <Descriptions.Item label={t('devices.label_adb_address')}>{device.adb_serial}</Descriptions.Item>
            )}
            <Descriptions.Item label={t('devices.label_resolution')}>
              {device.resolution_width && device.resolution_height
                ? `${device.resolution_width} × ${device.resolution_height}`
                : '-'}
            </Descriptions.Item>
            <Descriptions.Item label={t('devices.label_screenshot_latency')}>
              {typeof device.device_stats?.screenshot_latency_avg_ms === 'number'
                ? `${device.device_stats.screenshot_latency_avg_ms.toFixed(0)}ms`
                : (device.screenshot_fps ?? 0) > 0
                  ? `${(1000 / (device.screenshot_fps as number)).toFixed(0)}ms`
                  : t('devices.value_not_collected')}
            </Descriptions.Item>
            <Descriptions.Item label={t('devices.label_control_mode')}>
              {/* spec-29j Phase 2d: `control_mode` is optional in schema — default to 'auto' (the
                  backend default per Device.CONTROL_MODE_DEFAULTS) when missing. */}
              <Tag color={getControlModeColor((device.control_mode ?? 'auto') as ControlMode)}>
                {t(`devices.control_mode_${device.control_mode ?? 'auto'}`)}
              </Tag>
            </Descriptions.Item>
            {device.screenshot_method &&
              device.screenshot_method !==
                CONTROL_MODE_DEFAULTS[(device.control_mode ?? 'auto') as ControlMode]?.screenshot && (
                <Descriptions.Item label={t('devices.label_screenshot_method')}>
                  <Tag color="cyan">{device.screenshot_method}</Tag>
                </Descriptions.Item>
              )}
            {device.input_method &&
              device.input_method !== CONTROL_MODE_DEFAULTS[(device.control_mode ?? 'auto') as ControlMode]?.input && (
                <Descriptions.Item label={t('devices.label_input_method')}>
                  <Tag>{device.input_method}</Tag>
                </Descriptions.Item>
              )}
            {device.locked_by_username && (
              <Descriptions.Item label={t('devices.label_locked_by')}>
                <Tag color="purple">🔒 {device.locked_by_username}</Tag>
              </Descriptions.Item>
            )}
          </Descriptions>

          <Divider />

          <Typography.Title level={5} className="gaf-section-title">
            {t('devices.section_agent_info')}
          </Typography.Title>
          {device.agent_info ? (
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label={t('devices.label_agent_id')}>{device.agent_info.agent_id}</Descriptions.Item>
              <Descriptions.Item label={t('devices.label_hostname')}>{device.agent_info.hostname}</Descriptions.Item>
              <Descriptions.Item label={t('devices.label_ip_address')}>
                {device.agent_info.ip_address}
              </Descriptions.Item>
              <Descriptions.Item label={t('devices.label_agent_status')}>
                <Tag color={STATUS_COLOR_MAP[device.agent_info.status] || 'default'}>
                  {STATUS_LABEL_MAP[device.agent_info.status] || device.agent_info.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('devices.label_last_heartbeat')}>
                {device.agent_info.last_heartbeat ? new Date(device.agent_info.last_heartbeat).toLocaleString() : '-'}
              </Descriptions.Item>
            </Descriptions>
          ) : (
            <Typography.Text type="secondary">{t('devices.agent_not_connected')}</Typography.Text>
          )}

          <Divider />

          <Typography.Title level={5} className="gaf-section-title">
            <ScheduleOutlined aria-hidden="true" /> {t('devices.section_device_stats')}
          </Typography.Title>
          {statEntries.length > 0 ? (
            <Descriptions column={1} size="small" bordered>
              {statEntries.map(([key, value]) => (
                <Descriptions.Item label={STAT_LABEL_MAP[key] || key} key={key}>
                  {formatStatValue(key, value)}
                </Descriptions.Item>
              ))}
            </Descriptions>
          ) : (
            <Typography.Text type="secondary">{t('devices.no_stats_data')}</Typography.Text>
          )}

          <Divider />

          <Typography.Title level={5} className="gaf-section-title">
            <InfoCircleOutlined aria-hidden="true" /> {t('devices.section_extra_info')}
          </Typography.Title>
          <Descriptions column={1} size="small" bordered>
            {device.system_version && (
              <Descriptions.Item label={t('devices.label_system_version')}>{device.system_version}</Descriptions.Item>
            )}
            {device.battery_level != null && device.battery_level >= 0 && (
              <Descriptions.Item label={t('devices.label_battery_level')}>
                <Tag color={device.battery_level > 20 ? 'green' : 'red'}>
                  <ThunderboltOutlined aria-hidden="true" /> {device.battery_level}%
                </Tag>
              </Descriptions.Item>
            )}
            {!device.system_version && !device.battery_level && (
              <Typography.Text type="secondary">{t('devices.no_extra_info')}</Typography.Text>
            )}
          </Descriptions>
        </div>
      </div>

      {device.game_profile && (
        <DispatchRoutineModal
          open={dispatchOpen}
          onClose={() => setDispatchOpen(false)}
          profileId={device.game_profile}
          device={device}
        />
      )}
    </Drawer>
  );
}

export default DeviceDetailPanel;
