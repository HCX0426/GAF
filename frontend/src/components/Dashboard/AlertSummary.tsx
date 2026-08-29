/**
 * AlertSummary — recent monitor events / alerts summary.
 *
 * Lists the latest 5 monitor events with severity tag so the user can see
 * recent alerts at a glance. Backend: /monitors/monitor-events/.
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import { Card, Tag, Spin, Empty, Typography, Space, Button, theme as antTheme } from 'antd';
import { WarningOutlined, BellOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { fetchMonitorEvents } from '@/api/monitors';
import type { MonitorEvent, MonitorEventSeverity, PaginatedResponse } from '@/types/models';
import { formatDateHM } from '@/utils/formatTime';

const { Text } = Typography;

const SEVERITY_COLOR: Record<MonitorEventSeverity, string> = {
  P0: 'red',
  P1: 'volcano',
  P2: 'orange',
  P3: 'gold',
};

export function AlertSummary() {
  const { token } = antTheme.useToken();
  const [events, setEvents] = useState<MonitorEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    try {
      const res: PaginatedResponse<MonitorEvent> = await fetchMonitorEvents({
        page_size: 5,
        signal: controller.signal,
      });
      setEvents(res?.results || []);
    } catch (err: unknown) {
      if ((err as Error)?.name === 'AbortError') return;
      setEvents([]);
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
      <Card title="告警摘要" size="small">
        <div className="gaf-p-lg" style={{ textAlign: 'center' }}>
          <Spin />
        </div>
      </Card>
    );
  }

  return (
    <Card
      title={
        <Space>
          <WarningOutlined />
          <Text strong>告警摘要</Text>
          {events.length > 0 && (
            <Text type="secondary" className="gaf-text-xs">
              最近 {events.length} 条
            </Text>
          )}
        </Space>
      }
      size="small"
      extra={
        <Button size="small" type="link" onClick={() => navigate('/ops/monitors')}>
          查看全部
        </Button>
      }
    >
      {events.length === 0 ? (
        <Empty description="无告警" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        // antd6 弃用 List — 迁移为原生 map 渲染, 复刻 List.Item 的分割线样式
        <div className="gaf-mt-sm">
          {events.map((event) => (
            <div
              key={event.id}
              style={{ padding: '6px 0', borderBottom: `1px solid ${token.colorBorderSecondary}` }}
            >
              <Space orientation="vertical" size={0} style={{ width: '100%' }}>
                <Space>
                  <Tag
                    color={(event.severity && SEVERITY_COLOR[event.severity]) || 'default'}
                    style={{ fontSize: 10, lineHeight: '16px' }}
                  >
                    {event.severity}
                  </Tag>
                  <Text className="gaf-text-sm">{event.event_type}</Text>
                  {!event.acknowledged_at && (
                    <Tag color="warning" style={{ fontSize: 10, lineHeight: '16px' }}>
                      未确认
                    </Tag>
                  )}
                </Space>
                <Text type="secondary" className="gaf-text-xs">
                  <BellOutlined /> {formatDateHM(event.created_at)}
                </Text>
              </Space>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export default AlertSummary;
