/**
 * InfraHealthPanel — base facility health panel
 *
 * from GET /api/v2/accounts/init/health/ get 8 item base facility check result,
 * with card + list form show every item status light, metric value and message.
 * supports every 10 seconds auto refresh and manual refresh, exception item show suggested operation Alert.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { API_PREFIX } from '@/config/app';
import { buildAuthHeaders } from '@/utils/tokenStore';
import { Card, Badge, Tag, Button, Alert, Statistic, Spin, Space, Row, Col, Typography } from 'antd';
import {
  DatabaseOutlined,
  CloudServerOutlined,
  ThunderboltOutlined,
  WifiOutlined,
  HddOutlined,
  MobileOutlined,
  TeamOutlined,
  ClockCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons';

const { Text } = Typography;

/** single item health check result */
interface HealthCheckItem {
  key: string;
  name: string;
  status: 'healthy' | 'warning' | 'critical';
  value: string;
  message: string;
  suggestion?: string;
}

/** health check API response structure */
interface HealthResponse {
  status: 'healthy' | 'warning' | 'critical';
  checks: HealthCheckItem[];
  timestamp: string;
}

/** status → color mapping */
const STATUS_COLOR_MAP: Record<string, string> = {
  healthy: '#52c41a',
  warning: '#faad14',
  critical: '#ff4d4f',
};

// F010 fix: map lookup replaces 3-level nested ternary for status display label
const STATUS_LABEL_MAP: Record<string, string> = {
  healthy: '正常',
  warning: '警告',
  critical: '严重',
};

/** status → text label color */
const STATUS_TAG_COLOR: Record<string, string> = {
  healthy: 'success',
  warning: 'warning',
  critical: 'error',
};

/** each check item to corresponding icon */
const CHECK_ICONS: Record<string, React.ReactNode> = {
  database: <DatabaseOutlined />,
  redis: <CloudServerOutlined />,
  celery: <ThunderboltOutlined />,
  websocket: <WifiOutlined />,
  disk: <HddOutlined />,
  memory: <MobileOutlined />,
  agent_online: <TeamOutlined />,
  celery_beat: <ClockCircleOutlined />,
};

/**
 * from after end get health check data
 * @returns health check response data,API unavailable when return null
 */
async function fetchHealthData(): Promise<HealthResponse | null> {
  try {
    // TD-304 fix (spec-63): 修 URL /api/system/health/ → /api/v2/accounts/init/health/ + 加 buildAuthHeaders
    const res = await fetch(`${API_PREFIX}/accounts/init/health/`, { headers: buildAuthHeaders() });
    if (res.ok) {
      const json = await res.json();
      // F7 fix (2026-08-28): 接口空态/字段缺失时返回 null，防止 data.checks.filter 崩溃
      if (!json || typeof json !== 'object' || !Array.isArray(json.checks)) {
        return null;
      }
      return json as HealthResponse;
    }
  } catch {
    // API unavailable when return null
  }
  return null;
}

export function InfraHealthPanel() {
  const [data, setData] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /** load health data */
  const loadHealth = useCallback(async () => {
    try {
      const result = await fetchHealthData();
      setData(result);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  /** first load + fixed when poll */
  useEffect(() => {
    loadHealth();
    // 30s polling (down from 10s). Infrastructure health (Redis/Celery/DB)
    // does not fluctuate sub-10s; manual refresh is available for on-demand.
    timerRef.current = setInterval(loadHealth, 30000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [loadHealth]);

  /** manual refresh */
  const handleManualRefresh = useCallback(() => {
    setRefreshing(true);
    loadHealth();
  }, [loadHealth]);

  if (loading) {
    return (
      <Card title="基础设施健康" size="small">
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin size="large" description="正在检测基础设施状态..." />
        </div>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card title="基础设施健康" size="small">
        <Alert type="error" title="无法获取健康检查数据" />
      </Card>
    );
  }

  const unhealthyItems = data.checks.filter((c) => c.status !== 'healthy');
  const healthyCount = data.checks.filter((c) => c.status === 'healthy').length;

  return (
    <Card
      title={
        <Space>
          <Text strong>基础设施健康</Text>
          <Badge
            count={`${healthyCount}/${data.checks.length}`}
            style={{ backgroundColor: STATUS_COLOR_MAP[data.status] }}
          />
        </Space>
      }
      size="small"
      extra={
        <Button
          icon={<ReloadOutlined spin={refreshing} />}
          size="small"
          onClick={handleManualRefresh}
          loading={refreshing}
        >
          刷新
        </Button>
      }
    >
      {/* 全局状态摘要 */}
      <Row gutter={[16, 16]} className="gaf-mb-lg">
        <Col span={8}>
          <Statistic
            title="总体状态"
            value={STATUS_LABEL_MAP[data.status] || '严重'}
            styles={{ content: { color: STATUS_COLOR_MAP[data.status] } }}
          />
        </Col>
        <Col span={8}>
          <Statistic
            title="健康项"
            value={healthyCount}
            suffix={`/ ${data.checks.length}`}
            styles={{ content: { color: '#52c41a' } }}
          />
        </Col>
        <Col span={8}>
          <Statistic
            title="异常项"
            value={unhealthyItems.length}
            styles={{ content: { color: unhealthyItems.length > 0 ? '#ff4d4f' : '#52c41a' } }}
          />
        </Col>
      </Row>

      {/* 各项检查列表 */}
      <div>
        {data.checks.map((item) => {
          const color = STATUS_COLOR_MAP[item.status];
          return (
            <div
              key={item.key}
              className="gaf-mb-sm gaf-py-sm gaf-px-md"
              style={{
                borderLeft: `4px solid ${color}`,
                paddingLeft: 12,
                backgroundColor: item.status !== 'healthy' ? '#fff7e6' : undefined,
                borderRadius: 4,
              }}
            >
              <div className="gaf-w-full">
                <div className="gaf-flex-center gaf-gap-sm gaf-mb-xs">
                  <span className="gaf-text-lg" style={{ color }}>
                    {CHECK_ICONS[item.key]}
                  </span>
                  <Text strong>{item.name}</Text>
                  <Tag color={STATUS_TAG_COLOR[item.status]}>{item.status.toUpperCase()}</Tag>
                  <Text type="secondary" style={{ marginLeft: 'auto' }}>
                    {item.value}
                  </Text>
                </div>
                <Text type="secondary" style={{ fontSize: 13 }}>
                  {item.message}
                </Text>
              </div>
            </div>
          );
        })}
      </div>

      {/* 异常项建议操作 */}
      {unhealthyItems.length > 0 && (
        <Alert
          type="warning"
          showIcon
          className="gaf-mt-lg"
          title={`发现 ${unhealthyItems.length} 项异常`}
          description={
            <div>
              {unhealthyItems.map((item) => (
                <div key={item.key} className="gaf-mb-xs">
                  <Text strong style={{ color: STATUS_COLOR_MAP[item.status] }}>
                    {item.name}
                  </Text>
                  ：{item.suggestion || item.message}
                </div>
              ))}
            </div>
          }
        />
      )}

      <Text type="secondary" className="gaf-text-xxs gaf-mt-sm" style={{ display: 'block', textAlign: 'right' }}>
        最后更新：{new Date(data.timestamp).toLocaleString('zh-CN')} · 每 10 秒自动刷新
      </Text>
    </Card>
  );
}

export default InfraHealthPanel;
