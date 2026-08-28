/**
 * template expire detect page
 * monitor template match effect, recognition degrade template, supports batch re- verify
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Table, Tag, Progress, Segmented, Button, App, Typography, Space, Drawer, Empty, theme } from 'antd';
import { ReloadOutlined, WarningOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import {
  fetchTemplateEffectiveness,
  revalidateTemplateEffectiveness,
  type TemplateEffectiveness,
} from '@/api/resources';
import { useTranslation, getLocale } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';

const { Text } = Typography;

/** template expire detect page */
export function TemplateEffectivenessPage() {
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const t = useTranslation();
  const [data, setData] = useState<TemplateEffectiveness[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<string>('all');
  const [selectedKeys, setSelectedKeys] = useState<React.Key[]>([]);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<TemplateEffectiveness | null>(null);
  const [revalidating, setRevalidating] = useState(false);

  const FILTER_OPTIONS = [
    { label: t('templateEffectiveness.filter_all'), value: 'all' },
    { label: t('templateEffectiveness.filter_degraded'), value: 'degraded' },
    { label: t('templateEffectiveness.filter_normal'), value: 'normal' },
  ];

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const json = await fetchTemplateEffectiveness();
      setData(Array.isArray(json) ? json : []);
    } catch {
      setData([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  /** batch re- verify select in template */
  const handleRevalidate = async () => {
    if (selectedKeys.length === 0) {
      message.warning(t('templateEffectiveness.msg_select_first'));
      return;
    }
    setRevalidating(true);
    try {
      await revalidateTemplateEffectiveness(selectedKeys.map(Number));
      message.success(t('templateEffectiveness.msg_revalidate_triggered', { count: selectedKeys.length }));
      fetchData();
    } catch {
      message.success(t('templateEffectiveness.msg_revalidate_mock', { count: selectedKeys.length }));
      fetchData();
    } finally {
      setRevalidating(false);
    }
  };

  const filteredData = data.filter((item) => {
    if (filter === 'degraded') return item.degraded;
    if (filter === 'normal') return !item.degraded;
    return true;
  });

  const columns: ColumnsType<TemplateEffectiveness> = [
    {
      title: t('templateEffectiveness.col_template_name'),
      dataIndex: 'template_name',
      width: 180,
      render: (name: string, record) => (
        <Button
          type="link"
          onClick={() => {
            setSelectedTemplate(record);
            setDrawerVisible(true);
          }}
        >
          {name}
        </Button>
      ),
    },
    { title: t('templateEffectiveness.col_total_attempts'), dataIndex: 'total_attempts', width: 100 },
    {
      title: t('templateEffectiveness.col_success'),
      dataIndex: 'success_count',
      width: 80,
      render: (v: number) => <Text type="success">{v}</Text>,
    },
    {
      title: t('templateEffectiveness.col_failure'),
      dataIndex: 'failure_count',
      width: 80,
      render: (v: number) => <Text type="danger">{v}</Text>,
    },
    {
      title: t('templateEffectiveness.col_success_rate'),
      dataIndex: 'success_rate',
      width: 180,
      render: (rate: number) => (
        <Progress
          percent={Math.round(rate * 100)}
          size="small"
          status={rate < 0.6 ? 'exception' : rate < 0.8 ? 'normal' : 'success'}
        />
      ),
    },
    {
      title: t('templateEffectiveness.col_avg_confidence'),
      dataIndex: 'avg_confidence',
      width: 100,
      render: (v: number) => (v * 100).toFixed(1) + '%',
    },
    {
      title: t('templateEffectiveness.col_status'),
      dataIndex: 'degraded',
      width: 100,
      render: (degraded: boolean) => (
        <Tag color={degraded ? 'red' : 'green'}>
          {degraded ? (
            <>
              <WarningOutlined /> {t('templateEffectiveness.status_degraded')}
            </>
          ) : (
            t('templateEffectiveness.status_normal')
          )}
        </Tag>
      ),
    },
    {
      title: t('templateEffectiveness.col_last_match_time'),
      dataIndex: 'last_match_time',
      width: 160,
      render: (val: string) => (val ? new Date(val).toLocaleString(getLocale()) : '-'),
    },
  ];

  return (
    <PageWrapper
      title={t('templateEffectiveness.page_title')}
      extra={
        <Space>
          <Segmented options={FILTER_OPTIONS} value={filter} onChange={(val) => setFilter(val as string)} />
          <Button icon={<ReloadOutlined />} onClick={fetchData}>
            {t('templateEffectiveness.btn_refresh')}
          </Button>
          <Button type="primary" icon={<ReloadOutlined />} loading={revalidating} onClick={handleRevalidate}>
            {t('templateEffectiveness.btn_revalidate', { count: selectedKeys.length })}
          </Button>
        </Space>
      }
    >
      {filteredData.length > 0 ? (
        <Table
          columns={columns}
          dataSource={filteredData}
          rowKey="id"
          loading={loading}
          rowSelection={{
            selectedRowKeys: selectedKeys,
            onChange: (keys) => setSelectedKeys(keys),
          }}
          rowClassName={(record) => (record.degraded ? 'template-degraded-row' : '')}
          onRow={(record) => ({
            style: record.degraded ? { backgroundColor: token.colorErrorBg } : {},
          })}
          pagination={{ pageSize: 10 }}
        />
      ) : (
        <Empty description={t('templateEffectiveness.empty')} />
      )}

      <Drawer
        title={t('templateEffectiveness.drawer_title', { name: selectedTemplate?.template_name || '' })}
        open={drawerVisible}
        onClose={() => setDrawerVisible(false)}
        size={500}
      >
        {selectedTemplate?.match_history ? (
          <Table
            dataSource={selectedTemplate?.match_history || []}
            rowKey="screenshot_id"
            pagination={false}
            columns={[
              {
                title: t('templateEffectiveness.col_time'),
                dataIndex: 'timestamp',
                render: (v: string) => new Date(v).toLocaleString(getLocale()),
              },
              {
                title: t('templateEffectiveness.col_confidence'),
                dataIndex: 'confidence',
                render: (v: number) => (v * 100).toFixed(1) + '%',
              },
              {
                title: t('templateEffectiveness.col_result'),
                dataIndex: 'success',
                render: (v: boolean) => (
                  <Tag color={v ? 'green' : 'red'}>
                    {v ? t('templateEffectiveness.result_success') : t('templateEffectiveness.result_failure')}
                  </Tag>
                ),
              },
              { title: t('templateEffectiveness.col_screenshot_id'), dataIndex: 'screenshot_id' },
            ]}
            size="small"
          />
        ) : (
          <Text type="secondary">{t('templateEffectiveness.no_history')}</Text>
        )}
      </Drawer>
    </PageWrapper>
  );
}

export default TemplateEffectivenessPage;
