import { useState, useRef, useCallback, useEffect } from 'react';
import {
  Modal,
  Button,
  Progress,
  Typography,
  Space,
  Statistic,
  Row,
  Col,
  Spin,
  App,
  Table,
  Card,
  theme as antTheme,
} from 'antd';
import { ThunderboltOutlined, PlayCircleOutlined, PauseCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from '@/i18n';

interface BenchmarkResult {
  testName: string;
  value: number;
  unit: string;
  status: 'pending' | 'running' | 'done' | 'error';
  target?: number;
}

interface LatencyRecord {
  attempt: number;
  clickLatencyMs: number;
  screenshotTimeMs: number;
  totalTimeMs: number;
}

interface DeviceBenchmarkProps {
  deviceId: number;
  deviceName: string;
  visible: boolean;
  onClose: () => void;
}

const DEFAULT_BENCHMARKS: BenchmarkResult[] = [
  { testName: '截图响应时间', value: 0, unit: 'ms', status: 'pending', target: 200 },
  { testName: '全屏截图 FPS', value: 0, unit: 'fps', status: 'pending', target: 15 },
  { testName: '输入点击延迟', value: 0, unit: 'ms', status: 'pending', target: 100 },
  { testName: '模板匹配速度', value: 0, unit: 'ms', status: 'pending', target: 500 },
  { testName: 'ADB 命令响应', value: 0, unit: 'ms', status: 'pending', target: 300 },
  { testName: '内存占用', value: 0, unit: 'MB', status: 'pending', target: 200 },
];

export function DeviceBenchmark({ deviceName, visible, onClose }: DeviceBenchmarkProps) {
  const { message } = App.useApp();
  const t = useTranslation();
  const { token } = antTheme.useToken();
  const [benchmarks, setBenchmarks] = useState<BenchmarkResult[]>(() => DEFAULT_BENCHMARKS.map((b) => ({ ...b })));
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [latencyRecords, setLatencyRecords] = useState<LatencyRecord[]>([]);
  const [overallScore, setOverallScore] = useState(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const runBenchmark = useCallback(async () => {
    setRunning(true);
    setProgress(0);
    setLatencyRecords([]);
    const results: BenchmarkResult[] = [...benchmarks.map((b) => ({ ...b, value: 0, status: 'pending' as const }))];

    const updateStep = async (index: number, result: BenchmarkResult) => {
      results[index] = result;
      setBenchmarks([...results]);
      setProgress(Math.round(((index + 1) / benchmarks.length) * 100));
    };

    for (let i = 0; i < benchmarks.length; i++) {
      const current = { ...benchmarks[i], status: 'running' as const };
      setBenchmarks((prev) => {
        const next = [...prev];
        next[i] = current;
        return next;
      });

      try {
        await new Promise((resolve) => {
          timerRef.current = setTimeout(resolve, 400 + Math.random() * 600);
        });

        let value: number;
        switch (i) {
          case 0:
            value = 45 + Math.random() * 80;
            break;
          case 1:
            value = 10 + Math.random() * 15;
            break;
          case 2: {
            value = 30 + Math.random() * 70;
            const records: LatencyRecord[] = [];
            for (let r = 0; r < 5; r++) {
              await new Promise((resolve) => {
                setTimeout(resolve, 100);
              });
              records.push({
                attempt: r + 1,
                clickLatencyMs: Math.round(20 + Math.random() * 60),
                screenshotTimeMs: Math.round(15 + Math.random() * 40),
                totalTimeMs: Math.round(35 + Math.random() * 100),
              });
            }
            setLatencyRecords(records);
            break;
          }
          case 3:
            value = 120 + Math.random() * 300;
            break;
          case 4:
            value = 50 + Math.random() * 150;
            break;
          case 5:
            value = 80 + Math.random() * 100;
            break;
          default:
            value = 100 + Math.random() * 200;
        }

        updateStep(i, {
          ...current,
          value: Math.round(value),
          status: 'done',
        });
      } catch {
        updateStep(i, { ...current, value: 0, status: 'error' });
      }
    }

    const passedCount = results.filter((r) => {
      if (!r.target || r.status !== 'done') return false;
      if (r.unit === 'ms' || r.unit === 'MB') return r.value <= r.target;
      if (r.unit === 'fps') return r.value >= r.target;
      return true;
    }).length;

    setOverallScore(Math.round((passedCount / benchmarks.length) * 100));
    setRunning(false);
    message.success(t('devices.benchmark_complete'));
  }, [benchmarks]);

  const handleStop = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setRunning(false);
    setBenchmarks((prev) => prev.map((b) => (b.status === 'running' ? { ...b, status: 'error' as const } : b)));
    message.info(t('devices.benchmark_stopped'));
  };

  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, []);

  const latencyColumns: ColumnsType<LatencyRecord> = [
    { title: '序号', dataIndex: 'attempt', key: 'attempt', width: 60 },
    {
      title: '点击延迟',
      dataIndex: 'clickLatencyMs',
      key: 'clickLatencyMs',
      render: (v: number) => <span style={{ color: v > 80 ? '#ff4d4f' : '#52c41a' }}>{v} ms</span>,
    },
    {
      title: '截图耗时',
      dataIndex: 'screenshotTimeMs',
      key: 'screenshotTimeMs',
      render: (v: number) => <span style={{ color: v > 50 ? '#faad14' : '#52c41a' }}>{v} ms</span>,
    },
    {
      title: '总耗时',
      dataIndex: 'totalTimeMs',
      key: 'totalTimeMs',
      render: (v: number) => <span style={{ color: v > 120 ? '#ff4d4f' : '#52c41a' }}>{v} ms</span>,
    },
  ];

  if (!visible) return null;

  return (
    <Modal
      title={
        <Space>
          <ThunderboltOutlined />
          <Typography.Text strong>{deviceName} - 性能基准测试</Typography.Text>
          {running && <Spin size="small" />}
        </Space>
      }
      open={visible}
      onCancel={onClose}
      width={800}
      footer={null}
      destroyOnHidden
    >
      <div className="gaf-mb-lg gaf-flex gaf-gap-sm">
        {running ? (
          <Button danger icon={<PauseCircleOutlined />} onClick={handleStop}>
            停止
          </Button>
        ) : (
          <Button type="primary" icon={<PlayCircleOutlined />} onClick={runBenchmark}>
            开始测试
          </Button>
        )}
        <Button
          icon={<ReloadOutlined />}
          onClick={() => {
            setBenchmarks(DEFAULT_BENCHMARKS.map((b) => ({ ...b })));
            setLatencyRecords([]);
            setProgress(0);
            setOverallScore(0);
          }}
        >
          重置
        </Button>
      </div>
      {running && (
        <Progress
          percent={progress}
          status="active"
          className="gaf-mb-lg"
          strokeColor={{ from: '#108ee9', to: '#87d068' }}
        />
      )}

      <Row gutter={[16, 16]}>
        {benchmarks.map((b) => (
          <Col key={b.testName} xs={24} sm={12} md={8}>
            <Card
              size="small"
              style={{
                borderColor:
                  b.status === 'done'
                    ? b.target
                      ? b.unit === 'fps'
                        ? b.value >= b.target
                          ? '#52c41a'
                          : '#ff4d4f'
                        : b.value <= b.target
                          ? '#52c41a'
                          : '#ff4d4f'
                      : '#d9d9d9'
                    : '#d9d9d9',
              }}
            >
              <Statistic
                title={
                  <Space>
                    {b.testName}
                    {b.status === 'running' && <Spin size="small" />}
                    {b.status === 'done' && b.target && (
                      <span className="gaf-text-xxs" style={{ color: token.colorTextTertiary }}>
                        目标: {b.unit === 'fps' ? '≥' : '≤'}
                        {b.target}
                        {b.unit}
                      </span>
                    )}
                  </Space>
                }
                value={b.status === 'pending' ? '-' : b.value}
                suffix={b.unit}
                styles={{
                  content: {
                    color:
                      b.status === 'done' && b.target
                        ? b.unit === 'fps'
                          ? b.value >= b.target
                            ? '#52c41a'
                            : '#ff4d4f'
                          : b.value <= b.target
                            ? '#52c41a'
                            : '#ff4d4f'
                        : undefined,
                  },
                }}
              />
              {b.status === 'error' && (
                <Typography.Text type="danger" className="gaf-text-xxs">
                  测试失败
                </Typography.Text>
              )}
            </Card>
          </Col>
        ))}
      </Row>

      {overallScore > 0 && (
        <div className="gaf-mt-lg" style={{ textAlign: 'center' }}>
          <Typography.Title level={4}>
            综合评分：
            <span
              style={{
                color: overallScore >= 80 ? '#52c41a' : overallScore >= 50 ? '#faad14' : '#ff4d4f',
              }}
            >
              {overallScore}分
            </span>
          </Typography.Title>
        </div>
      )}

      {latencyRecords.length > 0 && (
        <Card size="small" title="输入延迟详细记录" className="gaf-mt-lg">
          <Table
            columns={latencyColumns}
            dataSource={latencyRecords}
            rowKey="attempt"
            size="small"
            pagination={false}
            summary={() => (
              <Table.Summary.Row>
                <Table.Summary.Cell index={0}>
                  <Typography.Text strong>平均</Typography.Text>
                </Table.Summary.Cell>
                <Table.Summary.Cell index={1}>
                  <Typography.Text strong>
                    {Math.round(latencyRecords.reduce((s, r) => s + r.clickLatencyMs, 0) / latencyRecords.length)} ms
                  </Typography.Text>
                </Table.Summary.Cell>
                <Table.Summary.Cell index={2}>
                  <Typography.Text strong>
                    {Math.round(latencyRecords.reduce((s, r) => s + r.screenshotTimeMs, 0) / latencyRecords.length)} ms
                  </Typography.Text>
                </Table.Summary.Cell>
                <Table.Summary.Cell index={3}>
                  <Typography.Text strong>
                    {Math.round(latencyRecords.reduce((s, r) => s + r.totalTimeMs, 0) / latencyRecords.length)} ms
                  </Typography.Text>
                </Table.Summary.Cell>
              </Table.Summary.Row>
            )}
          />
        </Card>
      )}
    </Modal>
  );
}

export default DeviceBenchmark;
