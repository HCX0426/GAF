import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { Slider, Button, Space, Typography, Card, Spin, Empty, theme as antTheme } from 'antd';
import { PlayCircleOutlined, PauseOutlined } from '@ant-design/icons';
import StepProgressBar from '@/components/Pipeline/StepProgressBar';
import type { StepInfo } from '@/components/Pipeline/StepProgressBar';
import GafCanvasOverlay from '@/components/Canvas/GafCanvasOverlay';
import type { Annotation } from '@/components/Canvas/GafCanvasOverlay';
import type { StepStatus } from '@/types/models';
import { fetchExecutionReplay } from '@/api/executions';
import { useTranslation } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';

interface ExecutionFrame {
  index: number;
  imageBase64: string;
  timestamp: string;
  stepIndex: number;
}

interface ExecutionStep {
  index: number;
  name: string;
  status: StepStatus;
  duration?: number;
  frameStart: number;
  frameEnd: number;
}

interface KeyframeMark {
  position: number;
  color: string;
  label: string;
}

const CANVAS_WIDTH = 960;
const CANVAS_HEIGHT = 540;

const SPEED_OPTIONS = [0.5, 1, 2, 4];

function generateKeyframes(
  steps: ExecutionStep[],
  totalFrames: number,
  tokens: { colorPrimary: string; colorSuccess: string; colorError: string; colorTextTertiary: string },
  t: (key: string, params?: Record<string, string | number>) => string,
): KeyframeMark[] {
  const marks: KeyframeMark[] = [
    { position: 0, color: tokens.colorPrimary, label: t('executionReplay.keyframe_start') },
  ];

  steps.forEach((step) => {
    const pos = Math.round((step.frameStart / totalFrames) * 100);
    let color = tokens.colorSuccess;
    if (step.status === 'failed') color = tokens.colorError;
    else if (step.status === 'running') color = tokens.colorPrimary;
    else if (step.status === 'pending') color = tokens.colorTextTertiary;
    marks.push({ position: pos, color, label: t('executionReplay.keyframe_step', { index: step.index }) });
  });

  marks.push({ position: 100, color: tokens.colorTextTertiary, label: t('executionReplay.keyframe_end') });
  return marks;
}

export function ExecutionReplayPage() {
  const { executionId } = useParams<{ executionId: string }>();
  const t = useTranslation();
  const [loading, setLoading] = useState(true);
  const [frames, setFrames] = useState<ExecutionFrame[]>([]);
  const [steps, setSteps] = useState<ExecutionStep[]>([]);
  const [currentPosition, setCurrentPosition] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playSpeed, setPlaySpeed] = useState(1);
  const playTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const { token } = antTheme.useToken();

  useEffect(() => {
    if (!executionId) return;
    let cancelled = false;
    const loadReplayData = async () => {
      setLoading(true);
      try {
        const data = (await fetchExecutionReplay(executionId)) as {
          frames?: ExecutionFrame[];
          steps?: ExecutionStep[];
        };
        if (!cancelled) {
          setFrames(data.frames ?? []);
          setSteps(data.steps ?? []);
        }
      } catch {
        // API unavailable when keep empty data
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };
    loadReplayData();
    return () => {
      cancelled = true;
    };
  }, [executionId]);

  const totalFrames = frames.length;
  const currentFrame = frames[Math.floor((currentPosition / 100) * Math.max(totalFrames - 1, 0))] || null;
  const currentStepIndex = currentFrame ? currentFrame.stepIndex : 0;

  const stepInfos: StepInfo[] = steps.map((s) => ({
    index: s.index,
    name: s.name,
    status: s.status,
    duration: s.duration,
  }));

  const keyframes = generateKeyframes(steps, totalFrames, token, t);

  const sliderMarks: Record<number, React.ReactNode> = {};
  keyframes.forEach((kf) => {
    sliderMarks[kf.position] = (
      <div
        style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: kf.color,
          margin: '0 auto',
        }}
        title={kf.label}
      />
    );
  });

  const stopPlayback = useCallback(() => {
    if (playTimerRef.current) {
      clearInterval(playTimerRef.current);
      playTimerRef.current = null;
    }
    setIsPlaying(false);
  }, []);

  const startPlayback = useCallback(() => {
    if (isPlaying) return;
    setIsPlaying(true);

    const intervalMs = 1000 / playSpeed;
    playTimerRef.current = setInterval(() => {
      setCurrentPosition((prev) => {
        if (prev >= 100) {
          stopPlayback();
          return 100;
        }
        return prev + 1;
      });
    }, intervalMs);
  }, [isPlaying, playSpeed, stopPlayback]);

  const togglePlayback = useCallback(() => {
    if (isPlaying) {
      stopPlayback();
    } else {
      if (currentPosition >= 100) {
        setCurrentPosition(0);
      }
      startPlayback();
    }
  }, [isPlaying, stopPlayback, startPlayback, currentPosition]);

  useEffect(() => {
    return () => {
      if (playTimerRef.current) {
        clearInterval(playTimerRef.current);
      }
    };
  }, []);

  const handleSpeedChange = useCallback(
    (speed: number) => {
      setPlaySpeed(speed);
      if (isPlaying) {
        stopPlayback();
        setTimeout(() => {
          if (playTimerRef.current) return;
          setIsPlaying(true);
          const intervalMs = 1000 / speed;
          playTimerRef.current = setInterval(() => {
            setCurrentPosition((prev) => {
              if (prev >= 100) {
                stopPlayback();
                return 100;
              }
              return prev + 1;
            });
          }, intervalMs);
        }, 0);
      }
    },
    [isPlaying, stopPlayback],
  );

  const replayAnnotations: Annotation[] = [];
  if (currentFrame) {
    const step = steps[currentFrame.stepIndex];
    if (step) {
      replayAnnotations.push({
        id: 'step_marker',
        type: 'rect',
        x: CANVAS_WIDTH / 2 - 20,
        y: CANVAS_HEIGHT - 60,
        width: 40,
        height: 40,
        color: step.status === 'failed' ? token.colorError : token.colorPrimary,
        label: t('executionReplay.step_label', { index: step.index }),
      });
    }
  }

  /** Build debug info for canvas overlay */
  const debugInfo = {
    fps: playSpeed * 30,
    currentStep: steps[currentStepIndex]?.name ?? '-',
    deviceName: `Execution ${executionId}`,
    resolution: `${CANVAS_WIDTH}x${CANVAS_HEIGHT}`,
  };

  return (
    <PageWrapper>
      <div className="gaf-flex-col gaf-gap-md gaf-p-lg" style={{ height: 'calc(100vh - 120px)' }}>
        <Spin spinning={loading}>
          <div className="gaf-flex gaf-gap-md gaf-flex-1" style={{ minHeight: 0 }}>
            <Card
              size="small"
              title={
                <Typography.Text ellipsis style={{ maxWidth: 600 }}>
                  {t('executionReplay.card_title', { id: executionId || t('executionReplay.loading') })}
                </Typography.Text>
              }
              className="gaf-flex-1"
            >
              <div
                className="gaf-flex-center gaf-justify-center gaf-position-relative gaf-w-full gaf-radius-md"
                style={{
                  height: CANVAS_HEIGHT,
                  background: token.colorBgLayout,
                  overflow: 'hidden',
                }}
              >
                {currentFrame?.imageBase64 ? (
                  <GafCanvasOverlay
                    width={CANVAS_WIDTH}
                    height={CANVAS_HEIGHT}
                    annotations={replayAnnotations}
                    imageBase64={currentFrame.imageBase64}
                    className="gaf-w-full gaf-h-full"
                    style={{ border: 'none' }}
                    showCrosshair={true}
                    showDebugInfo={true}
                    debugInfo={debugInfo}
                  />
                ) : (
                  <div className="gaf-text-center" style={{ color: token.colorTextSecondary }}>
                    <Typography.Text className="gaf-text-lg" style={{ color: token.colorText }}>
                      {t('executionReplay.frame_label', { index: currentFrame?.index ?? 0 })}
                    </Typography.Text>
                    <br />
                    <Typography.Text className="gaf-text-xs" style={{ color: token.colorText }}>
                      {currentFrame?.timestamp || t('executionReplay.waiting_data')}
                    </Typography.Text>
                  </div>
                )}
              </div>
            </Card>

            <Card
              size="small"
              title={t('executionReplay.steps_title')}
              className="gaf-overflow-auto gaf-flex-shrink-0"
              style={{ width: 240 }}
            >
              {steps.length > 0 ? (
                <StepProgressBar steps={stepInfos} currentStepIndex={currentStepIndex} />
              ) : (
                <Empty description={t('executionReplay.empty_steps')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </Card>
          </div>

          <Card size="small" className="gaf-flex-shrink-0">
            <div className="gaf-flex-center gaf-gap-md">
              <Button
                type="primary"
                shape="circle"
                icon={isPlaying ? <PauseOutlined /> : <PlayCircleOutlined />}
                onClick={togglePlayback}
                disabled={totalFrames === 0}
                aria-label={isPlaying ? '暂停' : '播放'}
              />
              <Space size={4}>
                {SPEED_OPTIONS.map((speed) => (
                  <Button
                    key={speed}
                    size="small"
                    type={playSpeed === speed ? 'primary' : 'default'}
                    onClick={() => handleSpeedChange(speed)}
                  >
                    {speed}x
                  </Button>
                ))}
              </Space>
              <Typography.Text className="gaf-text-xs" style={{ color: token.colorTextTertiary, minWidth: 60 }}>
                {t('executionReplay.position_label', {
                  pos: currentPosition,
                  current: currentFrame?.index ?? 0,
                  total: totalFrames,
                })}
              </Typography.Text>
              <div className="gaf-flex-1">
                <Slider
                  min={0}
                  max={100}
                  value={currentPosition}
                  onChange={(val) => {
                    setCurrentPosition(val);
                    if (isPlaying) {
                      stopPlayback();
                    }
                  }}
                  marks={sliderMarks}
                  tooltip={{ formatter: (v) => `${v}%` }}
                />
              </div>
            </div>
          </Card>
        </Spin>
      </div>
    </PageWrapper>
  );
}

export default ExecutionReplayPage;
