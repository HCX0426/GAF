/**
 * TrendChart — 7-day execution trend chart.
 *
 * Renders a recharts LineChart showing total / success / failed execution
 * counts over the past 7 days. Backend: /analytics/trend/.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { Card, Spin, Empty, Typography, theme as antTheme } from 'antd';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { fetchAnalyticsTrend, type TrendItem } from '@/api/ops';

const { Text } = Typography;

function formatDay(isoStr: string): string {
  try {
    return new Date(isoStr).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
  } catch {
    return isoStr;
  }
}

export function TrendChart() {
  const { token } = antTheme.useToken();
  const [data, setData] = useState<TrendItem[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchAnalyticsTrend();
      setData(res || []);
    } catch {
      setData([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const chartData = useMemo(
    // Backend returns execution_count + success_rate (percent); derive
    // success/failed counts for display.
    () =>
      data.map((item) => {
        const count = Number.isFinite(item.execution_count) ? item.execution_count : 0;
        const success = Math.round((count * (Number.isFinite(item.success_rate) ? item.success_rate : 0)) / 100);
        return {
          date: formatDay(item.date),
          total: count,
          success,
          failed: count - success,
        };
      }),
    [data],
  );

  return (
    <Card title="执行趋势 (近 7 天)" size="small">
      {loading ? (
        <div className="gaf-p-xl" style={{ textAlign: 'center' }}>
          <Spin />
        </div>
      ) : chartData.length === 0 ? (
        <Empty description="暂无趋势数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <div style={{ width: '100%', height: 220 }}>
          <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
            <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={token.colorBorderSecondary} />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line
                type="monotone"
                dataKey="total"
                name="总数"
                stroke={token.colorPrimary}
                strokeWidth={2}
                dot={{ r: 3 }}
              />
              <Line
                type="monotone"
                dataKey="success"
                name="成功"
                stroke={token.colorSuccess}
                strokeWidth={2}
                dot={{ r: 3 }}
              />
              <Line
                type="monotone"
                dataKey="failed"
                name="失败"
                stroke={token.colorError}
                strokeWidth={2}
                dot={{ r: 3 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <Text type="secondary" className="gaf-text-xs" style={{ display: 'block', marginTop: 4 }}>
        数据来源: /analytics/trend/
      </Text>
    </Card>
  );
}

export default TrendChart;
