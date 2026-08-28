/**
 * recovery operation log Tab (P-020-C)
 *
 * show 5 layer recover mechanism execute history:
 * - step ( step level )
 * - task ( task level )
 * - app ( app level )
 * - device ( device level )
 * - system ( system level )
 *
 * supports:
 * - by recovery_level filter
 * - by success filter
 * - click row view details JSON details
 * - details Modal show complete chain_result
 */

import { useCallback, useEffect, useState } from 'react';
import { App, Button, Modal, Select, Space, Table, Tag, Tooltip, theme as antTheme } from 'antd';
import { ReloadOutlined, EyeOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { fetchRecoveryLog, fetchRecoveryLogs, type RecoveryLogEntry } from '@/api/scheduler';
import { useTranslation, getLocale } from '@/i18n';

// 注意: antTheme.useToken() 必须在组件内部调用 (hook 规则),
// 此处原写法 `const { token } = antTheme.useToken` 是 bug — 取的是函数本身而非调用结果,
// token 实际为 undefined. 已移到 RecoveryLogTab 组件内部 (见下文).

/** Format ISO datetime to local string using the current locale */
function formatDateTime(val: string | null | undefined): string {
  if (!val) return '-';
  return new Intl.DateTimeFormat(getLocale(), {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(val));
}

/** Recovery level → color / short label */
const LEVEL_COLOR_MAP: Record<RecoveryLogEntry['recovery_level'], string> = {
  step: 'blue',
  task: 'cyan',
  app: 'gold',
  device: 'orange',
  system: 'red',
};

/** Map a recovery level to its i18n key (label resolved at call site). */
function levelLabelKey(level: RecoveryLogEntry['recovery_level']): string {
  switch (level) {
    case 'step':
      return 'monitors.recovery_level_step_label';
    case 'task':
      return 'monitors.recovery_level_task_label';
    case 'app':
      return 'monitors.recovery_level_app_label';
    case 'device':
      return 'monitors.recovery_level_device_label';
    case 'system':
      return 'monitors.recovery_level_system_label';
    default:
      return 'monitors.recovery_level_system_label';
  }
}

interface RecoveryLogTabProps {
  refreshKey: number;
}

export function RecoveryLogTab({ refreshKey }: RecoveryLogTabProps) {
  const t = useTranslation();
  const { message: msg } = App.useApp();
  const { token } = antTheme.useToken();
  const [logs, setLogs] = useState<RecoveryLogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [levelFilter, setLevelFilter] = useState<RecoveryLogEntry['recovery_level'] | undefined>();
  const [successFilter, setSuccessFilter] = useState<boolean | undefined>();
  const [detailModal, setDetailModal] = useState<{ open: boolean; entry: RecoveryLogEntry | null }>({
    open: false,
    entry: null,
  });

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params: { recovery_level?: RecoveryLogEntry['recovery_level']; success?: boolean } = {};
      if (levelFilter) params.recovery_level = levelFilter;
      if (successFilter !== undefined) params.success = successFilter;
      const res = await fetchRecoveryLogs(params);
      setLogs(res);
    } catch {
      msg.error(t('monitors.msg_load_recovery_failed'));
    } finally {
      setLoading(false);
    }
  }, [levelFilter, successFilter, msg, t]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reuse Monitors page other Tab load pattern (RulesTab/EventsTab same pattern )
    loadLogs();
  }, [loadLogs, refreshKey]);

  const handleViewDetail = async (id: number) => {
    try {
      const entry = await fetchRecoveryLog(id);
      setDetailModal({ open: true, entry });
    } catch {
      msg.error(t('monitors.msg_load_detail_failed'));
    }
  };

  const columns: ColumnsType<RecoveryLogEntry> = [
    {
      title: t('monitors.col_recovery_level'),
      dataIndex: 'recovery_level',
      key: 'recovery_level',
      width: 110,
      render: (level: RecoveryLogEntry['recovery_level']) => (
        <Tag color={LEVEL_COLOR_MAP[level]}>{t(levelLabelKey(level))}</Tag>
      ),
    },
    {
      title: t('monitors.col_trigger_event'),
      dataIndex: 'trigger_event',
      key: 'trigger_event',
      ellipsis: true,
      render: (val: string) => (
        <Tooltip title={val}>
          <span>{val}</span>
        </Tooltip>
      ),
    },
    {
      title: t('monitors.col_action_taken'),
      dataIndex: 'action_taken',
      key: 'action_taken',
      ellipsis: true,
      width: 200,
      render: (val: string) => (
        <Tooltip title={val}>
          <span>{val}</span>
        </Tooltip>
      ),
    },
    {
      title: t('monitors.col_result'),
      dataIndex: 'success',
      key: 'success',
      width: 80,
      render: (success: boolean) =>
        success ? (
          <Tag icon={<CheckCircleOutlined />} color="green">
            {t('monitors.result_success')}
          </Tag>
        ) : (
          <Tag icon={<CloseCircleOutlined />} color="red">
            {t('monitors.result_failed')}
          </Tag>
        ),
    },
    {
      title: t('monitors.col_created_at'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (val: string) => formatDateTime(val),
    },
    {
      title: t('monitors.col_action'),
      key: 'action',
      width: 90,
      fixed: 'right',
      render: (_, record) => (
        <Tooltip title={t('monitors.tooltip_view_recovery_detail')}>
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            aria-label={t('monitors.aria_view_recovery_detail')}
            onClick={() => handleViewDetail(record.id)}
          >
            {t('monitors.btn_detail')}
          </Button>
        </Tooltip>
      ),
    },
  ];

  // stats
  const stats = {
    total: logs.length,
    success: logs.filter((l) => l.success).length,
    failed: logs.filter((l) => !l.success).length,
  };

  return (
    <div>
      <div className="gaf-mb-md">
        <Space wrap>
          <Select
            placeholder={t('monitors.placeholder_filter_recovery_level')}
            allowClear
            style={{ width: 150 }}
            value={levelFilter}
            onChange={setLevelFilter}
            options={[
              { value: 'step', label: t('monitors.recovery_level_step_label') },
              { value: 'task', label: t('monitors.recovery_level_task_label') },
              { value: 'app', label: t('monitors.recovery_level_app_label') },
              { value: 'device', label: t('monitors.recovery_level_device_label') },
              { value: 'system', label: t('monitors.recovery_level_system_label') },
            ]}
          />
          <Select
            placeholder={t('monitors.placeholder_filter_result')}
            allowClear
            style={{ width: 130 }}
            value={successFilter}
            onChange={setSuccessFilter}
            options={[
              { value: true, label: t('monitors.result_success') },
              { value: false, label: t('monitors.result_failed') },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={loadLogs}>
            {t('monitors.btn_refresh')}
          </Button>
        </Space>
        <Space style={{ marginLeft: 16 }}>
          <Tag color="default">
            {t('monitors.stats_total')} {stats.total}
          </Tag>
          <Tag color="green">
            {t('monitors.result_success')} {stats.success}
          </Tag>
          <Tag color="red">
            {t('monitors.result_failed')} {stats.failed}
          </Tag>
        </Space>
      </div>
      <Table
        columns={columns}
        dataSource={logs}
        rowKey="id"
        loading={loading}
        size="small"
        pagination={{
          pageSize: 20,
          showSizeChanger: true,
          showTotal: (total) => t('monitors.pagination_total', { count: total }),
        }}
        scroll={{ x: 800 }}
      />
      <Modal
        title={
          detailModal.entry ? (
            <Space>
              <Tag color={LEVEL_COLOR_MAP[detailModal.entry.recovery_level]}>
                {t(levelLabelKey(detailModal.entry.recovery_level))}
              </Tag>
              <span>{t('monitors.recovery_detail_title', { id: detailModal.entry.id })}</span>
            </Space>
          ) : (
            t('monitors.recovery_detail_title_default')
          )
        }
        open={detailModal.open}
        onCancel={() => setDetailModal({ open: false, entry: null })}
        footer={<Button onClick={() => setDetailModal({ open: false, entry: null })}>{t('monitors.btn_close')}</Button>}
        width={700}
      >
        {detailModal.entry && (
          <div>
            <Space orientation="vertical" className="gaf-w-full" size="middle">
              <div>
                <b>{t('monitors.col_trigger_event')}:</b> {detailModal.entry.trigger_event}
              </div>
              <div>
                <b>{t('monitors.col_action_taken')}:</b> {detailModal.entry.action_taken}
              </div>
              <div>
                <b>{t('monitors.col_result')}:</b>{' '}
                {detailModal.entry.success ? (
                  <Tag color="green">{t('monitors.result_success')}</Tag>
                ) : (
                  <Tag color="red">{t('monitors.result_failed')}</Tag>
                )}
              </div>
              <div>
                <b>{t('monitors.col_created_at')}:</b> {formatDateTime(detailModal.entry.created_at)}
              </div>
              <div>
                <b>{t('monitors.detail_json_label')}</b>
                <pre
                  className="gaf-mt-sm gaf-p-md gaf-text-xs gaf-overflow-auto"
                  style={{ background: token.colorBgLayout, borderRadius: 6, maxHeight: 360 }}
                >
                  {JSON.stringify(detailModal.entry.details, null, 2)}
                </pre>
              </div>
            </Space>
          </div>
        )}
      </Modal>
    </div>
  );
}

export default RecoveryLogTab;
