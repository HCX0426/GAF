/**
 * verify status panel component
 * show every items resource pack verify status, progress bar and re- verify operation
 */
import { useEffect, useRef, useState } from 'react';
import { Table, Tag, Button, Progress, Card, Spin, Space, Statistic, App, Typography, theme } from 'antd';
import { ReloadOutlined, CheckCircleOutlined, WarningOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { fetchValidationStatuses, revalidateAllResourcePacks, type ValidationStatus } from '@/api/resources';
import { useTranslation, getLocale } from '@/i18n';

export function ValidationPanel() {
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const t = useTranslation();
  const [validationData, setValidationData] = useState<ValidationStatus[]>([]);
  const [loading, setLoading] = useState(false);
  const [revalidating, setRevalidating] = useState(false);
  /** Track the post-revalidate refresh timer so it can be cleaned up on unmount */
  const revalidateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** Clear any pending revalidate timer on unmount */
  useEffect(() => {
    return () => {
      if (revalidateTimerRef.current) clearTimeout(revalidateTimerRef.current);
    };
  }, []);

  useEffect(() => {
    loadValidationData();
  }, []);

  /** load verify status data */
  const loadValidationData = async () => {
    setLoading(true);
    try {
      const data = await fetchValidationStatuses();
      setValidationData(data);
    } catch {
      message.error(t('resources.msg_load_validation_failed'));
    } finally {
      setLoading(false);
    }
  };

  /** execute all re- verify operation */
  const handleRevalidateAll = async () => {
    setRevalidating(true);
    try {
      await revalidateAllResourcePacks();
      message.success(t('resources.msg_revalidate_triggered'));
      if (revalidateTimerRef.current) clearTimeout(revalidateTimerRef.current);
      revalidateTimerRef.current = setTimeout(() => loadValidationData(), 2000);
    } catch {
      message.error(t('resources.msg_revalidate_failed'));
    } finally {
      setRevalidating(false);
    }
  };

  /** get status label color and icon */
  const getStatusTag = (status: string) => {
    switch (status) {
      case 'ok':
        return (
          <Tag icon={<CheckCircleOutlined />} color="success">
            {t('resources.status_ok')}
          </Tag>
        );
      case 'partial':
        return (
          <Tag icon={<WarningOutlined />} color="warning">
            {t('resources.status_partial')}
          </Tag>
        );
      case 'stale':
        return (
          <Tag icon={<ClockCircleOutlined />} color="default">
            {t('resources.status_stale')}
          </Tag>
        );
      default:
        return <Tag>{status}</Tag>;
    }
  };

  /** calculate has effective ratio percentage */
  const getValidPercent = (record: ValidationStatus): number => {
    const total = record.valid_count + record.invalid_count;
    if (total === 0) return 0;
    return Math.round((record.valid_count / total) * 100);
  };

  /** stats summary data */
  const totalPacks = validationData.length;
  const okCount = validationData.filter((v) => v.status === 'ok').length;
  const partialCount = validationData.filter((v) => v.status === 'partial').length;
  const staleCount = validationData.filter((v) => v.status === 'stale').length;

  const columns = [
    {
      title: t('resources.col_pack_name'),
      dataIndex: 'pack_name',
      key: 'pack_name',
      render: (name: string) => <strong>{name}</strong>,
    },
    {
      title: t('resources.col_validation_status'),
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => getStatusTag(status),
    },
    {
      title: t('resources.col_valid_total'),
      key: 'ratio',
      width: 200,
      render: (_: unknown, record: ValidationStatus) => (
        <div>
          <Progress
            percent={getValidPercent(record)}
            size="small"
            status={getValidPercent(record) === 100 ? 'success' : 'active'}
            format={() => `${record.valid_count}/${record.total_count}`}
          />
          <Typography.Text type="secondary" className="gaf-text-xxs">
            {t('resources.label_invalid_count', { count: record.invalid_count })}
          </Typography.Text>
        </div>
      ),
    },
    {
      title: t('resources.col_last_validated'),
      dataIndex: 'last_validated_at',
      key: 'last_validated_at',
      width: 180,
      render: (time: string) => (time ? new Date(time).toLocaleString(getLocale()) : '-'),
    },
  ];

  return (
    <div>
      <Card
        title={t('resources.title_validation_panel')}
        extra={
          <Button
            type="primary"
            icon={<ReloadOutlined spin={revalidating} />}
            loading={revalidating}
            onClick={handleRevalidateAll}
          >
            {t('resources.btn_revalidate_all')}
          </Button>
        }
        className="gaf-mb-lg"
      >
        <Space size="large" className="gaf-mb-lg">
          <Statistic title={t('resources.stat_total_packs')} value={totalPacks} />
          <Statistic
            title={t('resources.stat_ok')}
            value={okCount}
            styles={{ content: { color: token.colorSuccess } }}
          />
          <Statistic
            title={t('resources.stat_partial')}
            value={partialCount}
            styles={{ content: { color: token.colorWarning } }}
          />
          <Statistic
            title={t('resources.stat_stale')}
            value={staleCount}
            styles={{ content: { color: token.colorTextTertiary } }}
          />
        </Space>

        <Spin spinning={loading}>
          <Table
            dataSource={validationData || []}
            columns={columns}
            rowKey="pack_id"
            pagination={false}
            size="middle"
          />
        </Spin>
      </Card>
    </div>
  );
}

export default ValidationPanel;
