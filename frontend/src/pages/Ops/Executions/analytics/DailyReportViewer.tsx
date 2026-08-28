/**
 * every daily execution report view device
 * show specified date execute report, supports date select,PDF/MD export
 */
import { useState, useEffect, useCallback } from 'react';
import { Card, DatePicker, Button, Space, Spin, Empty, Descriptions, Table, Tag, Typography } from 'antd';
import { FilePdfOutlined, FileMarkdownOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useTranslation } from '@/i18n';
import { getDailyReport, type DailyReportData } from '@/api/executions';

const { Text } = Typography;

/** DailyReportViewer component props */
interface DailyReportViewerProps {
  date?: string;
}

/** status color mapping */
const STATUS_COLOR_MAP: Record<string, string> = {
  success: 'green',
  failed: 'red',
  running: 'blue',
  pending: 'orange',
};

/** status in text mapping */
const STATUS_LABEL_MAP: Record<string, string> = {
  success: 'executions.report_status_success',
  failed: 'executions.report_status_failed',
  running: 'executions.report_status_running',
  pending: 'executions.report_status_pending',
};

/**
 */
export function DailyReportViewer({ date: propDate }: DailyReportViewerProps) {
  const t = useTranslation();
  const [selectedDate, setSelectedDate] = useState<string>(propDate || dayjs().format('YYYY-MM-DD'));
  const [reportData, setReportData] = useState<DailyReportData | null>(null);
  const [loading, setLoading] = useState(false);

  /** load report data */
  const loadReport = useCallback(async (targetDate: string) => {
    setLoading(true);
    try {
      // F005 fix: use client-based API instead of raw fetch() (which had no auth headers).
      const data = await getDailyReport(targetDate);
      setReportData(data);
    } catch {
      setReportData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReport(selectedDate);
  }, [selectedDate, loadReport]);

  /** handle date change */
  const handleDateChange = (_date: dayjs.Dayjs | null, dateString: string | null) => {
    if (dateString) setSelectedDate(dateString);
  };

  /** export PDF( call browser print ) */
  const handleExportPDF = () => window.print();

  /** export Markdown file download */
  const handleExportMD = () => {
    if (!reportData) return;
    const { summary, items } = reportData;
    let md = `# ${t('executions.md_report_title', { date: selectedDate })}\n\n`;
    md += `## ${t('executions.md_summary')}\n\n`;
    md += `- ${t('executions.label_total_executions')}: ${summary.total_executions}\n`;
    md += `- ${t('executions.label_success')}: ${summary.success_count}\n`;
    md += `- ${t('executions.label_failed')}: ${summary.failed_count}\n`;
    md += `- ${t('executions.label_avg_duration')}: ${summary.avg_duration}\n\n`;
    md += `## ${t('executions.md_details')}\n\n`;
    md += `| ${t('executions.col_task_name')} | ${t('executions.col_device')} | ${t('executions.col_account')} | ${t('executions.col_status')} | ${t('executions.col_duration')} |\n`;
    md += `|--------|------|------|------|------|\n`;
    items.forEach((item) => {
      md += `| ${item.task_name} | ${item.device_name} | ${item.account_name} | ${t(STATUS_LABEL_MAP[item.status] || 'executions.col_status')} | ${item.duration} |\n`;
    });
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `daily-report-${selectedDate}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  /** details table column definition */
  const columns = [
    { title: t('executions.col_task_name'), dataIndex: 'task_name', key: 'task_name', ellipsis: true },
    { title: t('executions.col_device'), dataIndex: 'device_name', key: 'device_name', width: 100 },
    { title: t('executions.col_account'), dataIndex: 'account_name', key: 'account_name', width: 100 },
    {
      title: t('executions.col_status'),
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status: string) => (
        <Tag color={STATUS_COLOR_MAP[status] || 'default'}>
          {t(STATUS_LABEL_MAP[status] || 'executions.col_status')}
        </Tag>
      ),
    },
    { title: t('executions.col_duration'), dataIndex: 'duration', key: 'duration', width: 90 },
  ];

  return (
    <div>
      <div className="gaf-flex-between gaf-flex-wrap gaf-gap-sm gaf-mb-lg">
        <Space>
          <DatePicker value={dayjs(selectedDate)} onChange={handleDateChange} />
          <Text type="secondary" className="gaf-text-13">
            {t('executions.text_report_date')}
          </Text>
        </Space>
        <Space>
          <Button icon={<FilePdfOutlined />} onClick={handleExportPDF}>
            {t('executions.btn_export_pdf')}
          </Button>
          <Button icon={<FileMarkdownOutlined />} onClick={handleExportMD}>
            {t('executions.btn_export_md')}
          </Button>
        </Space>
      </div>

      <Spin spinning={loading}>
        {!reportData && !loading ? (
          <Empty description={t('executions.text_no_report')} />
        ) : reportData ? (
          <Card title={t('executions.text_daily_report_title', { date: selectedDate })}>
            <Descriptions bordered column={{ xs: 1, sm: 2, md: 4 }} size="small" className="gaf-mb-lg">
              <Descriptions.Item label={t('executions.label_total_executions')}>
                {reportData.summary.total_executions}
              </Descriptions.Item>
              <Descriptions.Item label={t('executions.label_success')}>
                <Tag color="green">{reportData.summary.success_count}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('executions.label_failed')}>
                <Tag color="red">{reportData.summary.failed_count}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('executions.label_avg_duration')}>
                {reportData.summary.avg_duration}
              </Descriptions.Item>
            </Descriptions>

            <Table
              columns={columns}
              dataSource={reportData.results || reportData.items || []}
              rowKey="id"
              pagination={false}
              size="small"
              scroll={{ y: 400 }}
            />

            {reportData.generated_at && (
              <div className="gaf-mt-md" style={{ textAlign: 'right' }}>
                <Text type="secondary" className="gaf-text-xs">
                  {t('executions.text_report_generated_at', {
                    time: dayjs(reportData.generated_at).format('YYYY-MM-DD HH:mm:ss'),
                  })}
                </Text>
              </div>
            )}
          </Card>
        ) : null}
      </Spin>
    </div>
  );
}

export default DailyReportViewer;
