/**
 * test screenshot modal component
 * run screenshot test on specified device, shows screenshot result, latency, frame rate and other info.
 */
import { useState, useEffect, useCallback } from 'react';
import { Modal, Spin, Alert, Descriptions, Tag, Space, Button, Image, Select } from 'antd';
import { ReloadOutlined, CameraOutlined } from '@ant-design/icons';
import { useDeviceStore } from '@/stores/useDeviceStore';
import { useTranslation } from '@/i18n';
import type { ScreenshotTestResult } from '@/types/models';

/** ScreenshotTester component props */
interface ScreenshotTesterProps {
  /** device ID */
  deviceId: number;
  /** device name */
  deviceName: string;
  /** modal is no open */
  open: boolean;
  /** close modal callback */
  onClose: () => void;
}

/**
 * screenshot latency color
 */
function getLatencyColor(ms: number): string {
  if (ms < 50) return 'green';
  if (ms <= 100) return '#faad14';
  return 'red';
}

/**
 * test screenshot modal
 * shows full screenshot test process: loading, success display, failure prompt
 */
export function ScreenshotTester({ deviceId, deviceName, open, onClose }: ScreenshotTesterProps) {
  const t = useTranslation();
  // Use the store's testScreenshot so the DeviceCard's latency/FPS updates
  // immediately after a test (the store patches the device in-place).
  const testScreenshot = useDeviceStore((s) => s.testScreenshot);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ScreenshotTestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedMethod, setSelectedMethod] = useState<string>('auto');
  // Persist available methods across reloads so the dropdown options do not
  // flicker (and lose the currently-selected entry) while a new frame loads.
  const [availableMethods, setAvailableMethods] = useState<string[]>([]);

  /**
   * execute screenshot test
   *
   * `method` is a required parameter (no closure default) so the callback
   * only depends on `deviceId`. This is critical: if `selectedMethod` were a
   * dependency, changing it would recreate `runTest`, which would retrigger
   * the open-effect below and reset the dropdown back to 'auto'.
   */
  const runTest = useCallback(
    async (method: string) => {
      setLoading(true);
      setError(null);
      try {
        const res = await testScreenshot(deviceId, method);
        if (res.success) {
          setResult(res);
          setAvailableMethods(res.available_methods ?? []);
        } else {
          setError(res.error || '截图测试失败，未知错误');
          setResult(null);
        }
      } catch {
        setError('截图测试请求失败，请检查设备连接');
        setResult(null);
      } finally {
        setLoading(false);
      }
    },
    [deviceId, testScreenshot],
  );

  useEffect(() => {
    if (open) {
      setSelectedMethod('auto');
      setAvailableMethods([]);
      setResult(null);
      setError(null);
      runTest('auto');
    } else {
      setResult(null);
      setError(null);
      setSelectedMethod('auto');
      setAvailableMethods([]);
    }
  }, [open, runTest]);

  const handleMethodChange = (value: string) => {
    setSelectedMethod(value);
    runTest(value);
  };

  const methodOptions = [
    { value: 'auto', label: t('deviceCenter.screenshot_method_auto') },
    ...availableMethods.map((m) => ({ value: m, label: m })),
  ];

  return (
    <Modal
      title={
        <Space>
          <CameraOutlined />
          <span>测试截图 - {deviceName}</span>
        </Space>
      }
      open={open}
      onCancel={onClose}
      width={800}
      centered
      footer={
        <Space>
          <Button onClick={onClose}>关闭</Button>
          <Button type="primary" icon={<ReloadOutlined />} loading={loading} onClick={() => runTest(selectedMethod)}>
            重新测试
          </Button>
        </Space>
      }
      destroyOnHidden
    >
      {loading && (
        <div style={{ textAlign: 'center', padding: '60px 0' }}>
          <Spin size="large" />
          <div className="gaf-mt-lg" style={{ color: '#888' }}>
            正在截图中...
          </div>
        </div>
      )}

      {!loading && error && (
        <Alert type="error" showIcon title="截图测试失败" description={error} className="gaf-mb-lg" />
      )}

      {!loading && result && (
        <div>
          <div className="gaf-mb-lg" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ color: '#666' }}>{t('deviceCenter.screenshot_method')}：</span>
            <Select
              value={selectedMethod}
              options={methodOptions}
              onChange={handleMethodChange}
              style={{ minWidth: 160 }}
              aria-label={t('deviceCenter.screenshot_method')}
            />
          </div>

          <div className="gaf-mb-lg" style={{ textAlign: 'center' }}>
            <Image
              src={`data:${result.screenshot_base64!.startsWith('/9j/') ? 'image/jpeg' : 'image/png'};base64,${result.screenshot_base64}`}
              alt="截图结果"
              style={{ maxWidth: '100%', maxHeight: '70vh', objectFit: 'contain' }}
              wrapperStyle={{ display: 'flex', justifyContent: 'center', maxHeight: '70vh' }}
              fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
            />
          </div>

          <Descriptions bordered size="small" column={2}>
            <Descriptions.Item label="截图延迟" span={1}>
              <Tag color={getLatencyColor(result.latency_ms)}>{result.latency_ms} ms</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="帧率" span={1}>
              {result.fps.toFixed(1)} FPS
            </Descriptions.Item>
            <Descriptions.Item label="分辨率" span={1}>
              {result.resolution.width} × {result.resolution.height}
            </Descriptions.Item>
            <Descriptions.Item label="截图方式" span={1}>
              <Tag>{result.screenshot_method}</Tag>
            </Descriptions.Item>
          </Descriptions>
        </div>
      )}
    </Modal>
  );
}

export default ScreenshotTester;
