import { useState, useCallback, useEffect, useMemo } from 'react';
import {
  Badge,
  Button,
  Card,
  Empty,
  Modal,
  Select,
  Space,
  Switch,
  Tooltip,
  Tag,
  App,
  Typography,
  Segmented,
  theme,
} from 'antd';
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  StopOutlined,
  PlusOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useUnattendedStore } from '@/stores/useUnattendedStore';
import { classifyError } from '@/utils/errorHandler';
import { useTranslation } from '@/i18n';
import { fetchGameProfiles } from '@/api/gameProfiles';
import { fetchRotationRules } from '@/api/accounts';
import { fetchMultiGameMode, updateMultiGameMode } from '@/api/settings';
import type { GameProfile, RotationRule, UnattendedSession } from '@/types/models';

/**
 * Unattended control bar (P-011 multi-session parallel).
 *
 * Replaces the single global switch with:
 *  - A "Start new session" header with a GameProfile selector + Start button
 *  - A list of active session cards, each with its own Pause/Resume/Stop
 *
 * Each session is scoped to a GameProfile. The backend enforces one active
 * session per profile (409 Conflict), so the UI filters the profile dropdown
 * to exclude profiles that already have a running session.
 */
export function UnattendedControlBar() {
  const t = useTranslation();
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const {
    sessions,
    preflightLoading,
    startUnattended,
    stopUnattended,
    pauseUnattended,
    resumeUnattended,
    fetchPreflight,
  } = useUnattendedStore();

  /** Available game profiles (loaded once on mount). */
  const [profiles, setProfiles] = useState<GameProfile[]>([]);
  /** Currently selected profile id for starting a new session. */
  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(null);
  /** Switch operation loading state (preflight + start). */
  const [startLoading, setStartLoading] = useState(false);
  /** Emergency stop modal visibility + target session. */
  const [emergencyTarget, setEmergencyTarget] = useState<UnattendedSession | null>(null);
  /** Selected emergency stop reason. */
  const [emergencyReason, setEmergencyReason] = useState<string>('');
  /** P-011 Spec A: multi-game parallel mode toggle (false = single mode). */
  const [multiGameMode, setMultiGameMode] = useState<boolean>(false);
  /** Loading state for the multi-game mode toggle. */
  const [multiGameLoading, setMultiGameLoading] = useState<boolean>(false);
  /** Available rotation rules (loaded once on mount). */
  const [rotationRules, setRotationRules] = useState<RotationRule[]>([]);
  /** Currently selected rotation rule id for starting a new session (null = no rotation). */
  const [selectedRotationRuleId, setSelectedRotationRuleId] = useState<number | null>(null);
  /** Loop rotation switch — keep dispatching after the account chain completes. */
  const [loopRotation, setLoopRotation] = useState<boolean>(false);

  /** Emergency stop reason options (i18n-driven). */
  const EMERGENCY_REASONS = [
    { label: t('dashboard.reason_device_error'), value: 'device_error' },
    { label: t('dashboard.reason_account_risk'), value: 'account_risk' },
    { label: t('dashboard.reason_manual_intervention'), value: 'manual_intervention' },
    { label: t('dashboard.reason_maintenance'), value: 'maintenance' },
    { label: t('dashboard.reason_other'), value: 'other' },
  ];

  /** Load game profiles + multi-game mode flag + rotation rules on mount. */
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [profilesRes, multiMode, rotationRes] = await Promise.all([
          fetchGameProfiles({ page: 1, page_size: 100 }),
          fetchMultiGameMode(),
          fetchRotationRules(),
        ]);
        if (!cancelled) {
          setProfiles(profilesRes.results ?? []);
          setMultiGameMode(multiMode);
          setRotationRules(rotationRes.results ?? []);
        }
      } catch {
        // Silently ignore — dropdown/switch will default to empty/false
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /**
   * Toggle multi-game parallel mode (Spec A).
   *
   * When enabled, Device input/screenshot methods are restricted to the
   * parallel-safe whitelist on the backend (resolve_device_methods
   * downgrades unsafe methods + unattended_start_view 400s on misconfigured
   * devices). The toggle itself only flips the FeatureFlag; the backend
   * enforces the actual method restrictions.
   */
  const handleToggleMultiGameMode = useCallback(
    async (enabled: boolean) => {
      setMultiGameLoading(true);
      try {
        await updateMultiGameMode(enabled);
        setMultiGameMode(enabled);
        if (enabled) {
          message.info(t('dashboard.multi_game_mode_hint'));
        }
      } catch (err: unknown) {
        const classified = classifyError(err);
        message.error(t('dashboard.start_failed', { message: classified.message }));
      } finally {
        setMultiGameLoading(false);
      }
    },
    [message, t],
  );

  /** Profile ids that already have an active session — disabled in dropdown. */
  const runningProfileIds = useMemo(
    () => new Set(sessions.filter((s) => s.gameProfileId != null).map((s) => s.gameProfileId)),
    [sessions],
  );

  /**
   * Return badge status color and text based on a single session state.
   */
  function getSessionBadge(session: UnattendedSession) {
    if (!session.isRunning) {
      return { status: 'error' as const, text: t('dashboard.status_stopped'), color: token.colorError };
    }
    if (session.isPaused) {
      return { status: 'warning' as const, text: t('dashboard.status_paused'), color: token.colorWarning };
    }
    return { status: 'success' as const, text: t('dashboard.status_running'), color: token.colorSuccess };
  }

  /**
   * Handle "Start new session" button click.
   *
   * Runs preflight → if all pass, calls startUnattended(gameProfileId).
   * Shows appropriate error messages for missing profile / failed preflight / API error.
   */
  const handleStart = useCallback(async () => {
    if (selectedProfileId == null) {
      message.warning(t('dashboard.unattended_no_profile_selected'));
      return;
    }
    setStartLoading(true);
    try {
      const checks = await fetchPreflight(selectedProfileId);
      const hasFail = checks.some((c) => c.status === 'fail');
      if (hasFail) {
        message.error(t('dashboard.preflight_failed'));
        return;
      }
      await startUnattended(selectedProfileId, '', selectedRotationRuleId ?? undefined, loopRotation);
      message.success(t('dashboard.unattended_started'));
      // Reset selector + rotation options so the user must explicitly pick again
      setSelectedProfileId(null);
      setSelectedRotationRuleId(null);
      setLoopRotation(false);
    } catch (err: unknown) {
      const classified = classifyError(err);
      message.error(t('dashboard.start_failed', { message: classified.message }));
    } finally {
      setStartLoading(false);
    }
  }, [selectedProfileId, selectedRotationRuleId, loopRotation, fetchPreflight, startUnattended, t, message]);

  /**
   * Pause a specific session by id.
   */
  const handlePause = useCallback(
    async (session: UnattendedSession) => {
      if (session.id == null) return;
      try {
        await pauseUnattended(session.id);
        message.warning(t('dashboard.paused_global'));
      } catch {
        message.error(t('dashboard.pause_failed'));
      }
    },
    [pauseUnattended, t, message],
  );

  /**
   * Resume a specific paused session by id.
   */
  const handleResume = useCallback(
    async (session: UnattendedSession) => {
      if (session.id == null) return;
      try {
        await resumeUnattended(session.id);
        message.success(t('dashboard.resumed'));
      } catch {
        message.error(t('dashboard.resume_failed'));
      }
    },
    [resumeUnattended, t, message],
  );

  /**
   * Open emergency stop confirmation modal for a specific session.
   */
  const openEmergencyModal = useCallback((session: UnattendedSession) => {
    setEmergencyReason('');
    setEmergencyTarget(session);
  }, []);

  /**
   * Confirm emergency stop on the modal-targeted session.
   */
  const confirmEmergencyStop = useCallback(async () => {
    if (!emergencyReason) {
      message.warning(t('dashboard.select_emergency_reason'));
      return;
    }
    if (emergencyTarget?.id == null) {
      setEmergencyTarget(null);
      return;
    }
    try {
      await stopUnattended(emergencyTarget.id, `emergency:${emergencyReason}`);
      message.error(t('dashboard.emergency_executed'));
      setEmergencyTarget(null);
    } catch {
      message.error(t('dashboard.emergency_failed'));
    }
  }, [emergencyReason, emergencyTarget, stopUnattended, t, message]);

  return (
    <div
      className="gaf-radius-lg"
      style={{
        padding: '16px 24px',
        background: token.colorBgLayout,
        border: `1px solid ${token.colorBorderSecondary}`,
      }}
    >
      {/* Header: title + new-session launcher + multi-game mode toggle */}
      <div className="gaf-flex-between gaf-flex-wrap gaf-gap-md" style={{ marginBottom: sessions.length > 0 ? 16 : 0 }}>
        <div className="gaf-toolbar-group">
          <Typography.Text strong style={{ fontSize: 15 }}>
            {t('dashboard.unattended_active_sessions', { count: sessions.length })}
          </Typography.Text>
          {/* P-011 Spec A: multi-game parallel mode toggle */}
          <Tooltip title={t('dashboard.multi_game_mode_hint')}>
            <Segmented
              size="small"
              disabled={multiGameLoading}
              value={multiGameMode ? 'multi' : 'single'}
              onChange={(v) => handleToggleMultiGameMode(v === 'multi')}
              options={[
                { label: t('dashboard.mode_single'), value: 'single' },
                {
                  label: (
                    <span>
                      <ThunderboltOutlined /> {t('dashboard.mode_multi')}
                    </span>
                  ),
                  value: 'multi',
                },
              ]}
            />
          </Tooltip>
        </div>
        <div className="gaf-toolbar-group">
          <Select
            showSearch
            placeholder={t('dashboard.unattended_select_profile')}
            value={selectedProfileId ?? undefined}
            onChange={(v: number) => setSelectedProfileId(v)}
            style={{ minWidth: 220 }}
            optionFilterProp="label"
            options={profiles.map((p) => ({
              value: p.id,
              label: p.game_name,
              disabled: runningProfileIds.has(p.id),
            }))}
            notFoundContent={profiles.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} /> : undefined}
          />
          <Select
            allowClear
            showSearch
            placeholder={t('dashboard.rotation_rule_placeholder')}
            value={selectedRotationRuleId ?? undefined}
            onChange={(v?: number) => setSelectedRotationRuleId(v ?? null)}
            style={{ minWidth: 180 }}
            optionFilterProp="label"
            options={rotationRules.map((r) => ({
              value: r.id,
              label: r.name,
            }))}
          />
          <Tooltip title={t('dashboard.loop_rotation_hint')}>
            <Space>
              <Switch
                size="small"
                checked={loopRotation}
                onChange={setLoopRotation}
                disabled={selectedRotationRuleId == null}
              />
              <Typography.Text className="gaf-text-sm">{t('dashboard.loop_rotation')}</Typography.Text>
            </Space>
          </Tooltip>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            loading={startLoading || preflightLoading}
            onClick={handleStart}
            disabled={selectedProfileId == null}
          >
            {t('dashboard.unattended_start_new')}
          </Button>
        </div>
      </div>

      {/* Sessions list */}
      {sessions.length === 0 ? (
        <Empty description={t('dashboard.unattended_no_active_sessions')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        // antd6 弃用 List — 迁移为原生 map 渲染
        <>
          {sessions.map((session) => {
            const badge = getSessionBadge(session);
            return (
              <Card
                key={String(session.id ?? `sess-${session.gameProfileId}`)}
                size="small"
                className="gaf-mb-sm"
                bodyStyle={{ padding: '12px 16px' }}
              >
                <div className="gaf-flex-between gaf-flex-wrap gaf-gap-sm">
                  {/* Left: status badge + profile name */}
                  <Space size="middle" align="center">
                    <Tooltip title={badge.text}>
                      <Badge
                        status={badge.status}
                        text={
                          <span
                            className="gaf-font-semibold"
                            style={{
                              fontSize: 14,
                              color: badge.color,
                              animation:
                                badge.status === 'success' ? 'pulse-green 1.5s ease-in-out infinite' : undefined,
                            }}
                          >
                            {badge.text}
                          </span>
                        }
                      />
                    </Tooltip>
                    <Typography.Text strong>
                      {t('dashboard.unattended_session_for', {
                        name: session.gameProfileName ?? `#${session.gameProfileId}`,
                      })}
                    </Typography.Text>
                    {session.startedAt && (
                      <Typography.Text type="secondary" className="gaf-text-xs">
                        {new Date(session.startedAt).toLocaleString()}
                      </Typography.Text>
                    )}
                  </Space>

                  {/* Right: per-session controls */}
                  <Space wrap>
                    {session.isRunning && !session.isPaused && (
                      <Button size="small" icon={<PauseCircleOutlined />} onClick={() => handlePause(session)}>
                        {t('dashboard.btn_pause')}
                      </Button>
                    )}
                    {session.isPaused && (
                      <Button
                        size="small"
                        type="primary"
                        icon={<PlayCircleOutlined />}
                        onClick={() => handleResume(session)}
                      >
                        {t('dashboard.btn_resume')}
                      </Button>
                    )}
                    {session.isRunning && (
                      <Button size="small" danger icon={<StopOutlined />} onClick={() => openEmergencyModal(session)}>
                        {t('dashboard.btn_emergency_stop')}
                      </Button>
                    )}
                  </Space>
                </div>
              </Card>
            );
          })}
        </>
      )}

      {/* Emergency stop confirmation modal (per-session) */}
      <Modal
        title={t('dashboard.emergency_confirm_title')}
        open={emergencyTarget !== null}
        onOk={confirmEmergencyStop}
        onCancel={() => setEmergencyTarget(null)}
        okText={t('dashboard.confirm_stop')}
        cancelText={t('app.cancel')}
        okButtonProps={{ danger: true }}
      >
        <p className="gaf-font-medium gaf-mb-lg" style={{ color: token.colorError }}>
          {t('dashboard.emergency_warning')}
        </p>
        {emergencyTarget?.gameProfileName && (
          <p className="gaf-mb-sm">
            <Tag color="blue">{t('dashboard.unattended_session_for', { name: emergencyTarget.gameProfileName })}</Tag>
          </p>
        )}
        <p className="gaf-mb-sm">{t('dashboard.select_reason_label')}</p>
        <Select
          value={emergencyReason || undefined}
          onChange={setEmergencyReason}
          placeholder={t('dashboard.select_reason_placeholder')}
          options={EMERGENCY_REASONS}
          className="gaf-w-full"
        />
      </Modal>

      {/* Green pulse animation style */}
      <style>{`
        @keyframes pulse-green {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
    </div>
  );
}

export default UnattendedControlBar;
