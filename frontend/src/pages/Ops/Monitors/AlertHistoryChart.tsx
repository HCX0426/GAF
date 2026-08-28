import { useEffect, useState, useCallback } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Card, Spin, Empty, Segmented, theme } from 'antd';
import type { GlobalToken } from 'antd/es/theme/interface';
import { fetchAlertHistory as fetchAlertHistoryRaw } from '@/api/monitors';
import { useTranslation } from '@/i18n';

/** alert history single day data structure */
interface AlertHistoryDay {
  date: string;
  critical: number;
  warning: number;
  info: number;
  resolved: number;
}

/** API return alert history data structure */
interface AlertHistoryResponse {
  results: AlertHistoryDay[];
}

/** time range option */
type TimeRange = 7 | 14 | 30;

/** auto refresh interval (ms) */
const REFRESH_INTERVAL = 60_000;

/** map alert severity to its chart color using design tokens */
function getAlertColors(token: GlobalToken): { critical: string; warning: string; info: string; resolved: string } {
  return {
    critical: token.colorError,
    warning: token.colorWarning,
    info: token.colorPrimary,
    resolved: token.colorSuccess,
  };
}

/**
 * format ISO date string to MM/DD display
 * @param isoDate ISO format date string (YYYY-MM-DD)
 * @returns MM/DD format string
 */
function formatDateLabel(isoDate: string): string {
  const d = new Date(isoDate);
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${month}/${day}`;
}

/**
 * custom Tooltip content render
 * show each alert level detail value summary
 */
function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value: number; name: string; color: string; payload: Record<string, unknown> }>;
  label?: string;
}) {
  const t = useTranslation();
  const { token } = theme.useToken();
  if (!active || !payload || payload.length === 0) return null;

  /** calculate when daily alert total count */
  const total = payload.reduce((sum, entry) => sum + (entry.value as number), 0);

  return (
    <div
      className="gaf-text-xs gaf-radius-md"
      style={{
        background: token.colorBgContainer,
        border: `1px solid ${token.colorBorder}`,
        padding: '10px 14px',
        boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
        minWidth: 140,
      }}
    >
      <div
        className="gaf-font-semibold"
        style={{ marginBottom: 6, borderBottom: `1px solid ${token.colorBorderSecondary}`, paddingBottom: 4 }}
      >
        {label}
      </div>
      {payload.map((entry) => (
        <div key={entry.name} className="gaf-flex-between gaf-gap-lg gaf-mt-xs">
          <span>
            <span
              style={{
                display: 'inline-block',
                width: 8,
                height: 8,
                borderRadius: 2,
                background: entry.color,
                marginRight: 6,
                verticalAlign: 'middle',
              }}
            />
            {entry.name}
          </span>
          <span className="gaf-font-medium">{entry.value as number}</span>
        </div>
      ))}
      <div
        className="gaf-flex-between"
        style={{ marginTop: 6, paddingTop: 4, borderTop: `1px dashed ${token.colorBorder}` }}
      >
        <span className="gaf-font-semibold">{t('monitors.alert_history_total')}</span>
        <span className="gaf-font-semibold">{total}</span>
      </div>
    </div>
  );
}

/**
 * alert history trend chart component
 *
 * use Recharts BarChart stack stacked bar chart show most recent N day alert trend:
 * - critical( red #ff4d4f)— severity alert
 * - warning( orange #faad14)— warning alert
 * - info( blue #1890ff)— info alert
 * - resolved( green #52c41a)— resolved alert
 *
 * top provides Segmented switch device supports 7 day /14 day /30 day time range switch.
 * X-axis shows MM/DD format dates,
 * Tooltip show detail value and total.
 * every 60 seconds auto poll refresh data.
 * show empty state prompt when no data.
 */
export function AlertHistoryChart() {
  const t = useTranslation();
  const { token } = theme.useToken();
  const colors = getAlertColors(token);
  const [data, setData] = useState<AlertHistoryDay[]>([]);
  const [loading, setLoading] = useState(true);
  const [range, setRange] = useState<TimeRange>(7);

  /**
   * from after end get specified day range alert history data
   * @param days query day range
   * @returns alert history data array, fail when return empty array
   */
  const loadAlertHistory = useCallback(async (days: TimeRange): Promise<AlertHistoryDay[]> => {
    try {
      const data = (await fetchAlertHistoryRaw(days)) as unknown as AlertHistoryResponse;
      return data.results ?? [];
    } catch {
      return [];
    }
  }, []);

  /**
   * load alert history data and update status
   * use useCallback to avoid reference changes when timer is rebuilt
   */
  const loadData = useCallback(async () => {
    setLoading(true);
    const result = await loadAlertHistory(range);
    setData(result);
    setLoading(false);
  }, [range]);

  /**
   * component mount when first load, after every 60 seconds auto refresh;
   * switch time range when re- load; unmount when clear fixed when device
   */
  useEffect(() => {
    loadData();
    const timer = setInterval(loadData, REFRESH_INTERVAL);
    return () => clearInterval(timer);
  }, [loadData]);

  /**
   * handle time range switch event
   * @param value new select in time range value
   */
  const handleRangeChange = (value: string | number) => {
    setRange(value as TimeRange);
  };

  return (
    <Card
      title={t('monitors.alert_history_title')}
      size="small"
      extra={
        <Segmented
          value={range}
          options={[
            { label: t('monitors.range_7days'), value: 7 },
            { label: t('monitors.range_14days'), value: 14 },
            { label: t('monitors.range_30days'), value: 30 },
          ]}
          onChange={handleRangeChange}
          size="small"
        />
      }
    >
      <Spin spinning={loading}>
        {data.length === 0 && !loading ? (
          <Empty description={t('monitors.empty_alert_history')} />
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={token.colorBorderSecondary} />
              <XAxis
                dataKey="date"
                tickFormatter={formatDateLabel}
                tick={{ fontSize: 12 }}
                axisLine={{ stroke: token.colorBorder }}
                tickLine={{ stroke: token.colorBorder }}
              />
              <YAxis
                tick={{ fontSize: 12 }}
                axisLine={{ stroke: token.colorBorder }}
                tickLine={{ stroke: token.colorBorder }}
                allowDecimals={false}
              />
              <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
              <Legend iconType="square" wrapperStyle={{ fontSize: 12 }} />
              <Bar
                dataKey="critical"
                name={t('monitors.alert_level_critical')}
                stackId="alerts"
                fill={colors.critical}
                radius={[0, 0, 0, 0]}
              />
              <Bar
                dataKey="warning"
                name={t('monitors.alert_level_warning')}
                stackId="alerts"
                fill={colors.warning}
                radius={[0, 0, 0, 0]}
              />
              <Bar
                dataKey="info"
                name={t('monitors.alert_level_info')}
                stackId="alerts"
                fill={colors.info}
                radius={[0, 0, 0, 0]}
              />
              <Bar
                dataKey="resolved"
                name={t('monitors.alert_level_resolved')}
                stackId="alerts"
                fill={colors.resolved}
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        )}
      </Spin>
    </Card>
  );
}

export default AlertHistoryChart;
