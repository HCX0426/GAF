/**
 * unattended master switch page — /ops/unattended
 *
 * 2 tabs:
 *  1. Control — master switch, preflight checklist, status matrix, execution queue
 *  2. Strategy — 5-layer recovery / night mode / frequency limit / notify / cooldown
 *
 * Control tab includes:
 * - master switch record: start/stop switch + three-color status light + pause / recover / emergency stop
 * - pre-check list: start before each item check result
 * - status matrix: device × account real-time run row status Grid
 *   (v3 §5.3: right-click a cell to dispatch a routine for that window+account)
 * - execute queue: pending execute task list
 */
import { useEffect, useState, useMemo, useCallback } from 'react';
import {
  Card,
  Spin,
  Empty,
  Typography,
  Row,
  Col,
  Tag,
  Tooltip,
  Progress,
  App,
  Table,
  Segmented,
  Dropdown,
  Button,
  Tabs,
  theme,
} from 'antd';
import {
  CheckCircleFilled,
  CloseCircleFilled,
  SyncOutlined,
  PauseCircleFilled,
  DashboardOutlined,
  TableOutlined,
  ThunderboltOutlined,
  ControlOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import UnattendedControlBar from './UnattendedControlBar';
import PreflightChecklist from './PreflightChecklist';
import DispatchRoutineModal from '@/components/GameProfile/DispatchRoutineModal';
import UnattendedStrategySettings from '@/components/Settings/UnattendedStrategySettings';
import { useUnattendedStore } from '@/stores/useUnattendedStore';
import { fetchDevice } from '@/api/devices';
import type { MatrixRow, QueueItem, Device } from '@/types/models';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation, getLocale } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';
import type { GlobalToken } from 'antd/es/theme/interface';

/** map cell status to its color + icon using design tokens */
function getCellStatusMap(
  token: GlobalToken,
): Record<
  string,
  {
    color: string;
    icon: typeof SyncOutlined | typeof CheckCircleFilled | typeof CloseCircleFilled | typeof PauseCircleFilled;
  }
> {
  return {
    running: { color: token.colorSuccess, icon: SyncOutlined },
    success: { color: token.colorSuccess, icon: CheckCircleFilled },
    failed: { color: token.colorError, icon: CloseCircleFilled },
    queued: { color: token.colorPrimary, icon: PauseCircleFilled },
    paused: { color: token.colorWarning, icon: PauseCircleFilled },
    idle: { color: token.colorBorder, icon: PauseCircleFilled },
  };
}

export function UnattendedControlPage() {
  const t = useTranslation();
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const cellStatusMap = getCellStatusMap(token);
  const {
    sessions,
    preflightChecks,
    preflightLoading,
    matrix,
    matrixLoading,
    queue,
    queueLoading,
    fetchMatrix,
    fetchQueue,
  } = useUnattendedStore();

  const [viewMode, setViewMode] = useState<string>('matrix');
  const [activeTab, setActiveTab] = useState<'control' | 'strategy'>('control');

  // v3 §5.3: matrix right-click dispatch state
  const [dispatchDevice, setDispatchDevice] = useState<Device | null>(null);
  const [dispatchProfileId, setDispatchProfileId] = useState<number | null>(null);
  const [dispatchDefaultRoutine, setDispatchDefaultRoutine] = useState<number | null>(null);
  const [dispatchLoading, setDispatchLoading] = useState(false);

  const handleCellDispatch = useCallback(
    async (deviceId: number | string) => {
      setDispatchLoading(true);
      try {
        const dev = await fetchDevice(Number(deviceId));
        if (!dev.game_profile) {
          message.warning(t('ops.dispatch_no_profile'));
          return;
        }
        setDispatchDevice(dev);
        setDispatchProfileId(dev.game_profile);
        // default_routine comes from profile detail; we don't have it here,
        // DispatchRoutineModal falls back to chains[0] when defaultRoutineId is null.
        setDispatchDefaultRoutine(null);
      } catch {
        message.error(t('ops.dispatch_load_device_failed'));
      } finally {
        setDispatchLoading(false);
      }
    },
    [message, t],
  );

  const QUEUE_STATUS_MAP: Record<string, { color: string; label: string }> = {
    queued: { color: 'default', label: t('ops.queue_queued') },
    warming_up: { color: 'processing', label: t('ops.queue_warming_up') },
    running: { color: 'success', label: t('ops.queue_running') },
  };

  useEffect(() => {
    fetchMatrix();
    fetchQueue();
    const interval = setInterval(() => {
      // P-011: refresh matrix/queue whenever any session is running
      if (sessions.some((s) => s.isRunning)) {
        fetchMatrix();
        fetchQueue();
      }
    }, 30000);
    return () => clearInterval(interval);
  }, [fetchMatrix, fetchQueue, sessions]);

  const matrixColumns: ColumnsType<MatrixRow> = useMemo(() => {
    const allAccounts = new Set<string>();
    matrix.forEach((row) => row.cells.forEach((c) => allAccounts.add(c.accountName)));
    const accountNames = Array.from(allAccounts);

    const baseColumns: ColumnsType<MatrixRow> = [
      {
        title: t('ops.col_device'),
        dataIndex: 'deviceName',
        key: 'deviceName',
        width: 160,
        fixed: 'left',
        render: (name: string, row: MatrixRow) => (
          <div className="gaf-flex-center gaf-gap-xs">
            <Tag color={row.deviceStatus === 'online' ? 'green' : 'red'}>
              {row.deviceStatus === 'online' ? t('ops.device_online') : t('ops.device_offline')}
            </Tag>
            <Typography.Text strong>{name}</Typography.Text>
          </div>
        ),
      },
    ];

    const accountColumns: ColumnsType<MatrixRow> = accountNames.map((acct) => ({
      title: acct,
      key: acct,
      width: 140,
      render: (_: unknown, row: MatrixRow) => {
        const cell = row.cells.find((c) => c.accountName === acct);
        if (!cell) return <Typography.Text type="secondary">—</Typography.Text>;
        const config = cellStatusMap[cell.status] || cellStatusMap.idle;
        const Icon = config.icon;
        const cellContent = (
          <Tooltip title={cell.taskName || t('ops.cell_idle')}>
            <div className="gaf-flex-center gaf-gap-xs">
              <Icon className="gaf-text-sm" style={{ color: config.color }} spin={cell.status === 'running'} />
              <Typography.Text className="gaf-text-xs">{cell.taskName || t('ops.cell_idle')}</Typography.Text>
              {cell.progress > 0 && cell.progress < 100 && (
                <Progress
                  percent={cell.progress}
                  size="small"
                  className="gaf-m-0"
                  style={{ width: 40 }}
                  showInfo={false}
                />
              )}
            </div>
          </Tooltip>
        );
        // v3 §5.3: right-click the cell to dispatch a routine for this window+account.
        // Click the small thunderbolt icon as an alternative entry (visible on hover).
        return (
          <Dropdown
            trigger={['contextMenu']}
            menu={{
              items: [
                {
                  key: 'dispatch',
                  label: t('ops.cell_dispatch'),
                  icon: <ThunderboltOutlined />,
                  disabled: row.deviceStatus !== 'online',
                  onClick: () => handleCellDispatch(row.deviceId),
                },
              ],
            }}
          >
            <div className="gaf-flex-center gaf-gap-xs">
              {cellContent}
              <Tooltip title={t('ops.cell_dispatch')}>
                <Button
                  type="link"
                  size="small"
                  className="gaf-cell-dispatch-btn"
                  style={{ padding: 0, opacity: 0.6 }}
                  disabled={row.deviceStatus !== 'online' || dispatchLoading}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleCellDispatch(row.deviceId);
                  }}
                  aria-label={t('ops.cell_dispatch')}
                  icon={<ThunderboltOutlined />}
                />
              </Tooltip>
            </div>
          </Dropdown>
        );
      },
    }));

    return [...baseColumns, ...accountColumns];
  }, [matrix, t, handleCellDispatch, dispatchLoading]);

  const queueColumns: ColumnsType<QueueItem> = [
    { title: t('ops.col_device'), dataIndex: 'deviceName', key: 'deviceName', width: 120 },
    { title: t('ops.col_account'), dataIndex: 'accountName', key: 'accountName', width: 100 },
    { title: t('ops.col_task'), dataIndex: 'taskName', key: 'taskName', ellipsis: true },
    {
      title: t('ops.col_status'),
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (s: string) => {
        const cfg = QUEUE_STATUS_MAP[s] || { color: 'default', label: s };
        return <Tag color={cfg.color}>{cfg.label}</Tag>;
      },
    },
    {
      title: t('ops.col_estimated_start'),
      dataIndex: 'estimatedStart',
      key: 'estimatedStart',
      width: 160,
      render: (v: string) => (v ? new Date(v).toLocaleString(getLocale()) : '—'),
    },
  ];

  return (
    <PageWrapper>
      <Tabs
        activeKey={activeTab}
        onChange={(k) => setActiveTab(k as 'control' | 'strategy')}
        items={[
          {
            key: 'control',
            label: (
              <span>
                <ControlOutlined />
                <span style={{ marginLeft: 6 }}>{t('ops.tab_control')}</span>
              </span>
            ),
            children: (
              <>
                <Card className="gaf-mb-lg">
                  <UnattendedControlBar />
                </Card>

                <Row gutter={[16, 16]}>
                  <Col xs={24} lg={12}>
                    <Card title={t('ops.card_preflight_title')} size="small">
                      <PreflightChecklist checks={preflightChecks} loading={preflightLoading} />
                    </Card>
                  </Col>

                  <Col xs={24} lg={12}>
                    <Card
                      title={t('ops.card_queue_title')}
                      size="small"
                      extra={
                        <Typography.Text type="secondary">
                          {t('ops.queue_count', { count: queue.length })}
                        </Typography.Text>
                      }
                    >
                      <Spin spinning={queueLoading}>
                        {queue.length === 0 ? (
                          <Empty description={t('ops.empty_queue')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
                        ) : (
                          <Table
                            rowKey="id"
                            columns={queueColumns}
                            dataSource={queue}
                            size="small"
                            pagination={false}
                            scroll={{ y: 260 }}
                          />
                        )}
                      </Spin>
                    </Card>
                  </Col>
                </Row>

                <Card
                  title={t('ops.card_matrix_title')}
                  size="small"
                  className="gaf-mt-lg"
                  extra={
                    <Segmented
                      size="small"
                      value={viewMode}
                      onChange={(val) => setViewMode(val as string)}
                      options={[
                        { label: t('ops.view_matrix'), value: 'matrix', icon: <DashboardOutlined /> },
                        { label: t('ops.view_table'), value: 'table', icon: <TableOutlined /> },
                      ]}
                    />
                  }
                >
                  <Spin spinning={matrixLoading}>
                    {matrix.length === 0 ? (
                      <Empty description={t('ops.empty_matrix')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
                    ) : (
                      <Table
                        rowKey="deviceId"
                        columns={matrixColumns}
                        dataSource={matrix}
                        size="small"
                        pagination={false}
                        scroll={{ x: 'max-content' }}
                      />
                    )}
                  </Spin>
                </Card>

                {/* v3 §5.3: matrix right-click dispatch modal */}
                <DispatchRoutineModal
                  open={dispatchDevice !== null}
                  onClose={() => {
                    setDispatchDevice(null);
                    setDispatchProfileId(null);
                    setDispatchDefaultRoutine(null);
                  }}
                  profileId={dispatchProfileId ?? 0}
                  device={dispatchDevice}
                  defaultRoutineId={dispatchDefaultRoutine}
                />
              </>
            ),
          },
          {
            key: 'strategy',
            label: (
              <span>
                <SettingOutlined />
                <span style={{ marginLeft: 6 }}>{t('ops.tab_strategy')}</span>
              </span>
            ),
            children: <UnattendedStrategySettings />,
          },
        ]}
      />
    </PageWrapper>
  );
}

export default UnattendedControlPage;
