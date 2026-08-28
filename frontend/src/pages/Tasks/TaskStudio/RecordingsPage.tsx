/**
 * recording management page
 * show recording list, supports view details, convert is Pipeline, delete etc. operation
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Table,
  Button,
  Space,
  Tag,
  Modal,
  App,
  Card,
  Empty,
  Typography,
  Descriptions,
  Popconfirm,
  Tooltip,
  Badge,
  Row,
  Col,
  Statistic,
  theme,
} from 'antd';
import {
  DeleteOutlined,
  ExportOutlined,
  EyeOutlined,
  PlayCircleOutlined,
  VideoCameraOutlined,
  ClockCircleOutlined,
  FileImageOutlined,
  StepForwardOutlined,
} from '@ant-design/icons';
import { fetchRecordings, fetchRecordingDetail, convertRecordingToPipeline, deleteRecording } from '@/api/recordings';
import type { RecordingItem, RecordingDetail, RecordingEvent } from '@/api/recordings';
import { useTranslation } from '@/i18n';
import dayjs from 'dayjs';
import RecordingStepper from './RecordingStepper';
import PageWrapper from '@/components/Common/PageWrapper';

const { Text, Title } = Typography;

/** recording management page component */
export function RecordingsPage() {
  const t = useTranslation();
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const [recordings, setRecordings] = useState<RecordingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [selectedRecording, setSelectedRecording] = useState<RecordingItem | null>(null);
  const [detailData, setDetailData] = useState<Record<string, unknown> | null>(null);
  const [convertingId, setConvertingId] = useState<number | null>(null);
  const [stepperOpen, setStepperOpen] = useState(false);
  const [stepperEvents, setStepperEvents] = useState<RecordingEvent[]>([]);
  const [stepperName, setStepperName] = useState('');

  /** load recording list */
  const loadRecordings = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchRecordings();
      setRecordings(data);
    } catch (err: unknown) {
      const detail = err instanceof Error ? err.message : String(err);
      message.error(t('taskStudio.recordings.load_failed', { detail }));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadRecordings();
  }, [loadRecordings]);

  /** view recording details */
  const handleViewDetail = async (recording: RecordingItem) => {
    setSelectedRecording(recording);
    setDetailModalOpen(true);
    setDetailData(null);
    try {
      const data = await fetchRecordingDetail(recording.id);
      setDetailData(data as unknown as Record<string, unknown>);
    } catch {
      message.error(t('taskStudio.recordings.detail_load_failed'));
    }
  };

  /** convert is Pipeline */
  const handleConvertToPipeline = async (id: number) => {
    setConvertingId(id);
    try {
      const result = await convertRecordingToPipeline(id);
      message.success(t('taskStudio.recordings.pipeline_created', { name: result.name }));
      loadRecordings();
    } catch (err: unknown) {
      const detail = err instanceof Error ? err.message : String(err);
      message.error(t('taskStudio.recordings.convert_failed', { detail }));
    } finally {
      setConvertingId(null);
    }
  };

  /** delete recording */
  const handleDelete = async (id: number) => {
    try {
      await deleteRecording(id);
      message.success(t('taskStudio.recordings.deleted'));
      loadRecordings();
    } catch (err: unknown) {
      const detail = err instanceof Error ? err.message : String(err);
      message.error(t('taskStudio.recordings.delete_failed', { detail }));
    }
  };

  /** playback recording (C2 Stepper) */
  const handlePlayback = async (recording: RecordingItem) => {
    try {
      const detail: RecordingDetail = await fetchRecordingDetail(recording.id);
      const events = detail.events || detail.recording_data?.events || [];
      if (events.length === 0) {
        message.warning(t('pipelineEditor.msg_recording_no_events'));
        return;
      }
      setStepperEvents(events);
      setStepperName(recording.name);
      setStepperOpen(true);
    } catch {
      message.error(t('pipelineEditor.msg_recording_detail_load_failed'));
    }
  };

  /** format transform when long */
  const formatDuration = (seconds: number): string => {
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}m ${s}s`;
  };

  /** judge is no can convert ( has pipeline_json data ) */
  const canConvert = (recording: RecordingItem): boolean => {
    return !!recording.pipeline_json && Object.keys(recording.pipeline_json).length > 0;
  };

  const columns = [
    {
      title: t('taskStudio.recordings.col.name'),
      dataIndex: 'name',
      key: 'name',
      render: (text: string) => <Text strong>{text}</Text>,
    },
    {
      title: t('taskStudio.recordings.col.duration'),
      dataIndex: 'duration',
      key: 'duration',
      width: 100,
      render: (val: number) => (
        <span>
          <ClockCircleOutlined className="gaf-mr-xs" />
          {formatDuration(val)}
        </span>
      ),
      sorter: (a: RecordingItem, b: RecordingItem) => a.duration - b.duration,
    },
    {
      title: t('taskStudio.recordings.col.event_count'),
      dataIndex: 'event_count',
      key: 'event_count',
      width: 80,
      render: (val: number) => val ?? '-',
    },
    {
      title: t('taskStudio.recordings.col.screenshot_count'),
      dataIndex: 'screenshot_count',
      key: 'screenshot_count',
      width: 80,
      render: (val: number) => (
        <span>
          <span aria-hidden="true">
            <FileImageOutlined className="gaf-mr-xs" />
          </span>
          {val}
        </span>
      ),
    },
    {
      title: t('taskStudio.recordings.col.resolution'),
      dataIndex: 'resolution',
      key: 'resolution',
      width: 100,
      render: (val: string) => val || '-',
    },
    {
      title: t('taskStudio.status'),
      key: 'status',
      width: 100,
      render: (_: unknown, record: RecordingItem) => {
        return canConvert(record) ? (
          <Tag color="green">{t('taskStudio.recordings.status.convertible')}</Tag>
        ) : (
          <Tag color="orange">{t('taskStudio.recordings.status.pending')}</Tag>
        );
      },
    },
    {
      title: t('taskStudio.recordings.col.created_at'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (val: string) => (val ? dayjs(val).format('YYYY-MM-DD HH:mm:ss') : '-'),
      sorter: (a: RecordingItem, b: RecordingItem) =>
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    },
    {
      title: t('taskStudio.action'),
      key: 'action',
      width: 240,
      render: (_: unknown, record: RecordingItem) => (
        <div className="gaf-flex-center gaf-gap-xs">
          <Tooltip key="view" title={t('taskStudio.recordings.view_detail')}>
            <Button
              type="link"
              size="small"
              icon={<EyeOutlined />}
              aria-label={t('taskStudio.recordings.view_detail')}
              onClick={() => handleViewDetail(record)}
            />
          </Tooltip>
          <Tooltip key="playback" title="回放 (Stepper)">
            <Button
              type="link"
              size="small"
              icon={<StepForwardOutlined />}
              aria-label="回放"
              onClick={() => handlePlayback(record)}
            />
          </Tooltip>
          {canConvert(record) && (
            <Tooltip key="convert" title={t('taskStudio.recordings.convert_to_pipeline')}>
              <Button
                type="link"
                size="small"
                icon={<ExportOutlined />}
                aria-label={t('taskStudio.recordings.convert_to_pipeline')}
                loading={convertingId === record.id}
                onClick={() => handleConvertToPipeline(record.id)}
              />
            </Tooltip>
          )}
          <Popconfirm
            key="delete"
            title={t('taskStudio.recordings.confirm_delete')}
            onConfirm={() => handleDelete(record.id)}
            okText={t('taskStudio.delete')}
            cancelText={t('taskStudio.cancel')}
            okType="danger"
          >
            <Tooltip title={t('taskStudio.delete')}>
              <Button type="link" size="small" danger icon={<DeleteOutlined />} aria-label={t('taskStudio.delete')} />
            </Tooltip>
          </Popconfirm>
        </div>
      ),
    },
  ];

  return (
    <PageWrapper>
      <Card
        size="small"
        title={
          <Space>
            <span aria-hidden="true">
              <VideoCameraOutlined />
            </span>
            <span>{t('taskStudio.recordings.title')}</span>
          </Space>
        }
        extra={
          <Space>
            <Badge count={recordings.length} showZero color={token.colorPrimary} />
            <Text type="secondary">{t('taskStudio.recordings.count_suffix')}</Text>
          </Space>
        }
      >
        {recordings.length === 0 && !loading ? (
          <Empty description={t('taskStudio.recordings.empty')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <Table
            dataSource={recordings}
            columns={columns}
            rowKey="id"
            loading={loading}
            pagination={{
              pageSize: 10,
              showTotal: (total) => t('taskStudio.recordings.total', { total }),
              showSizeChanger: false,
            }}
            size="middle"
          />
        )}
      </Card>

      {/* 详情弹窗 */}
      <Modal
        title={t('taskStudio.recordings.detail_title', { name: selectedRecording?.name || '' })}
        open={detailModalOpen}
        onCancel={() => {
          setDetailModalOpen(false);
          setDetailData(null);
        }}
        footer={[
          selectedRecording && canConvert(selectedRecording) && (
            <Button
              key="convert"
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={convertingId === selectedRecording?.id}
              onClick={() => selectedRecording && handleConvertToPipeline(selectedRecording.id)}
            >
              {t('taskStudio.recordings.convert_button')}
            </Button>
          ),
          <Button
            key="close"
            onClick={() => {
              setDetailModalOpen(false);
              setDetailData(null);
            }}
          >
            {t('taskStudio.recordings.close')}
          </Button>,
        ]}
        width={640}
      >
        {selectedRecording && (
          <>
            <Row gutter={16} className="gaf-mb-lg">
              <Col span={8}>
                <Statistic
                  title={t('taskStudio.recordings.stat.duration')}
                  value={formatDuration(selectedRecording.duration)}
                  prefix={<ClockCircleOutlined />}
                />
              </Col>
              <Col span={8}>
                <Statistic title={t('taskStudio.recordings.stat.events')} value={selectedRecording.event_count ?? 0} />
              </Col>
              <Col span={8}>
                <Statistic
                  title={t('taskStudio.recordings.stat.screenshots')}
                  value={selectedRecording.screenshot_count}
                  prefix={
                    <span aria-hidden="true">
                      <FileImageOutlined />
                    </span>
                  }
                />
              </Col>
            </Row>

            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="ID">{selectedRecording.id}</Descriptions.Item>
              <Descriptions.Item label={t('taskStudio.recordings.col.resolution')}>
                {selectedRecording.resolution}
              </Descriptions.Item>
              <Descriptions.Item label={t('taskStudio.recordings.col.created_at')}>
                {dayjs(selectedRecording.created_at).format('YYYY-MM-DD HH:mm:ss')}
              </Descriptions.Item>
              <Descriptions.Item label={t('taskStudio.status')}>
                {canConvert(selectedRecording) ? (
                  <Tag color="green">{t('taskStudio.recordings.status.convertible')}</Tag>
                ) : (
                  <Tag color="orange">{t('taskStudio.recordings.status.pending')}</Tag>
                )}
              </Descriptions.Item>
            </Descriptions>

            {detailData && (
              <div className="gaf-mt-lg">
                <Title level={5}>{t('taskStudio.recordings.raw_data_preview')}</Title>
                <pre
                  className="gaf-p-md gaf-text-xs gaf-radius-md gaf-overflow-auto"
                  style={{ background: token.colorFillQuaternary, maxHeight: 300 }}
                >
                  {JSON.stringify(detailData, null, 2)}
                </pre>
              </div>
            )}
          </>
        )}
      </Modal>

      {/* C2 回放 Stepper Modal */}
      <RecordingStepper
        open={stepperOpen}
        events={stepperEvents}
        recordingName={stepperName}
        onClose={() => setStepperOpen(false)}
      />
    </PageWrapper>
  );
}

export default RecordingsPage;
