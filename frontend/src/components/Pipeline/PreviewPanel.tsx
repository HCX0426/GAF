/**
 * PreviewPanel — Live screenshot preview for Pipeline editor (P-002)
 *
 * Shows real-time screenshots from the selected device with ROI overlay.
 * Uses periodic polling to fetch screenshots (WebSocket stream can be added later).
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Card, Select, Button, Tag, Space, Typography, Spin, App, Tooltip } from 'antd';
import { VideoCameraOutlined, PauseCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { requestScreenshot } from '@/api/devices';
import { useTranslation } from '@/i18n';

const { Text } = Typography;

interface DeviceOption {
  label: string;
  value: number;
}

interface PreviewPanelProps {
  /** List of available devices */
  devices?: DeviceOption[];
}

export function PreviewPanel({ devices = [] }: PreviewPanelProps) {
  const { message } = App.useApp();
  const t = useTranslation();
  const [selectedDevice, setSelectedDevice] = useState<number | null>(null);
  const [screenshot, setScreenshot] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [live, setLive] = useState(false);
  const [fps, setFps] = useState(0);
  const intervalRef = React.useRef<ReturnType<typeof setInterval> | null>(null);
  const frameCountRef = React.useRef(0);
  const fpsTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchScreenshot = useCallback(async (deviceId: number) => {
    try {
      const data = await requestScreenshot(deviceId);
      if (data.screenshot_base64) {
        // Auto-detect MIME from base64 header: JPEG starts with /9j/, PNG with iVBOR
        const mime = data.screenshot_base64.startsWith('/9j/') ? 'image/jpeg' : 'image/png';
        setScreenshot(`data:${mime};base64,${data.screenshot_base64}`);
        frameCountRef.current += 1;
      } else {
        setScreenshot(null);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  // FPS counter
  useEffect(() => {
    fpsTimerRef.current = setInterval(() => {
      setFps(frameCountRef.current);
      frameCountRef.current = 0;
    }, 1000);
    return () => {
      if (fpsTimerRef.current) clearInterval(fpsTimerRef.current);
    };
  }, []);

  // Live mode: auto-refresh
  useEffect(() => {
    if (live && selectedDevice) {
      fetchScreenshot(selectedDevice);
      intervalRef.current = setInterval(() => {
        fetchScreenshot(selectedDevice!);
      }, 2000); // 0.5 fps to avoid overloading
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [live, selectedDevice, fetchScreenshot]);

  // Single capture
  const handleCapture = useCallback(() => {
    if (!selectedDevice) {
      message.warning(t('pipelineEditor.msg_preview_select_device'));
      return;
    }
    setLoading(true);
    fetchScreenshot(selectedDevice);
  }, [selectedDevice, fetchScreenshot, message]);

  // Toggle live mode
  const handleToggleLive = useCallback(() => {
    if (!selectedDevice) {
      message.warning(t('pipelineEditor.msg_preview_select_device'));
      return;
    }
    setLive((prev) => !prev);
  }, [selectedDevice, message]);

  return (
    <div className="gaf-p-md">
      <div className="gaf-mb-md">
        <Text strong>实时预览</Text>
        <Tag color="blue" className="gaf-ml-sm">
          P-002
        </Tag>
      </div>

      <div className="gaf-mb-md">
        <Select
          className="gaf-w-full"
          placeholder="选择设备"
          value={selectedDevice}
          onChange={(v) => {
            setSelectedDevice(v);
            setScreenshot(null);
            setLive(false);
          }}
          options={devices}
          size="small"
          allowClear
          aria-label="选择预览设备"
        />
      </div>

      <div className="gaf-mb-md">
        <Space>
          <Tooltip title="捕获截图">
            <Button
              size="small"
              icon={<ReloadOutlined spin={loading} />}
              onClick={handleCapture}
              loading={loading}
              disabled={!selectedDevice}
            >
              捕获
            </Button>
          </Tooltip>
          <Tooltip title={live ? '停止实时预览' : '开启实时预览'}>
            <Button
              size="small"
              type={live ? 'primary' : 'default'}
              icon={live ? <PauseCircleOutlined /> : <VideoCameraOutlined />}
              onClick={handleToggleLive}
              disabled={!selectedDevice}
            >
              {live ? '停止' : '实时'}
            </Button>
          </Tooltip>
        </Space>
        {live && (
          <Tag color="green" className="gaf-ml-sm">
            {fps} fps
          </Tag>
        )}
      </div>

      <Card
        size="small"
        className="gaf-flex-center"
        style={{ height: 400, justifyContent: 'center', background: '#000', borderRadius: 4 }}
        styles={{
          body: { padding: 0, height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' },
        }}
      >
        {loading && !screenshot ? (
          <Spin description="加载中…" />
        ) : screenshot ? (
          <img
            src={screenshot}
            alt="Device screenshot"
            width={640}
            height={400}
            loading="lazy"
            style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
          />
        ) : (
          <Text style={{ color: '#666' }}>{selectedDevice ? '暂无截图数据' : '请选择设备'}</Text>
        )}
      </Card>
    </div>
  );
}

export default PreviewPanel;
