/**
 * HeaderStatusIndicator — Header status light
 *
 * in Header right show system overall running row status indicator light ( three-color dot + pulse animation ),
 * click expand Popover floating layer show detail info,WebSocket real-time update.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { Popover, Typography, Space, Spin, theme as antTheme } from 'antd';
import { fetchSystemStatus } from '@/api/misc';
import { useAuthStore } from '@/stores/useAuthStore';
import { classifyError } from '@/utils/errorHandler';
import { CheckCircleFilled, ExclamationCircleFilled, CloseCircleFilled, MinusCircleFilled } from '@ant-design/icons';

const { Text } = Typography;

interface StatusMessage {
  id: number;
  timestamp: string;
  type: 'warning' | 'error';
  source: string;
  message: string;
}

interface SystemStatus {
  overall: 'running' | 'warning' | 'error' | 'idle';
  devicesOnline: number | null;
  devicesIdle: number | null;
  devicesTotal: number | null;
  activeExecutions: number | null;
  todayCompleted: number | null;
  unattendedActive: boolean;
  recentWarnings: StatusMessage[];
  recentErrors: StatusMessage[];
  agentError?: string;
  taskError?: string;
  updatedAt: string;
}

const STATUS_STYLE: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
  running: {
    color: '#52c41a',
    icon: <CheckCircleFilled className="gaf-text-sm" style={{ color: '#52c41a' }} />,
    label: '运行中',
  },
  warning: {
    color: '#faad14',
    icon: <ExclamationCircleFilled className="gaf-text-sm" style={{ color: '#faad14' }} />,
    label: '有警告',
  },
  error: {
    color: '#ff4d4f',
    icon: <CloseCircleFilled className="gaf-text-sm" style={{ color: '#ff4d4f' }} />,
    label: '异常',
  },
  idle: {
    color: '#bfbfbf',
    icon: <MinusCircleFilled className="gaf-text-sm" style={{ color: '#bfbfbf' }} />,
    label: '未启动',
  },
};

function formatTimeStr(isoStr: string): string {
  try {
    return new Date(isoStr).toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return isoStr;
  }
}

export function HeaderStatusIndicator() {
  const { token } = antTheme.useToken();
  const { isAuthenticated } = useAuthStore();
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);

  /** get system status — only login after execute */
  const fetchStatus = useCallback(
    async (signal?: AbortSignal) => {
      if (!isAuthenticated) {
        setLoading(false);
        setStatus(null);
        return;
      }
      try {
        const data = await fetchSystemStatus<SystemStatus>(signal);
        if (!signal?.aborted) {
          setStatus(data);
        }
      } catch (err: unknown) {
        const classified = classifyError(err);
        const status429 =
          (err as { response?: { status?: number } })?.response?.status === 429;
        // M2 fix (2026-08-28): 429 限流是全局 user:300/min 高频下的偶发保护，
        // 静默忽略避免 console 每次刷屏；其余错误保留告警。
        if (
          !status429 &&
          classified.originalError instanceof Error &&
          classified.originalError.name !== 'AbortError' &&
          !(err instanceof Error && err.name === 'CanceledError')
        ) {
          console.error('System status fetch failed:', err);
        }
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [isAuthenticated],
  );

  /** current abort controller ref for cleanup */
  const statusControllerRef = useRef<AbortController | null>(null);
  /** skip StrictMode test mount to avoid spurious ERR_ABORTED */
  const isRealMountRef = useRef(false);

  useEffect(() => {
    if (!isRealMountRef.current) {
      isRealMountRef.current = true;
      return;
    }
    if (!isAuthenticated) return;
    statusControllerRef.current = new AbortController();
    fetchStatus(statusControllerRef.current.signal);
    const interval = setInterval(() => {
      statusControllerRef.current?.abort();
      statusControllerRef.current = new AbortController();
      fetchStatus(statusControllerRef.current.signal);
    }, 30000);
    return () => {
      clearInterval(interval);
      statusControllerRef.current?.abort();
      statusControllerRef.current = null;
    };
  }, [fetchStatus, isAuthenticated]);

  if (loading) {
    return (
      <Spin size="small">
        <div style={{ width: 14, height: 14, borderRadius: '50%', background: token.colorTextTertiary }} />
      </Spin>
    );
  }

  const overall = status?.overall || 'idle';
  const style = STATUS_STYLE[overall] || STATUS_STYLE.idle;

  const popoverContent = (
    <div style={{ width: 280 }}>
      <Space orientation="vertical" size="small" className="gaf-w-full">
        <Text strong>
          {style.icon} 系统运行状态 — {style.label}
        </Text>

        <div>
          <Text type="secondary">设备在线：</Text>
          <Text strong>
            {status?.devicesOnline ?? '-'} / {status?.devicesTotal ?? '-'}
          </Text>
        </div>

        {(status?.agentError || status?.taskError) && (
          <div className="gaf-mt-sm gaf-py-sm gaf-px-md" style={{ background: token.colorErrorBg, borderRadius: 4 }}>
            <Text type="danger" strong className="gaf-text-sm">
              ⚠ 数据获取异常
            </Text>
            {status.agentError && (
              <div className="gaf-mt-xs gaf-text-xxs" style={{ color: token.colorError }}>
                {status.agentError}
              </div>
            )}
            {status.taskError && (
              <div className="gaf-mt-xs gaf-text-xxs" style={{ color: token.colorError }}>
                {status.taskError}
              </div>
            )}
          </div>
        )}

        <div>
          <Text type="secondary">当前执行中：</Text>
          <Text strong>{status?.activeExecutions ?? 0} 个任务</Text>
        </div>

        <div>
          <Text type="secondary">今日完成：</Text>
          <Text strong>{status?.todayCompleted ?? 0} 个任务</Text>
        </div>

        {status?.recentWarnings && status.recentWarnings.length > 0 && (
          <>
            <Text type="warning" strong>
              最近警告：
            </Text>
            {status.recentWarnings.slice(0, 3).map((w) => (
              <div key={w.id} className="gaf-text-sm" style={{ color: token.colorWarning }}>
                {formatTimeStr(w.timestamp)} [{w.source}] {w.message}
              </div>
            ))}
          </>
        )}

        {status?.recentErrors && status.recentErrors.length > 0 && (
          <>
            <Text type="danger" strong>
              最近错误：
            </Text>
            {status.recentErrors.slice(0, 3).map((e) => (
              <div key={e.id} className="gaf-text-sm" style={{ color: token.colorError }}>
                {formatTimeStr(e.timestamp)} [{e.source}] {e.message}
              </div>
            ))}
          </>
        )}

        <a href="/dashboard" className="gaf-text-sm">
          查看详情 →
        </a>
      </Space>
    </div>
  );

  return (
    <Popover content={popoverContent} trigger="click" placement="bottomRight">
      <div
        style={{
          width: 14,
          height: 14,
          borderRadius: '50%',
          background: style.color,
          cursor: 'pointer',
          display: 'inline-block',
          flexShrink: 0,
          animation: overall === 'running' ? 'pulse-status 2s ease-in-out infinite' : undefined,
        }}
        title={style.label}
      />
      <style>{`
        @keyframes pulse-status {
          0%, 100% { box-shadow: 0 0 0 0 rgba(82, 196, 26, 0.6); }
          50% { box-shadow: 0 0 0 6px rgba(82, 196, 26, 0); }
        }
      `}</style>
    </Popover>
  );
}

export default HeaderStatusIndicator;
