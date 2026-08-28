/**
 * account status panel Drawer
 * show account detail info, status metric, supports manual refresh and auto refresh
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { Drawer, Descriptions, Badge, Button, Spin } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { fetchGameAccount } from '@/api/accounts';
import { useTranslation, getLocale } from '@/i18n';
import type { GameAccount } from '@/types/models';

interface AccountStatusPanelProps {
  account: GameAccount;
  open: boolean;
  onClose: () => void;
}

/** status Badge mapping */
const STATUS_BADGE_MAP: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
  ok: 'success',
  warn: 'warning',
  error: 'error',
  unknown: 'default',
};

/** status i18n key mapping */
const STATUS_TEXT_KEY: Record<string, string> = {
  ok: 'accounts.status_ok',
  warn: 'accounts.status_warn',
  error: 'accounts.status_error',
  unknown: 'accounts.status_unknown',
};

/**
 * account status panel
 * show status details,30 seconds auto refresh, mock stamina data
 */
export function AccountStatusPanel({ account, open, onClose }: AccountStatusPanelProps) {
  const t = useTranslation();
  const locale = getLocale();
  const [currentAccount, setCurrentAccount] = useState<GameAccount>(account);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /**
   * manual refresh account info
   */
  const handleRefresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchGameAccount(currentAccount.id);
      setCurrentAccount(data);
    } catch {
      // silent failure
    } finally {
      setLoading(false);
    }
  }, [currentAccount.id]);

  /** auto refresh: every 30 seconds */
  useEffect(() => {
    if (open) {
      timerRef.current = setInterval(handleRefresh, 30000);
      return () => {
        if (timerRef.current) {
          clearInterval(timerRef.current);
        }
      };
    }
  }, [open, handleRefresh]);

  /** close when clean */
  useEffect(() => {
    if (!open && timerRef.current) {
      clearInterval(timerRef.current);
    }
  }, [open]);

  return (
    <Drawer
      title={t('accounts.status_panel_title', { name: currentAccount.username })}
      open={open}
      onClose={onClose}
      size={420}
      extra={
        <Button icon={<ReloadOutlined spin={loading} />} onClick={handleRefresh} loading={loading}>
          {t('accounts.refresh')}
        </Button>
      }
    >
      <Spin spinning={loading}>
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label={t('accounts.col_game_name_label')}>{currentAccount.game_name}</Descriptions.Item>
          <Descriptions.Item label={t('accounts.col_username_label')}>{currentAccount.username}</Descriptions.Item>
          <Descriptions.Item label={t('accounts.col_server_region_label')}>
            {currentAccount.server_region || '-'}
          </Descriptions.Item>
          <Descriptions.Item label={t('accounts.col_login_method_label')}>
            {currentAccount.login_method}
          </Descriptions.Item>

          <Descriptions.Item label={t('accounts.col_status_label')}>
            <Badge
              status={STATUS_BADGE_MAP[currentAccount.status] || 'default'}
              text={
                STATUS_TEXT_KEY[currentAccount.status]
                  ? t(STATUS_TEXT_KEY[currentAccount.status])
                  : currentAccount.status
              }
            />
          </Descriptions.Item>

          <Descriptions.Item label={t('accounts.col_group_label')}>
            {currentAccount.group_name || t('accounts.ungrouped')}
          </Descriptions.Item>

          <Descriptions.Item label={t('accounts.col_resource_pack_label')}>
            {(() => {
              // 后端 GameAccount.allowed_resource_packs 已移除 (R37 window-centric 重构),
              // 此处用 type assertion 兼容历史字段读取 (业务 bug, 待后续重构)
              const packs = (currentAccount as unknown as { allowed_resource_packs?: { name: string }[] })
                .allowed_resource_packs;
              return packs?.length ? packs.map((p) => p.name).join(', ') : t('accounts.no_limit');
            })()}
          </Descriptions.Item>

          <Descriptions.Item label={t('accounts.col_last_login_label')}>
            {currentAccount.last_login_at
              ? dayjs(currentAccount.last_login_at).locale(locale).format('YYYY-MM-DD HH:mm:ss')
              : t('accounts.never_login')}
          </Descriptions.Item>

          <Descriptions.Item label={t('accounts.col_last_check_label')}>
            {currentAccount.last_check_at
              ? dayjs(currentAccount.last_check_at).locale(locale).format('YYYY-MM-DD HH:mm:ss')
              : t('accounts.not_checked')}
          </Descriptions.Item>

          <Descriptions.Item label={t('accounts.col_active_status_label')}>
            <Badge
              status={currentAccount.is_active ? 'success' : 'default'}
              text={currentAccount.is_active ? t('accounts.active') : t('accounts.inactive')}
            />
          </Descriptions.Item>

          <Descriptions.Item label={t('accounts.col_created_at_label')}>
            {dayjs(currentAccount.created_at).locale(locale).format('YYYY-MM-DD HH:mm:ss')}
          </Descriptions.Item>

          <Descriptions.Item label={t('accounts.col_updated_at_label')}>
            {dayjs(currentAccount.updated_at).locale(locale).format('YYYY-MM-DD HH:mm:ss')}
          </Descriptions.Item>
        </Descriptions>
      </Spin>
    </Drawer>
  );
}

export default AccountStatusPanel;
