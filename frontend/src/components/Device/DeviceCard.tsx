/**
 * device card component
 * shows Device basic info, status indicator, screenshot thumbnail, lock status, click to enter details
 */
import { useEffect, useRef } from 'react';
import { Card, Tag, Typography, Space, Tooltip } from 'antd';
import { DesktopOutlined, MobileOutlined, ThunderboltOutlined, LockOutlined } from '@ant-design/icons';
import type { Device, DeviceStatus, DeviceType } from '@/types/models';

/** DeviceCard component props */
interface DeviceCardProps {
  device: Device;
  onSelect?: (device: Device) => void;
  onTestScreenshot?: (device: Device) => void;
  selected?: boolean;
  /** WebSocket screenshot frame base64 */
  screenshotFrame?: string | null;
}

/** device status color mapping */
const STATUS_COLOR_MAP: Record<DeviceStatus, string> = {
  online: '#52c41a',
  offline: '#d9d9d9',
  busy: '#faad14',
  error: '#ff4d4f',
  locked: '#722ed1',
};

// F010 fix: helper function replaces 3-level nested ternary for animation name
function getDeviceAnimation(isOnline: boolean, isError: boolean): string {
  if (isOnline) return 'pulse 2s infinite';
  if (isError) return 'blink 1s infinite';
  return 'none';
}

/** device status text mapping */
const STATUS_LABEL_MAP: Record<DeviceStatus, string> = {
  online: '在线',
  offline: '离线',
  busy: '忙碌',
  error: '错误',
  locked: '已锁定',
};

/** device type icon mapping */
const TYPE_ICON_MAP: Record<DeviceType, React.ReactNode> = {
  windows: <DesktopOutlined />,
  emulator: <MobileOutlined />,
};

const TYPE_LABEL_MAP: Record<DeviceType, string> = {
  windows: 'Windows',
  emulator: '模拟器',
};

/**
 * device info card
 * shows device name, type, status, resolution, frame rate, lock status, supports screenshot thumbnail and test screenshot entry
 */
export function DeviceCard({ device, onSelect, selected = false, screenshotFrame }: DeviceCardProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!screenshotFrame || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const img = new Image();
    img.onload = () => {
      canvas.width = img.width;
      canvas.height = img.height;
      ctx.drawImage(img, 0, 0);
    };
    // Auto-detect image format: JPEG starts with /9j/, PNG starts with iVBOR
    const mimeType = screenshotFrame.startsWith('/9j/') ? 'image/jpeg' : 'image/png';
    img.src = `data:${mimeType};base64,${screenshotFrame}`;
  }, [screenshotFrame]);

  const isLocked = device.locked_by_username != null;
  // spec-29j Phase 2d: `device.status` is optional in schema (`DeviceStatusEnum | undefined`).
  // Default to 'offline' when missing — backend always sends a status, but TS requires the guard.
  // 'locked' remains a frontend-only display state derived from `locked_by_username != null`.
  const displayStatus: DeviceStatus = isLocked ? 'locked' : (device.status ?? 'offline');
  const statusColor = STATUS_COLOR_MAP[displayStatus];
  const isOnline = (device.status ?? 'offline') !== 'offline';
  const isError = device.status === 'error';

  return (
    <Card
      size="small"
      hoverable
      style={{
        borderColor: selected ? '#1890ff' : statusColor,
        borderWidth: selected ? 2 : 1,
        opacity: device.status === 'offline' ? 0.6 : 1,
        transition: 'border-width 0.3s ease, opacity 0.3s ease, box-shadow 0.3s ease, background-color 0.3s ease',
      }}
      styles={{
        body: { padding: 'var(--spacing-md, 12px)' },
      }}
      onClick={() => onSelect?.(device)}
    >
      <Space orientation="vertical" className="gaf-w-full" size={4}>
        {/* 截图缩略图区 */}
        <div
          className="gaf-w-full"
          style={{
            height: 120,
            background: '#1a1a2e',
            borderRadius: 4,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            overflow: 'hidden',
            position: 'relative',
          }}
        >
          {screenshotFrame ? (
            <canvas
              ref={canvasRef}
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'contain',
                objectPosition: 'center center',
                display: 'block',
              }}
            />
          ) : (
            <ThunderboltOutlined style={{ fontSize: 32, color: '#434358' }} />
          )}
          {/* 状态指示灯 */}
          <span
            style={{
              position: 'absolute',
              top: 6,
              right: 6,
              width: 10,
              height: 10,
              borderRadius: '50%',
              background: statusColor,
              boxShadow: `0 0 6px ${statusColor}`,
              animation: getDeviceAnimation(isOnline, isError),
            }}
          />
          {/* R37-P1 C5: removed test-screenshot floating button.
              Screenshot testing now lives in TemplateAnnotationPage Tab 1
              (real-time stream + template-match panel) — see plan §C5. */}
        </div>

        {/* 设备信息 */}
        <Space>
          <Tooltip title={TYPE_LABEL_MAP[device.device_type]}>
            <span style={{ color: statusColor }}>{TYPE_ICON_MAP[device.device_type]}</span>
          </Tooltip>
          <Typography.Text strong ellipsis style={{ maxWidth: 100 }}>
            {device.name}
          </Typography.Text>
          {isLocked && (
            <Tooltip title={`已被 ${device.locked_by_username} 锁定`}>
              <LockOutlined className="gaf-text-xs" style={{ color: '#722ed1' }} />
            </Tooltip>
          )}
          <Tag color={statusColor} className="gaf-text-xxs" style={{ marginLeft: 'auto' }}>
            {STATUS_LABEL_MAP[displayStatus]}
          </Tag>
          {/* R37-P1: show game_profile Tag if device is bound to a GameProfile */}
          {device.game_profile_detail?.game_name && (
            <Tag color="purple" className="gaf-text-xxs">
              {device.game_profile_detail.game_name}
            </Tag>
          )}
        </Space>

        {/* 分辨率与截图延迟 / 帧率 */}
        <Typography.Text type="secondary" className="gaf-text-xxs">
          {device.resolution_width && device.resolution_height
            ? `${device.resolution_width}×${device.resolution_height}`
            : '未知分辨率'}
          {typeof device.device_stats?.screenshot_latency_avg_ms === 'number'
            ? ` · ${device.device_stats.screenshot_latency_avg_ms.toFixed(0)}ms`
            : (device.screenshot_fps ?? 0) > 0
              ? ` · ${(1000 / (device.screenshot_fps as number)).toFixed(0)}ms`
              : null}
          {typeof (device.extra_info as Record<string, unknown> | null | undefined)?.dpi === 'number' &&
            ` · ${(device.extra_info as Record<string, unknown>).dpi} DPI`}
        </Typography.Text>

        {/* 最后活跃时间 */}
        {device.updated_at && (
          <Typography.Text type="secondary" className="gaf-text-xxs">
            最后活跃：{new Date(device.updated_at).toLocaleString()}
          </Typography.Text>
        )}
      </Space>

      {/* CSS 动画：在线脉冲、错误闪烁 */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.2; }
        }
      `}</style>
    </Card>
  );
}

export default DeviceCard;
