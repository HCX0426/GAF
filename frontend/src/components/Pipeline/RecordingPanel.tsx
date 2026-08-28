import { useState, useCallback, useRef, useEffect } from 'react';
import { Button, App, Typography, Badge } from 'antd';
import { PlayCircleOutlined, StopOutlined } from '@ant-design/icons';
import { useTranslation } from '@/i18n';
import { createRecording, updateRecording, convertRecordingToPipeline } from '@/api/recordings';
import type { RecordingEvent } from '@/api/recordings';

type RecordingStatus = 'idle' | 'recording' | 'converting';

/** F010 fix: map lookup replaces nested ternary for status label */
const RECORDING_STATUS_LABEL: Record<RecordingStatus, string> = {
  idle: '就绪',
  recording: '录制中',
  converting: '转换中',
};

interface RecordingPanelProps {
  onRecordingComplete?: (pipelineJSON: Record<string, unknown>) => void;
}

export function RecordingPanel({ onRecordingComplete }: RecordingPanelProps) {
  const { message } = App.useApp();
  const t = useTranslation();
  const [status, setStatus] = useState<RecordingStatus>('idle');
  const [eventCount, setEventCount] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const recordingIdRef = useRef<number | null>(null);
  const eventsRef = useRef<RecordingEvent[]>([]);
  const elapsedIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const eventIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearIntervals = useCallback(() => {
    if (elapsedIntervalRef.current) {
      clearInterval(elapsedIntervalRef.current);
      elapsedIntervalRef.current = null;
    }
    if (eventIntervalRef.current) {
      clearInterval(eventIntervalRef.current);
      eventIntervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      clearIntervals();
    };
  }, [clearIntervals]);

  const recordEvent = useCallback((event: RecordingEvent) => {
    eventsRef.current.push(event);
    setEventCount(eventsRef.current.length);
  }, []);

  const startRecording = useCallback(async () => {
    eventsRef.current = [];
    setEventCount(0);
    setElapsed(0);
    try {
      const recording = await createRecording({
        name: `录制 ${new Date().toLocaleString()}`,
        recording_data: { events: [], name: 'recording', screenshot_dir: '' },
      });
      recordingIdRef.current = recording.id;
      setStatus('recording');
      elapsedIntervalRef.current = setInterval(() => {
        setElapsed((prev) => prev + 1);
      }, 1000);
      // Demo: record a sample click event every second so the recording can be converted.
      // In production this should be replaced by real input events from the device bridge.
      eventIntervalRef.current = setInterval(() => {
        recordEvent({
          event_type: 'click',
          timestamp: elapsed,
          x: 100 + Math.floor(Math.random() * 200),
          y: 100 + Math.floor(Math.random() * 200),
          button: 'left',
          key: '',
          screenshot_path: '',
          duration: 0,
        });
      }, 1000);
      message.success(t('pipelineEditor.msg_recording_started'));
    } catch (err: unknown) {
      const detail = err instanceof Error ? err.message : String(err);
      message.error(`${t('pipelineEditor.msg_recording_convert_failed')}: ${detail}`);
    }
  }, [message, t, clearIntervals, recordEvent, elapsed]);

  const stopRecording = useCallback(async () => {
    clearIntervals();
    const recordingId = recordingIdRef.current;
    if (!recordingId) {
      message.error(t('pipelineEditor.msg_recording_convert_failed'));
      setStatus('idle');
      return;
    }
    setStatus('converting');
    message.info(t('pipelineEditor.msg_recording_converting'));
    try {
      await updateRecording(recordingId, {
        recording_data: { events: eventsRef.current, name: 'recording', screenshot_dir: '' },
        duration: elapsed,
      });
      const pipeline = await convertRecordingToPipeline(recordingId);
      if (onRecordingComplete) {
        onRecordingComplete(pipeline);
      }
      message.success(t('pipelineEditor.msg_recording_converted'));
    } catch (err: unknown) {
      const detail = err instanceof Error ? err.message : String(err);
      message.error(`${t('pipelineEditor.msg_recording_convert_failed')}: ${detail}`);
    }
    recordingIdRef.current = null;
    eventsRef.current = [];
    setStatus('idle');
  }, [clearIntervals, elapsed, message, onRecordingComplete, t]);

  return (
    <div
      className="gaf-flex-center gaf-gap-md gaf-py-md gaf-px-lg"
      style={{ position: 'absolute', top: 12, right: 12, zIndex: 10, background: 'rgba(0,0,0,0.75)', borderRadius: 8 }}
    >
      <Badge status={status === 'recording' ? 'processing' : 'default'} />
      <Typography.Text style={{ color: '#fff', fontSize: 13 }}>{RECORDING_STATUS_LABEL[status]}</Typography.Text>
      <Typography.Text className="gaf-text-xxs" style={{ color: '#aaa' }}>
        {eventCount} 事件 | {elapsed}s
      </Typography.Text>
      {status === 'idle' ? (
        <Button size="small" type="primary" danger icon={<PlayCircleOutlined />} onClick={startRecording}>
          开始录制
        </Button>
      ) : (
        <Button size="small" icon={<StopOutlined />} onClick={stopRecording} disabled={status === 'converting'}>
          停止
        </Button>
      )}
    </div>
  );
}

export default RecordingPanel;
