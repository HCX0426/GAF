/**
 * ProgressRing — today execution progress ring widget.
 *
 * Displays today's execution count + success rate as a circular progress.
 * Backend: tasks/analytics/task-stats + tasks/dashboard-daily-report.
 */
import { useState, useEffect, useCallback } from 'react';
import { Card, Progress, Statistic, Row, Col, Spin, Empty, Typography, theme as antTheme } from 'antd';
import { CheckCircleOutlined } from '@ant-design/icons';
import { getDashboardDailyReport } from '@/api/tasks';

const { Text } = Typography;

interface ProgressData {
  today_executions: number;
  success_rate: number;
  completed: number;
  failed: number;
}

export function ProgressRing() {
  const { token } = antTheme.useToken();
  const [data, setData] = useState<ProgressData | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const report = await getDashboardDailyReport();
      const overview = report?.overview;
      if (!overview) {
        setData(null);
        return;
      }
      setData({
        today_executions: overview.total_executions || 0,
        success_rate: overview.success_rate || 0,
        completed: overview.success_count || 0,
        failed: overview.failed_count || 0,
      });
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <Card title="今日进度" size="small">
        <div className="gaf-p-lg" style={{ textAlign: 'center' }}>
          <Spin />
        </div>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card title="今日进度" size="small">
        <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </Card>
    );
  }

  return (
    <Card title="今日进度" size="small">
      <Row gutter={[16, 16]} align="middle" justify="center">
        <Col xs={12} style={{ textAlign: 'center' }}>
          <Progress
            type="circle"
            percent={data.success_rate}
            size={100}
            strokeColor={data.success_rate >= 80 ? token.colorSuccess : token.colorWarning}
            format={(p) => `${p}%`}
          />
          <Text type="secondary" className="gaf-text-xs gaf-mt-xs" style={{ display: 'block' }}>
            成功率
          </Text>
        </Col>
        <Col xs={12}>
          <Statistic
            title="今日执行"
            value={data.today_executions}
            prefix={
              <span aria-hidden="true">
                <CheckCircleOutlined />
              </span>
            }
          />
          <div className="gaf-mt-sm">
            <Text type="success" className="gaf-text-sm">
              成功 {data.completed}
            </Text>
            <Text type="secondary" className="gaf-text-sm gaf-ml-md">
              失败 {data.failed}
            </Text>
          </div>
        </Col>
      </Row>
    </Card>
  );
}

export default ProgressRing;
