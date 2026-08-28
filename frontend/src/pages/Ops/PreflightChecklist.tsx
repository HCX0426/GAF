import { useMemo, useCallback } from 'react';
import { Progress, Button, Spin, Space, Typography, Tag, theme } from 'antd';
import {
  CheckCircleFilled,
  ExclamationCircleFilled,
  CloseCircleFilled,
  ToolOutlined,
  MinusCircleOutlined,
} from '@ant-design/icons';
import type { GlobalToken } from 'antd/es/theme/interface';
import type { PreflightCheck } from '@/types/models';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from '@/i18n';

const { Text } = Typography;

/**
 * Calculate preflight pass rate (pass count / total count).
 */
function calcPassRate(checks: PreflightCheck[]): number {
  if (checks.length === 0) return 0;
  const passCount = checks.filter((c) => c.status === 'pass').length;
  return Math.round((passCount / checks.length) * 100);
}

/**
 * Get progress bar color (graded by pass rate).
 */
function getProgressColor(rate: number, token: GlobalToken): string {
  if (rate === 100) return token.colorSuccess;
  if (rate >= 60) return token.colorWarning;
  return token.colorError;
}

/**
 * Preflight checklist component.
 *
 * Displays preflight results before starting unattended mode:
 * - Each item shows status icon, name, description
 * - Overall Progress component shows pass rate
 * - Failed items provide "Fix Guidance" button to navigate to fix_action route
 * - Warning items provide "Ignore & Continue" button
 */
interface PreflightChecklistProps {
  /** Preflight result array */
  checks?: PreflightCheck[];
  /** Whether loading */
  loading?: boolean;
}

export function PreflightChecklist({ checks = [], loading = false }: PreflightChecklistProps) {
  const t = useTranslation();
  const navigate = useNavigate();
  const { token } = theme.useToken();

  /** Check type label mapping (i18n-driven) */
  const CHECK_TYPE_LABELS: Record<PreflightCheck['check_type'], string> = {
    device_online: t('dashboard.check_device_online'),
    account_valid: t('dashboard.check_account_valid'),
    resource_ready: t('dashboard.check_resource_ready'),
    agent_connection: t('dashboard.check_agent_connection'),
    scheduler_rules: t('dashboard.check_scheduler_rules'),
  };

  /** Status icon + color + label mapping (i18n-driven) */
  const STATUS_ICON_MAP: Record<
    PreflightCheck['status'],
    { icon: typeof CheckCircleFilled; color: string; label: string }
  > = {
    pass: { icon: CheckCircleFilled, color: token.colorSuccess, label: t('dashboard.check_pass') },
    warning: { icon: ExclamationCircleFilled, color: token.colorWarning, label: t('dashboard.check_warning') },
    fail: { icon: CloseCircleFilled, color: token.colorError, label: t('dashboard.check_fail') },
  };

  /** Pass rate and color calculation */
  const passRate = useMemo(() => calcPassRate(checks), [checks]);
  const progressColor = useMemo(() => getProgressColor(passRate, token), [passRate, token]);

  /**
   * Click "Fix Guidance" button to navigate to the corresponding fix route.
   */
  const handleFixAction = useCallback(
    (fixAction?: string) => {
      if (!fixAction) return;
      navigate(fixAction);
    },
    [navigate],
  );

  /**
   * Render a single preflight check item.
   */
  const renderCheckItem = useCallback(
    (check: PreflightCheck) => {
      const statusConfig = STATUS_ICON_MAP[check.status];
      const StatusIcon = statusConfig.icon;

      return (
        <div
          className="gaf-flex-between gaf-py-md gaf-px-lg"
          style={{
            borderLeft: `3px solid ${statusConfig.color}`,
            background: check.status === 'fail' ? token.colorErrorBg : undefined,
          }}
        >
          <div className="gaf-flex gaf-flex-1 gaf-gap-md" style={{ alignItems: 'flex-start' }}>
            <StatusIcon style={{ fontSize: 22, color: statusConfig.color, marginTop: 2 }} />
            <div className="gaf-flex-1">
              <Space size={8}>
                <Text strong>{CHECK_TYPE_LABELS[check.check_type]}</Text>
                <Tag color={statusConfig.color}>{statusConfig.label}</Tag>
              </Space>
              <div className="gaf-mt-xs">
                <Text type="secondary">{check.message}</Text>
              </div>
            </div>
          </div>
          <div className="gaf-flex gaf-gap-sm gaf-flex-shrink-0" style={{ marginLeft: 16 }}>
            {check.status === 'fail' && check.fix_action ? (
              <Button
                type="link"
                danger
                size="small"
                icon={<ToolOutlined />}
                onClick={() => handleFixAction(check.fix_action)}
              >
                {t('dashboard.fix_guidance')}
              </Button>
            ) : null}
            {check.status === 'warning' ? (
              <Button type="link" size="small" icon={<MinusCircleOutlined />}>
                {t('dashboard.ignore_and_continue')}
              </Button>
            ) : null}
          </div>
        </div>
      );
    },
    [handleFixAction, CHECK_TYPE_LABELS, STATUS_ICON_MAP, t],
  );

  return (
    <Spin spinning={loading}>
      {/* Pass rate overview */}
      <div
        className="gaf-flex-between gaf-flex-wrap gaf-gap-md gaf-radius-md"
        style={{
          marginBottom: 20,
          padding: '12px 20px',
          background: token.colorBgLayout,
        }}
      >
        <Text strong>{t('dashboard.preflight_check')}</Text>
        <Space align="center" size="middle">
          <span className="gaf-text-13" style={{ color: token.colorTextSecondary }}>
            {t('dashboard.pass_rate')}
          </span>
          <Progress
            percent={passRate}
            strokeColor={progressColor}
            size={[120, 10]}
            format={(percent) => `${percent}%`}
          />
          <Text type="secondary">
            {t('dashboard.pass_count', {
              pass: checks.filter((c) => c.status === 'pass').length,
              total: checks.length,
            })}
          </Text>
        </Space>
      </div>

      {/* Check list - using custom list instead of deprecated List component */}
      <div
        className="gaf-radius-md gaf-overflow-hidden"
        style={{
          border: `1px solid ${token.colorBorderSecondary}`,
        }}
      >
        {checks.length === 0 ? (
          <div className="gaf-p-xl gaf-text-center" style={{ color: token.colorTextTertiary }}>
            {t('dashboard.empty_preflight')}
          </div>
        ) : (
          checks.map((check) => <div key={check.check_type}>{renderCheckItem(check)}</div>)
        )}
      </div>
    </Spin>
  );
}

export default PreflightChecklist;
