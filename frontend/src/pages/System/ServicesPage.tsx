/**
 * Services Management page (系统页签) — 监控各服务健康/进程/报错 + 统一查看终端日志.
 *
 * spec 2026-08-29-services-management-monitor P4.
 * - 服务状态卡片: redis / backend / agent / frontend / daemon
 * - 15s 自动轮询; 每服务可打开日志 Drawer (tail + ERROR 过滤 + 高亮)
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Drawer,
  Empty,
  Row,
  Select,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
  theme,
} from 'antd';
import {
  CheckCircleFilled,
  CloseCircleFilled,
  EyeOutlined,
  ReloadOutlined,
  MinusCircleFilled,
} from '@ant-design/icons';
import {
  fetchServiceLogs,
  fetchSystemServices,
  type ServiceInfo,
  type SystemServicesResponse,
} from '@/api/services';
import { useTranslation } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';

const { Text } = Typography;
const POLL_MS = 15_000;

/** 报错行前置正则 (与 backend/scripts 语义一致, 仅用于前端高亮). */
const ERROR_RE = /\b(ERROR|CRITICAL|FATAL)\b|Traceback \(most recent call last\)|(?:Exception|Error)[:(]/;

function isErrorLine(line: string): boolean {
  return ERROR_RE.test(line);
}

/** 服务健康灯颜色: null=未知(灰), true=绿, false=红. */
function HealthDot({ healthy }: { healthy: boolean | null }) {
  const { token } = theme.useToken();
  if (healthy === null) {
    return <MinusCircleFilled style={{ color: token.colorTextTertiary, fontSize: 16 }} />;
  }
  return healthy ? (
    <CheckCircleFilled style={{ color: '#52c41a', fontSize: 16 }} />
  ) : (
    <CloseCircleFilled style={{ color: '#ff4d4f', fontSize: 16 }} />
  );
}

export function ServicesPage() {
  const t = useTranslation();
  const { token } = theme.useToken();

  const [status, setStatus] = useState<SystemServicesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [logService, setLogService] = useState<ServiceInfo | null>(null);
  const [logFilter, setLogFilter] = useState<'all' | 'error'>('all');
  const [logLines, setLogLines] = useState<string[]>([]);
  const [logPath, setLogPath] = useState<string | null>(null);
  const [logLoading, setLogLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchSystemServices();
      setStatus(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  const loadLogs = useCallback(
    async (service: ServiceInfo, filter: 'all' | 'error' = logFilter) => {
      setLogLoading(true);
      try {
        const data = await fetchServiceLogs({ service: service.name, lines: 400, filter });
        setLogLines(data.lines);
        setLogPath(data.path);
      } catch (e) {
        setLogLines([]);
        setLogPath(null);
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLogLoading(false);
      }
    },
    [logFilter],
  );

  const openLogDrawer = (service: ServiceInfo) => {
    setLogService(service);
    setLogFilter('all');
    setLogLines([]);
    setLogPath(null);
    void loadLogs(service, 'all');
  };

  const switchFilter = (filter: 'all' | 'error') => {
    setLogFilter(filter);
    if (logService) void loadLogs(logService, filter);
  };

  const services = useMemo(() => status?.services ?? [], [status]);
  const totalErrors = useMemo(
    () => services.reduce((sum, s) => sum + (s.error_count ?? 0), 0),
    [services],
  );
  const unhealthyCount = useMemo(
    () => services.filter((s) => (s.healthy ?? true) === false).length,
    [services],
  );
  const daemonRunning = status?.daemon?.running ?? false;

  const overallTag = !status ? (
    <Tag>—</Tag>
  ) : unhealthyCount > 0 ? (
    <Tag color="red">{t('servicesManage.overall_error', { count: unhealthyCount })}</Tag>
  ) : totalErrors > 0 ? (
    <Tag color="orange">{t('servicesManage.overall_warning', { count: totalErrors })}</Tag>
  ) : (
    <Tag color="green">{t('servicesManage.overall_healthy')}</Tag>
  );

  return (
    <PageWrapper title={t('servicesManage.page_title')}>
      <Space wrap style={{ marginBottom: 16 }}>
        {daemonRunning ? (
          <Tag color="green" icon={<CheckCircleFilled />}>
            {t('servicesManage.daemon_running', { pid: status?.daemon?.pid ?? '' })}
          </Tag>
        ) : (
          <Tag color="default" icon={<MinusCircleFilled />}>
            {t('servicesManage.daemon_stopped')}
          </Tag>
        )}
        {overallTag}
        <Text type="secondary" style={{ fontSize: 12 }}>
          {status?.updatedAt ? `更新于 ${status.updatedAt}` : ''}
        </Text>
        <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={() => load()}>
          {t('servicesManage.btn_refresh')}
        </Button>
      </Space>

      {!daemonRunning && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          title={t('servicesManage.daemon_hint')}
        />
      )}
      {error && !loading && (
        <Alert type="error" showIcon style={{ marginBottom: 16 }} title={error} />
      )}

      {loading && services.length === 0 ? (
        <Spin style={{ display: 'block', margin: '48px auto', textAlign: 'center' }} />
      ) : (
        <Row gutter={[16, 16]}>
          {services.map((svc) => (
            <Col key={svc.name} xs={24} sm={12} md={8} lg={8} xl={8}>
              <ServiceCard svc={svc} onViewLog={openLogDrawer} />
            </Col>
          ))}
        </Row>
      )}

      <Drawer
        title={
          <Space>
            <Text strong>{t('servicesManage.logs_title')}</Text>
            <Text code>{logService?.name}</Text>
            {logPath && <Text type="secondary" style={{ fontSize: 12 }}>{logPath}</Text>}
          </Space>
        }
        open={logService !== null}
        onClose={() => setLogService(null)}
        size="large"
        destroyOnHidden
      >
        <Space style={{ marginBottom: 12 }}>
          <Select
            size="small"
            value={logFilter}
            style={{ width: 140 }}
            onChange={switchFilter}
            options={[
              { value: 'all', label: t('servicesManage.filter_all') },
              { value: 'error', label: t('servicesManage.filter_error') },
            ]}
          />
          <Button
            size="small"
            icon={<ReloadOutlined />}
            loading={logLoading}
            onClick={() => logService && void loadLogs(logService, logFilter)}
          >
            {t('servicesManage.btn_refresh')}
          </Button>
          {logFilter === 'error' && logLines.length === 0 && logLoading === false && (
            <Tag color="green">{t('servicesManage.no_errors')}</Tag>
          )}
        </Space>

        {logLoading ? (
          <Spin />
        ) : logLines.length === 0 ? (
          <Empty description={t('servicesManage.no_logs')} />
        ) : (
          <div
            style={{
              background: token.colorBgLayout,
              borderRadius: 8,
              padding: 12,
              maxHeight: '70vh',
              overflow: 'auto',
              fontFamily: "'Consolas', 'Courier New', monospace",
              fontSize: 12,
              lineHeight: 1.6,
            }}
          >
            {logLines.map((line, idx) => (
              <div
                key={idx}
                style={{
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-all',
                  color: isErrorLine(line) ? token.colorError : token.colorText,
                }}
              >
                {line || ' '}
              </div>
            ))}
          </div>
        )}
      </Drawer>
    </PageWrapper>
  );
}

interface ServiceCardProps {
  svc: ServiceInfo;
  onViewLog: (svc: ServiceInfo) => void;
}

/** 单服务状态卡片 */
function ServiceCard({ svc, onViewLog }: ServiceCardProps) {
  const t = useTranslation();
  const { token } = theme.useToken();
  const hasErrors = (svc.error_count ?? 0) > 0;

  const metaItems: Array<{ label: string; value: string }> = [
    { label: t('servicesManage.meta_status'), value: svc.running === null ? '—' : svc.running ? t('servicesManage.meta_running') : t('servicesManage.meta_stopped') },
    { label: t('servicesManage.meta_pid'), value: svc.pid?.toString() ?? '—' },
    { label: t('servicesManage.meta_port'), value: svc.port?.toString() ?? '—' },
    { label: t('servicesManage.meta_restarts'), value: (svc.restart_count ?? 0).toString() },
  ];

  return (
    <Card
      size="small"
      styles={{ body: { padding: 14 } }}
      title={
        <Space>
          <HealthDot healthy={svc.healthy} />
          <Text strong style={{ textTransform: 'uppercase' }}>{svc.name}</Text>
        </Space>
      }
      extra={
        hasErrors ? (
          <Tag color="red">{t('servicesManage.err_count', { count: svc.error_count ?? 0 })}</Tag>
        ) : null
      }
    >
      <Text
        type="secondary"
        style={{ fontSize: 12, display: 'block', marginBottom: 8, minHeight: 36 }}
      >
        {svc.detail || t('servicesManage.no_detail')}
      </Text>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '4px 12px', marginBottom: 12 }}>
        {metaItems.map((item) => (
          <div key={item.label} style={{ fontSize: 12 }}>
            <Text type="secondary">{item.label}: </Text>
            <Text>{item.value}</Text>
          </div>
        ))}
      </div>

      {hasErrors && svc.latest_error && (
        <div
          style={{
            background: token.colorErrorBg,
            borderRadius: 4,
            padding: '4px 8px',
            fontSize: 12,
            color: token.colorError,
            marginBottom: 12,
          }}
          title={svc.latest_error}
        >
          {svc.latest_error}
        </div>
      )}

      <Tooltip title={t('servicesManage.view_log_tip')}>
        <Button size="small" icon={<EyeOutlined />} onClick={() => onViewLog(svc)} block>
          {t('servicesManage.btn_view_log')}
        </Button>
      </Tooltip>
    </Card>
  );
}

export default ServicesPage;