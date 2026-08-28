/**
 * account batch detect Modal
 * to select fixed range or all account in progress batch status detect
 */
import { useState, useRef, useEffect } from 'react';
import { Modal, Radio, Button, Progress, Table, Tag, Space, App, theme as antTheme } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { batchCheckAccounts } from '@/api/accounts';
import { useTranslation } from '@/i18n';

interface AccountBatchCheckerProps {
  accountIds: number[];
  open: boolean;
  onClose: () => void;
  onComplete: () => void;
}

/** detect result item */
interface CheckResultItem {
  id: number;
  status: string;
  message: string;
}

/** detect status */
type CheckStatus = 'idle' | 'checking' | 'done';

/**
 * batch check account status component
 * supports full detect and select in detect two types mode
 */
export function AccountBatchChecker({ accountIds, open, onClose, onComplete }: AccountBatchCheckerProps) {
  const { message } = App.useApp();
  const { token } = antTheme.useToken();
  const t = useTranslation();
  const [scope, setScope] = useState<'selected' | 'all'>('selected');
  const [checkStatus, setCheckStatus] = useState<CheckStatus>('idle');
  const [progress, setProgress] = useState(0);
  const [results, setResults] = useState<CheckResultItem[]>([]);
  const [filter, setFilter] = useState<'all' | 'error' | 'warn'>('all');
  /** Track pending progress timers so they can be cleaned up on unmount/restart */
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  /** Clear all pending progress timers */
  const clearTimers = () => {
    timersRef.current.forEach((t) => clearTimeout(t));
    timersRef.current = [];
  };

  /** Clean up timers on unmount */
  useEffect(() => {
    return () => clearTimers();
  }, []);

  /**
   * start batch detect
   */
  const handleStart = async () => {
    clearTimers();
    setCheckStatus('checking');
    setProgress(0);
    setResults([]);
    setFilter('all');

    try {
      const payload = scope === 'all' ? { check_all: true } : { account_ids: accountIds };

      const data = await batchCheckAccounts(payload);
      const items = data.results || [];

      const total = items.length;
      setResults(items);

      if (total === 0) {
        setProgress(100);
        setCheckStatus('done');
        message.success(t('accounts.check_complete', { count: 0 }));
        return;
      }

      // Animate progress bar; mark done only after the last tick fires
      items.forEach((_, index) => {
        const timer = setTimeout(() => {
          setProgress(Math.round(((index + 1) / total) * 100));
          if (index === total - 1) {
            setCheckStatus('done');
            message.success(t('accounts.check_complete', { count: total }));
          }
        }, index * 80);
        timersRef.current.push(timer);
      });
    } catch {
      message.error(t('accounts.batch_check_failed'));
      setCheckStatus('idle');
    }
  };

  /** filter after result */
  const filteredResults = filter === 'all' ? results : results.filter((r) => r.status === filter);

  /** summary stats */
  const summary = {
    total: results.length,
    ok: results.filter((r) => r.status === 'ok').length,
    warn: results.filter((r) => r.status === 'warn').length,
    error: results.filter((r) => r.status === 'error').length,
  };

  /** status color mapping */
  const statusColorMap: Record<string, string> = {
    ok: 'success',
    warn: 'warning',
    error: 'error',
    unknown: 'default',
  };

  /** result table column definition */
  const columns: ColumnsType<CheckResultItem> = [
    {
      title: t('accounts.col_account_id'),
      dataIndex: 'id',
      key: 'id',
      width: 80,
    },
    {
      title: t('accounts.col_status'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => <Tag color={statusColorMap[status] || 'default'}>{status}</Tag>,
    },
    {
      title: t('accounts.col_info'),
      dataIndex: 'message',
      key: 'message',
    },
  ];

  /**
   * export CSV
   */
  const handleExportCSV = () => {
    const header = `${t('accounts.col_account_id')},${t('accounts.col_status')},${t('accounts.col_info')}\n`;
    const rows = results.map((r) => `${r.id},${r.status},"${r.message}"`).join('\n');
    const blob = new Blob(['\uFEFF' + header + rows], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `account_check_${Date.now()}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  /**
   * close reset
   */
  const handleClose = () => {
    setCheckStatus('idle');
    setResults([]);
    setProgress(0);
    onClose();
  };

  return (
    <Modal
      title={t('accounts.batch_check_title')}
      open={open}
      onCancel={handleClose}
      width={700}
      footer={
        checkStatus === 'idle' ? (
          <Space>
            <Button onClick={handleClose}>{t('accounts.cancel')}</Button>
            <Button type="primary" onClick={handleStart}>
              {t('accounts.start_check')}
            </Button>
          </Space>
        ) : checkStatus === 'done' ? (
          <Space>
            <Button onClick={handleExportCSV}>{t('accounts.export_csv')}</Button>
            <Button
              type="primary"
              onClick={() => {
                onComplete();
                handleClose();
              }}
            >
              {t('accounts.close')}
            </Button>
          </Space>
        ) : null
      }
    >
      {checkStatus === 'idle' && (
        <Radio.Group value={scope} onChange={(e) => setScope(e.target.value)}>
          <Radio value="selected">{t('accounts.selected_accounts', { count: accountIds.length })}</Radio>
          <Radio value="all">{t('accounts.all_accounts')}</Radio>
        </Radio.Group>
      )}

      {checkStatus === 'checking' && (
        <div style={{ padding: '24px 0' }}>
          <Progress percent={progress} status="active" />
          <p className="gaf-mt-sm gaf-text-center" style={{ color: token.colorTextTertiary }}>
            {t('accounts.checking_progress', { done: results.length, total: results.length || '...' })}
          </p>
        </div>
      )}

      {checkStatus === 'done' && (
        <>
          <div className="gaf-mb-lg">
            <Space>
              <Tag color="blue">{t('accounts.summary_total', { count: summary.total })}</Tag>
              <Tag color="success">{t('accounts.summary_ok', { count: summary.ok })}</Tag>
              <Tag color="warning">{t('accounts.summary_warn', { count: summary.warn })}</Tag>
              <Tag color="error">{t('accounts.summary_error', { count: summary.error })}</Tag>
            </Space>
          </div>

          <div className="gaf-mb-md">
            <Space>
              <Tag
                color={filter === 'all' ? 'blue' : 'default'}
                className="gaf-cursor-pointer"
                onClick={() => setFilter('all')}
              >
                {t('accounts.filter_all')}
              </Tag>
              <Tag
                color={filter === 'error' ? 'red' : 'default'}
                className="gaf-cursor-pointer"
                onClick={() => setFilter('error')}
              >
                {t('accounts.filter_error')}
              </Tag>
              <Tag
                color={filter === 'warn' ? 'orange' : 'default'}
                className="gaf-cursor-pointer"
                onClick={() => setFilter('warn')}
              >
                {t('accounts.filter_warn')}
              </Tag>
            </Space>
          </div>

          <Table
            columns={columns}
            dataSource={filteredResults}
            rowKey="id"
            pagination={false}
            size="small"
            scroll={{ y: 300 }}
          />
        </>
      )}
    </Modal>
  );
}

export default AccountBatchChecker;
