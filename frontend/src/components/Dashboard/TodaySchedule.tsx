/**
 * TodaySchedule — today task schedule
 *
 * Dashboard in today unattended execution schedule Timeline view.
 * shows tasks completed and pending today, supports 4 kinds status distinguish,
 * in-progress items pulse animation and progress percentage.
 */

import { useEffect, useState, useCallback, useRef } from 'react';
import { Card, Timeline, Tag, Typography, Progress, Space, Spin, Empty, theme as antTheme } from 'antd';
import type { TodayScheduleResponse, TodayScheduleItem } from '@/types/models';
import { fetchTodaySchedule } from '@/api/scheduler';
import { classifyError } from '@/utils/errorHandler';
import { SCHEDULE_STATUS_META, resolveScheduleStatus, tokenColorForStatus } from './scheduleStatusMeta';
import { formatTimeHM } from '@/utils/formatTime';

const { Text } = Typography;

function getWeekDayStr(): string {
  const days = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  const today = new Date();
  const y = today.getFullYear();
  const m = String(today.getMonth() + 1).padStart(2, '0');
  const d = String(today.getDate()).padStart(2, '0');
  const w = days[today.getDay()];
  return `${y}年${m}月${d}日 ${w}`;
}

export function TodaySchedule() {
  const { token } = antTheme.useToken();
  const [data, setData] = useState<TodayScheduleResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    // Abort previous in-flight request
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);
    try {
      const res = await fetchTodaySchedule({ signal: controller.signal });
      setData(res);
    } catch (err: unknown) {
      // A cancelled request is not a real failure — it happens when a newer
      // load()/remount aborts the previous in-flight request (dev StrictMode
      // double-mount). axios surfaces signal aborts as CanceledError
      // (code 'ERR_CANCELED'), not the native DOMException AbortError, so
      // treat both as a silent no-op instead of showing "canceled".
      const errName = (err as Error | null)?.name;
      const errCode = (err as { code?: string } | null)?.code;
      if (errName === 'AbortError' || errCode === 'ERR_CANCELED' || errName === 'CanceledError') {
        return;
      }
      const classified = classifyError(err);
      setError(`加载今日日程失败：${classified.message}`);
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    load();
    return () => {
      abortRef.current?.abort();
      abortRef.current = null;
    };
  }, [load]);

  if (loading) {
    return (
      <Card title="今日日程" size="small">
        <div className="gaf-p-xl" style={{ textAlign: 'center' }}>
          <Spin />
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card title="今日日程" size="small">
        <Text type="danger">{error}</Text>
      </Card>
    );
  }

  const scheduleItems: TodayScheduleItem[] = data?.items || [];

  if (!data || scheduleItems.length === 0) {
    return (
      <Card title="今日日程" size="small">
        <Empty description="今日无调度任务" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </Card>
    );
  }

  const completedCount = scheduleItems.filter((i) => i.status === 'completed').length;

  return (
    <Card
      title={
        <Space>
          <Text strong>今日日程</Text>
          <Text type="secondary" className="gaf-text-xs">
            {getWeekDayStr()}
          </Text>
        </Space>
      }
      size="small"
    >
      <Timeline
        items={scheduleItems.map((item) => {
          const status = resolveScheduleStatus(item.status);
          const meta = SCHEDULE_STATUS_META[status];
          const color = tokenColorForStatus(token, status);
          return {
            icon: (
              <span style={{ color }}>
                {meta.icon}
              </span>
            ),
            color,
            content: (
              <div>
                <div className="gaf-flex-between gaf-mb-xs">
                  <Space size="small">
                    <Text className="gaf-text-xs" style={{ color: token.colorTextTertiary }}>
                      {item.scheduled_time ? formatTimeHM(item.scheduled_time) : '—'}
                    </Text>
                    <Tag color={color} style={{ fontSize: 10, lineHeight: '18px' }}>
                      {meta.label}
                    </Tag>
                  </Space>
                </div>
                <div style={{ marginBottom: 2 }}>
                  <Text>
                    {item.device_name || '未知设备'}
                    {item.account_name ? (
                      <>
                        <Text type="secondary"> → </Text>
                        {item.account_name}
                      </>
                    ) : null}
                    <Text type="secondary"> → </Text>
                    {item.task_chain_name || '未知任务链'}
                  </Text>
                </div>
                {item.status === 'running' && item.progress !== undefined && (
                  <Progress percent={item.progress} size="small" strokeColor={token.colorPrimary} className="gaf-m-0" />
                )}
                {item.status === 'failed' && item.error_message && (
                  <Text type="danger" className="gaf-text-xs">
                    错误：{item.error_message}
                  </Text>
                )}
              </div>
            ),
          };
        })}
      />

      <div className="gaf-mt-md">
        <div className="gaf-flex-between gaf-mb-xs">
          <Text type="secondary">
            已完成 {completedCount} / {scheduleItems.length} 项
          </Text>
        </div>
        <Progress
          percent={scheduleItems.length > 0 ? Math.round((completedCount / scheduleItems.length) * 100) : 0}
          strokeColor={token.colorSuccess}
          size="small"
        />
      </div>
    </Card>
  );
}

export default TodaySchedule;
