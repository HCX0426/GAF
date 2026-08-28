/**
 * UnattendedControl — unattended mode status + control panel.
 *
 * Shows the current unattended mode_status (running / paused / stopped),
 * active session count, and provides pause/resume/stop buttons for the
 * first active session. Backend: /scheduler/unattended/*.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { Card, Tag, Button, Space, Spin, Empty, Typography, App } from 'antd';
import { PlayCircleOutlined, PauseCircleOutlined, StopOutlined } from '@ant-design/icons';
import {
  fetchUnattendedStatus,
  pauseUnattended,
  resumeUnattended,
  stopUnattended,
  type ActiveSessionEntry,
} from '@/api/misc';
import { useTranslation } from '@/i18n';

const { Text } = Typography;

export function UnattendedControl() {
  const t = useTranslation();
  const { message } = App.useApp();
  const [modeStatus, setModeStatus] = useState<string>('stopped');
  const [sessions, setSessions] = useState<ActiveSessionEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);

  /** mode status → tag color + label. Memoized on t so labels re-render on locale change. */
  const MODE_META = useMemo<Record<string, { color: string; label: string }>>(
    () => ({
      running: { color: 'processing', label: t('unattendedStrategy.control_running') },
      paused: { color: 'warning', label: t('unattendedStrategy.control_paused') },
      stopped: { color: 'default', label: t('unattendedStrategy.control_stopped') },
    }),
    [t],
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchUnattendedStatus();
      setModeStatus(res?.mode_status || 'stopped');
      setSessions(res?.active_sessions || []);
    } catch {
      setModeStatus('stopped');
      setSessions([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const activeSession = sessions[0];
  const meta = MODE_META[modeStatus] || MODE_META.stopped;

  const handlePause = async () => {
    if (!activeSession) return;
    setActing(true);
    try {
      await pauseUnattended(activeSession.id);
      message.success(t('unattendedStrategy.control_paused_msg'));
      await load();
    } catch {
      message.error(t('unattendedStrategy.control_pause_failed'));
    } finally {
      setActing(false);
    }
  };

  const handleResume = async () => {
    if (!activeSession) return;
    setActing(true);
    try {
      await resumeUnattended(activeSession.id);
      message.success(t('unattendedStrategy.control_resumed_msg'));
      await load();
    } catch {
      message.error(t('unattendedStrategy.control_resume_failed'));
    } finally {
      setActing(false);
    }
  };

  const handleStop = async () => {
    if (!activeSession) return;
    setActing(true);
    try {
      await stopUnattended(activeSession.id, 'manual');
      message.success(t('unattendedStrategy.control_stopped_msg'));
      await load();
    } catch {
      message.error(t('unattendedStrategy.control_stop_failed'));
    } finally {
      setActing(false);
    }
  };

  if (loading) {
    return (
      <Card title={t('unattendedStrategy.control_title')} size="small">
        <div className="gaf-p-lg" style={{ textAlign: 'center' }}>
          <Spin />
        </div>
      </Card>
    );
  }

  return (
    <Card title={t('unattendedStrategy.control_title')} size="small">
      {sessions.length === 0 ? (
        <Empty description={t('unattendedStrategy.control_no_session')} image={Empty.PRESENTED_IMAGE_SIMPLE}>
          <Text type="secondary" className="gaf-text-xs">
            {t('unattendedStrategy.control_go_scheduler')}
          </Text>
        </Empty>
      ) : (
        <Space orientation="vertical" style={{ width: '100%' }}>
          <Space>
            <Tag color={meta.color}>{meta.label}</Tag>
            <Text type="secondary" className="gaf-text-xs">
              {activeSession?.game_profile_name || t('unattendedStrategy.control_unknown_profile')}
            </Text>
          </Space>
          <Text type="secondary" className="gaf-text-xs">
            {t('unattendedStrategy.control_active_summary', {
              sessions: sessions.length,
              devices: activeSession?.total_devices ?? 0,
              accounts: activeSession?.total_accounts ?? 0,
            })}
          </Text>
          <Space>
            {modeStatus === 'running' && (
              <Button size="small" icon={<PauseCircleOutlined />} onClick={handlePause} loading={acting}>
                {t('unattendedStrategy.control_pause')}
              </Button>
            )}
            {modeStatus === 'paused' && (
              <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={handleResume} loading={acting}>
                {t('unattendedStrategy.control_resume')}
              </Button>
            )}
            <Button size="small" danger icon={<StopOutlined />} onClick={handleStop} loading={acting}>
              {t('unattendedStrategy.control_stop')}
            </Button>
          </Space>
        </Space>
      )}
    </Card>
  );
}

export default UnattendedControl;
