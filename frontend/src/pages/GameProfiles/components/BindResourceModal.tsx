/**
 * BindResourceModal — attach an existing child resource (Task / TaskChain /
 * GameAccount) to a GameProfile.
 *
 * Used by TasksTab / TaskChainsTab / AccountsTab on the GameProfile detail
 * page (spec v3 §2.5.2). Shows a searchable list of unbound resources and
 * calls the corresponding bind API on confirm.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { App, Modal, Select, Spin, Typography } from 'antd';
import { useTranslation } from '@/i18n';
import { bindTask, bindTaskChain, bindAccount } from '@/api/gameProfiles';
import { fetchTasks } from '@/api/tasks';
import { fetchTaskChains } from '@/api/tasks';
import { fetchGameAccounts } from '@/api/accounts';
import type { GameAccount, Task, TaskChain } from '@/types/models';

const { Text } = Typography;

export type BindResourceType = 'task' | 'task_chain' | 'account';

export interface BindResourceModalProps {
  open: boolean;
  profileId: number;
  resourceType: BindResourceType;
  /** IDs of resources already bound to this profile (hidden from the list). */
  excludeIds: number[];
  onClose: () => void;
  onBound: () => void;
}

interface OptionItem {
  value: number;
  label: string;
}

export function BindResourceModal({
  open,
  profileId,
  resourceType,
  excludeIds,
  onClose,
  onBound,
}: BindResourceModalProps) {
  const t = useTranslation();
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [options, setOptions] = useState<OptionItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  // Load unbound resources when modal opens.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        let items: Array<{ id: number; name?: string; username?: string }> = [];
        if (resourceType === 'task') {
          const res = await fetchTasks({ page_size: 100 });
          items = (res.results || res).map((x: Task) => ({ id: x.id, name: x.name }));
        } else if (resourceType === 'task_chain') {
          const res = await fetchTaskChains({ page_size: 100 });
          items = (res.results || res).map((x: TaskChain) => ({ id: x.id, name: x.name }));
        } else {
          const res = await fetchGameAccounts({ page_size: 100 });
          items = (res.results || res).map((x: GameAccount) => ({
            id: x.id,
            name: x.username || `#${x.id}`,
          }));
        }
        if (!cancelled) {
          const opts = items
            .filter((x) => !excludeIds.includes(x.id))
            .map((x) => ({ value: x.id, label: x.name || `#${x.id}` }));
          setOptions(opts);
        }
      } catch {
        if (!cancelled) message.error(t('gameProfiles.bind_load_failed'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, resourceType, excludeIds, message, t]);

  const titleKey = useMemo(() => {
    if (resourceType === 'task') return 'gameProfiles.bind_task_title';
    if (resourceType === 'task_chain') return 'gameProfiles.bind_task_chain_title';
    return 'gameProfiles.bind_account_title';
  }, [resourceType]);

  const handleOk = useCallback(async () => {
    if (selectedId == null) return;
    setSubmitting(true);
    try {
      if (resourceType === 'task') await bindTask(profileId, selectedId);
      else if (resourceType === 'task_chain') await bindTaskChain(profileId, selectedId);
      else await bindAccount(profileId, selectedId);
      message.success(t('gameProfiles.bind_success'));
      setSelectedId(null);
      onBound();
      onClose();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { error?: string } } })?.response?.data?.error;
      message.error(detail || t('gameProfiles.bind_failed'));
    } finally {
      setSubmitting(false);
    }
  }, [selectedId, resourceType, profileId, message, t, onBound, onClose]);

  const handleClose = useCallback(() => {
    setSelectedId(null);
    onClose();
  }, [onClose]);

  return (
    <Modal
      open={open}
      title={t(titleKey)}
      onCancel={handleClose}
      onOk={handleOk}
      okText={t('gameProfiles.btn_bind')}
      cancelText={t('common.cancel')}
      confirmLoading={submitting}
      okButtonProps={{ disabled: selectedId == null }}
      destroyOnHidden
    >
      <Spin spinning={loading}>
        <div className="gaf-mb-md">
          <Text type="secondary">{t('gameProfiles.bind_select_hint')}</Text>
        </div>
        <Select
          showSearch
          className="gaf-w-full"
          placeholder={t('gameProfiles.bind_select_placeholder')}
          optionFilterProp="label"
          value={selectedId}
          onChange={setSelectedId}
          options={options}
          notFoundContent={loading ? undefined : t('gameProfiles.bind_no_candidates')}
        />
      </Spin>
    </Modal>
  );
}

export default BindResourceModal;
