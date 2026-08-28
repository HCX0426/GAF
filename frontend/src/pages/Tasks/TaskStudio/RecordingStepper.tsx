/**
 * RecordingStepper component
 * Step-by-step playback of recording events with optional screenshot overlay.
 * C2: Recording playback Stepper
 * C4: Click position overlay on screenshots
 */
import { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { Modal, Steps, Button, Space, Typography, Tag, Empty, Descriptions, theme } from 'antd';
import {
  LeftOutlined,
  RightOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  AimOutlined,
  KeyOutlined,
  CameraOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import type { RecordingEvent } from '@/api/recordings';

const { Text, Paragraph } = Typography;

/** Event type metadata (icon + color + label) */
const eventMeta: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
  click: { icon: <AimOutlined />, color: 'red', label: 'Click' },
  key: { icon: <KeyOutlined />, color: 'blue', label: 'Key' },
  screenshot: { icon: <CameraOutlined />, color: 'green', label: 'Screenshot' },
  wait: { icon: <ClockCircleOutlined />, color: 'orange', label: 'Wait' },
};

interface RecordingStepperProps {
  open: boolean;
  events: RecordingEvent[];
  recordingName: string;
  onClose: () => void;
}

/** Format timestamp to seconds with 2 decimals */
function formatTimestamp(ts: number): string {
  return `${ts.toFixed(2)}s`;
}

/** Format event description */
function formatEventDesc(event: RecordingEvent): string {
  switch (event.event_type) {
    case 'click':
      return `(${event.x}, ${event.y}) ${event.button}`;
    case 'key':
      return event.key;
    case 'screenshot':
      return event.screenshot_path ? event.screenshot_path.split(/[\\/]/).pop() || 'screenshot' : 'screenshot';
    case 'wait':
      return `${event.duration.toFixed(1)}s`;
    default:
      return '';
  }
}

export function RecordingStepper({ open, events, recordingName, onClose }: RecordingStepperProps) {
  const { token } = theme.useToken();
  const [currentStep, setCurrentStep] = useState(0);
  const [autoPlay, setAutoPlay] = useState(false);
  /** Track auto-play interval so it can be cleaned up on unmount */
  const autoPlayIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /** Stop auto-play and clear the interval timer */
  const stopAutoPlay = useCallback(() => {
    if (autoPlayIntervalRef.current) {
      clearInterval(autoPlayIntervalRef.current);
      autoPlayIntervalRef.current = null;
    }
    setAutoPlay(false);
  }, []);

  /** Clear interval on unmount */
  useEffect(() => {
    return () => {
      if (autoPlayIntervalRef.current) clearInterval(autoPlayIntervalRef.current);
    };
  }, []);

  /** Filter to meaningful events (skip raw screenshots for cleaner steps) */
  const meaningfulEvents = useMemo(() => {
    return events.filter((e) => e.event_type !== 'screenshot' || events.length <= 5);
  }, [events]);

  const totalSteps = meaningfulEvents.length;
  const currentEvent = meaningfulEvents[currentStep];

  /** Find the most recent screenshot before current step (for overlay) */
  const currentScreenshot = useMemo(() => {
    if (!currentEvent) return null;
    const allEvents = events;
    const currentIdx = allEvents.indexOf(currentEvent);
    for (let i = currentIdx; i >= 0; i--) {
      if (allEvents[i].event_type === 'screenshot' && allEvents[i].screenshot_path) {
        return allEvents[i];
      }
    }
    return null;
  }, [currentEvent, events]);

  /** Image natural size for accurate overlay scaling (falls back to 1920x1080) */
  const [imgSize, setImgSize] = useState<{ w: number; h: number }>({ w: 1920, h: 1080 });
  const activeUrl = currentScreenshot?.screenshot_url || null;
  useEffect(() => {
    setImgSize({ w: 1920, h: 1080 });
  }, [activeUrl]);

  const handlePrev = () => {
    setCurrentStep((s) => Math.max(0, s - 1));
    stopAutoPlay();
  };

  const handleNext = () => {
    setCurrentStep((s) => Math.min(totalSteps - 1, s + 1));
    stopAutoPlay();
  };

  /** Toggle auto-play (advances every 1 second) */
  const toggleAutoPlay = () => {
    if (autoPlay) {
      stopAutoPlay();
      return;
    }
    if (autoPlayIntervalRef.current) clearInterval(autoPlayIntervalRef.current);
    autoPlayIntervalRef.current = setInterval(() => {
      setCurrentStep((s) => {
        if (s >= totalSteps - 1) {
          stopAutoPlay();
          return s;
        }
        return s + 1;
      });
    }, 1000);
    setAutoPlay(true);
  };

  if (!open) return null;

  return (
    <Modal
      title={`回放: ${recordingName}`}
      open={open}
      onCancel={onClose}
      width={800}
      footer={
        <Space>
          <Button
            icon={autoPlay ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
            onClick={toggleAutoPlay}
            disabled={totalSteps === 0}
          >
            {autoPlay ? '暂停' : '自动播放'}
          </Button>
          <Button onClick={onClose}>关闭</Button>
        </Space>
      }
    >
      {totalSteps === 0 ? (
        <Empty description="无事件可回放" />
      ) : (
        <>
          {/* Step navigation */}
          <div className="gaf-flex-between gaf-mb-lg">
            <Button icon={<LeftOutlined />} onClick={handlePrev} disabled={currentStep === 0}>
              上一步
            </Button>
            <Text strong>
              Step {currentStep + 1} / {totalSteps}
            </Text>
            <Button icon={<RightOutlined />} onClick={handleNext} disabled={currentStep === totalSteps - 1}>
              下一步
            </Button>
          </div>

          {/* Steps timeline */}
          <div className="gaf-mb-lg gaf-overflow-y-auto" style={{ maxHeight: 200 }}>
            <Steps
              current={currentStep}
              orientation="vertical"
              size="small"
              items={meaningfulEvents.map((event, idx) => {
                const meta = eventMeta[event.event_type] || { icon: null, color: 'default', label: event.event_type };
                return {
                  title: (
                    <Space size={4}>
                      <Tag color={meta.color} icon={meta.icon}>
                        {meta.label}
                      </Tag>
                      <Text type="secondary">{formatTimestamp(event.timestamp)}</Text>
                    </Space>
                  ),
                  description: formatEventDesc(event),
                  status: idx === currentStep ? 'process' : idx < currentStep ? 'finish' : 'wait',
                };
              })}
            />
          </div>

          {/* Current event detail + screenshot overlay (C4) */}
          {currentEvent && (
            <div>
              <Descriptions column={2} size="small" bordered className="gaf-mb-lg">
                <Descriptions.Item label="事件类型">
                  <Tag color={eventMeta[currentEvent.event_type]?.color || 'default'}>
                    {eventMeta[currentEvent.event_type]?.label || currentEvent.event_type}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="时间戳">{formatTimestamp(currentEvent.timestamp)}</Descriptions.Item>
                {currentEvent.event_type === 'click' && (
                  <>
                    <Descriptions.Item label="坐标">
                      ({currentEvent.x}, {currentEvent.y})
                    </Descriptions.Item>
                    <Descriptions.Item label="按钮">{currentEvent.button}</Descriptions.Item>
                  </>
                )}
                {currentEvent.event_type === 'key' && (
                  <Descriptions.Item label="按键" span={2}>
                    <Tag color="blue">{currentEvent.key}</Tag>
                  </Descriptions.Item>
                )}
                {currentEvent.event_type === 'wait' && (
                  <Descriptions.Item label="时长" span={2}>
                    {currentEvent.duration.toFixed(2)}s
                  </Descriptions.Item>
                )}
              </Descriptions>

              {/* Screenshot overlay (C4): show screenshot with click position marker */}
              {currentScreenshot && (
                <div>
                  <Text strong>{activeUrl ? '截图 (含点击位置标注):' : '截图路径 (前端暂不可预览):'}</Text>
                  <div
                    className="gaf-mt-sm gaf-radius-md gaf-position-relative"
                    style={{ border: `1px solid ${token.colorBorder}`, overflow: 'hidden' }}
                  >
                    {activeUrl ? (
                      <div className="gaf-position-relative" style={{ background: token.colorFillQuaternary }}>
                        <img
                          src={activeUrl}
                          alt="recording screenshot"
                          style={{ width: '100%', display: 'block' }}
                          onLoad={(e) => {
                            const el = e.currentTarget;
                            if (el.naturalWidth) setImgSize({ w: el.naturalWidth, h: el.naturalHeight });
                          }}
                        />
                        {/* C4 Overlay: click position marker (scaled to real image size) */}
                        {currentEvent.event_type === 'click' && (
                          <div
                            className="gaf-position-absolute"
                            style={{
                              left: `${(currentEvent.x / imgSize.w) * 100}%`,
                              top: `${(currentEvent.y / imgSize.h) * 100}%`,
                              transform: 'translate(-50%, -50%)',
                              zIndex: 10,
                            }}
                          >
                            <div
                              style={{
                                width: 24,
                                height: 24,
                                borderRadius: '50%',
                                border: '3px solid red',
                                backgroundColor: 'rgba(255, 0, 0, 0.2)',
                                boxShadow: '0 0 8px rgba(255, 0, 0, 0.6)',
                              }}
                            />
                            <div
                              className="gaf-position-absolute"
                              style={{
                                top: '50%',
                                left: '50%',
                                width: 4,
                                height: 4,
                                borderRadius: '50%',
                                backgroundColor: 'red',
                                transform: 'translate(-50%, -50%)',
                              }}
                            />
                          </div>
                        )}
                      </div>
                    ) : (
                      <div
                        className="gaf-flex-center gaf-justify-center gaf-position-relative"
                        style={{
                          background: token.colorFillQuaternary,
                          height: 300,
                        }}
                      >
                        <Text type="secondary">截图需通过后端 URL 访问</Text>
                        <Paragraph
                          type="secondary"
                          className="gaf-m-0 gaf-text-xxs gaf-position-absolute"
                          style={{ bottom: 8, left: 8 }}
                        >
                          {currentScreenshot.screenshot_path}
                        </Paragraph>
                      </div>
                    )}
                  </div>
                  <Text type="secondary" className="gaf-text-xxs">
                    红色圆圈标注点击位置 (C4 Overlay)。
                    {activeUrl ? '截图按实际分辨率缩放。' : '截图比例按 1920x1080 计算。'}
                  </Text>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </Modal>
  );
}

export default RecordingStepper;
