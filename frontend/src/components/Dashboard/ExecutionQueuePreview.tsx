/**
 * ExecutionQueuePreview — today's scheduled + running executions preview.
 *
 * Compact list showing the next 5 scheduled / running items from
 * scheduler/today so the user can see what's queued at a glance.
 */
import { useState, useEffect, useCallback } from 'react';
import { Card, Tag, Spin, Empty, Typography, Space, theme as antTheme } from 'antd';
import { fetchTodaySchedule } from '@/api/scheduler';
import type { TodayScheduleResponse } from '@/types/models';
import { SCHEDULE_STATUS_META, resolveScheduleStatus } from './scheduleStatusMeta';

const { Text } = Typography;

function formatTime(isoStr: string): string {
  try {
    return new Date(isoStr).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  } catch {
    return isoStr;
  }
}

export function ExecutionQueuePreview() {
  const { token } = antTheme.useToken();
  const [items, setItems] = useState<TodayScheduleResponse['items'] | undefined>(undefined);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchTodaySchedule();
      setItems(res?.items || []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <Card title="执行队列预览" size="small">
        <div className="gaf-p-lg" style={{ textAlign: 'center' }}>
          <Spin />
        </div>
      </Card>
    );
  }

  const list = items || [];
  const preview = list.slice(0, 5);

  return (
    <Card
      title={
        <Space>
          <Text strong>执行队列预览</Text>
          <Text type="secondary" className="gaf-text-xs">
            共 {list.length} 项
          </Text>
        </Space>
      }
      size="small"
    >
      {preview.length === 0 ? (
        <Empty description="今日无调度任务" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        // antd6 弃用 List — 迁移为原生 map 渲染, 复刻 List.Item 的分割线样式
        <div className="gaf-mt-sm">
          {preview.map((item) => {
            const meta = SCHEDULE_STATUS_META[resolveScheduleStatus(item.status)];
            return (
              <div
                key={`${item.device_name}-${item.task_chain_name}-${item.scheduled_time || ''}`}
                style={{ padding: '6px 0', borderBottom: `1px solid ${token.colorBorderSecondary}` }}
              >
                <Space>
                  <Text type="secondary" className="gaf-text-xs">
                    {item.scheduled_time ? formatTime(item.scheduled_time) : '—'}
                  </Text>
                  <Tag color={meta.tagColor} icon={meta.icon} style={{ fontSize: 10, lineHeight: '16px' }}>
                    {meta.label}
                  </Tag>
                  <Text className="gaf-text-sm">
                    {item.device_name}
                    {item.task_chain_name ? (
                      <>
                        {' '}
                        <Text type="secondary">→</Text>{' '}
                        {item.task_chain_name}
                      </>
                    ) : null}
                  </Text>
                </Space>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

export default ExecutionQueuePreview;
