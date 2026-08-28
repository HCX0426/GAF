/**
 * DispatchRoutineModal — per-device "排任务" modal (spec v3 §2.6 entry 1)
 *
 * Flow:
 *   GameProfile detail → Devices tab → row "排任务" button
 *   → this modal: select TaskChain (default = profile.default_routine)
 *                 select GameAccount (default = device.game_account)
 *   → confirm → POST /api/v2/pipeline/task-chains/{id}/execute/
 *   → navigate to /ops/executions
 */
import { useEffect, useState, useMemo, useCallback } from 'react';
import { Modal, Form, Select, Typography, App, Tag, Descriptions } from 'antd';
import { useNavigate } from 'react-router-dom';

import { fetchGameProfileTaskChains, fetchGameProfileAccounts, executeTaskChain } from '@/api/gameProfiles';
import type { Device, TaskChain, GameAccount } from '@/types/models';
import { useTranslation } from '@/i18n';

const { Text } = Typography;

interface Props {
  open: boolean;
  onClose: () => void;
  profileId: number;
  device: Device | null;
  defaultRoutineId?: number | null;
}

export default function DispatchRoutineModal({ open, onClose, profileId, device, defaultRoutineId }: Props) {
  const t = useTranslation();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [form] = Form.useForm();

  const [chains, setChains] = useState<TaskChain[]>([]);
  const [accounts, setAccounts] = useState<GameAccount[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const loadOptions = useCallback(async () => {
    if (!profileId) return;
    setLoading(true);
    try {
      const [chainRes, accountRes] = await Promise.all([
        fetchGameProfileTaskChains(profileId, { page: 1, page_size: 100 }),
        fetchGameProfileAccounts(profileId, { page: 1, page_size: 100 }),
      ]);
      setChains(chainRes.results ?? []);
      setAccounts(accountRes.results ?? []);
    } catch {
      message.error(t('gameProfiles.dispatch_load_failed'));
    } finally {
      setLoading(false);
    }
  }, [profileId, message, t]);

  useEffect(() => {
    if (open) {
      loadOptions();
    }
  }, [open, loadOptions]);

  // Pre-fill form when options loaded or device/defaultRoutineId changes
  useEffect(() => {
    if (!open || !device) return;
    const chainId = defaultRoutineId ?? chains[0]?.id;
    const accountId = device.game_account ?? accounts[0]?.id;
    form.setFieldsValue({
      task_chain_id: chainId,
      game_account_id: accountId,
    });
  }, [open, device, defaultRoutineId, chains, accounts, form]);

  const selectedChain = useMemo(() => chains.find((c) => c.id === form.getFieldValue('task_chain_id')), [chains, form]);

  const handleOk = async () => {
    if (!device) return;
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      const result = await executeTaskChain(values.task_chain_id, {
        device_id: device.id,
        game_account_id: values.game_account_id ?? null,
      });
      message.success(result.message);
      onClose();
      navigate('/ops/executions');
    } catch (err) {
      if (err && typeof err === 'object' && 'errorFields' in err) return; // form validation error
      message.error(t('gameProfiles.dispatch_execute_failed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={t('gameProfiles.dispatch_title')}
      open={open}
      onCancel={onClose}
      onOk={handleOk}
      confirmLoading={submitting}
      okText={t('gameProfiles.btn_dispatch')}
      cancelText={t('gameProfiles.btn_cancel')}
      destroyOnHidden
      width={520}
    >
      {device && (
        <Descriptions column={1} size="small" className="gaf-mb-md">
          <Descriptions.Item label={t('gameProfiles.col_device_name')}>
            <Text strong>{device.name}</Text>
            {device.status === 'online' ? (
              <Tag color="green" style={{ marginLeft: 8 }}>
                online
              </Tag>
            ) : (
              <Tag color="default" style={{ marginLeft: 8 }}>
                {device.status}
              </Tag>
            )}
          </Descriptions.Item>
        </Descriptions>
      )}

      <Form form={form} layout="vertical" disabled={loading}>
        <Form.Item
          name="task_chain_id"
          label={t('gameProfiles.dispatch_lbl_chain')}
          rules={[{ required: true, message: t('gameProfiles.dispatch_chain_required') }]}
        >
          <Select
            placeholder={t('gameProfiles.dispatch_placeholder_chain')}
            options={chains.map((c) => ({
              value: c.id,
              label: c.is_default ? `${c.name} (${t('gameProfiles.tag_default')})` : c.name,
              disabled: !c.is_enabled,
            }))}
          />
        </Form.Item>

        {selectedChain?.description && (
          <Text type="secondary" className="gaf-mb-md block">
            {selectedChain.description}
          </Text>
        )}

        <Form.Item name="game_account_id" label={t('gameProfiles.dispatch_lbl_account')}>
          <Select
            placeholder={t('gameProfiles.dispatch_placeholder_account')}
            allowClear
            options={accounts.map((a) => ({
              value: a.id,
              label: `${a.username} (${a.server_region})`,
            }))}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
