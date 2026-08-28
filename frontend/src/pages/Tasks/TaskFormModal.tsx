import { useEffect, useState } from 'react';
import { Modal, Form, Input, Select, Switch, App, Collapse } from 'antd';
import { createTask, updateTask } from '@/api/tasks';
import { fetchGameAccounts } from '@/api/accounts';
import { fetchDevices } from '@/api/devices';
import { fetchGameProfiles } from '@/api/gameProfiles';
import { fetchResourcePacks } from '@/api/resources';
import type { Task, GameAccount, Device, GameProfile, ResourcePack } from '@/types/models';
import { useTranslation } from '@/i18n';

interface TaskFormModalProps {
  open: boolean;
  editingTask: Task | null;
  onClose: () => void;
  onSuccess: () => void;
}

export function TaskFormModal({ open, editingTask, onClose, onSuccess }: TaskFormModalProps) {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const t = useTranslation();
  const [gameAccounts, setGameAccounts] = useState<GameAccount[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [gameProfiles, setGameProfiles] = useState<GameProfile[]>([]);
  const [resourcePacks, setResourcePacks] = useState<ResourcePack[]>([]);
  const isEdit = !!editingTask;

  // Execution mode options depend on current locale
  // spec-2026-07-27-execution-path-unification: chain 已废弃，统一为 pipeline
  const executionModeOptions = [
    { label: t('tasks.mode_pipeline_full'), value: 'pipeline' },
    { label: t('tasks.mode_state_machine_full'), value: 'state_machine' },
  ];

  useEffect(() => {
    if (open) {
      // spec35 #12: surface fetch failures to the user instead of swallowing silently.
      fetchGameAccounts()
        .then((res) => setGameAccounts(res.results || []))
        .catch((err) => {
          message.error(t('tasks.load_accounts_failed'));
          console.warn('[TaskFormModal] fetchGameAccounts failed:', err);
        });
      fetchDevices()
        .then((res) => setDevices(res.results || []))
        .catch((err) => {
          message.error(t('tasks.load_devices_failed'));
          console.warn('[TaskFormModal] fetchDevices failed:', err);
        });
      fetchGameProfiles({ page: 1, page_size: 100 })
        .then((res) => setGameProfiles(res.results || []))
        .catch((err) => {
          message.error(t('tasks.load_profiles_failed'));
          console.warn('[TaskFormModal] fetchGameProfiles failed:', err);
        });
      fetchResourcePacks({ page: 1, page_size: 100 })
        .then((res) => setResourcePacks(res.results || []))
        .catch((err) => {
          console.warn('[TaskFormModal] fetchResourcePacks failed:', err);
        });
      if (editingTask) {
        form.setFieldsValue({
          name: editingTask.name,
          description: editingTask.description,
          execution_mode: editingTask.execution_mode,
          is_enabled: editingTask.is_enabled,
          game_accounts: editingTask.game_account_details?.map((ga) => ga.id) || [],
          devices: editingTask.device_details?.map((d) => d.id) || [],
          game_profile: editingTask.game_profile ?? undefined,
          resource_pack: ((editingTask as Record<string, unknown>).resource_pack as number) ?? undefined,
        });
      } else {
        form.resetFields();
        form.setFieldsValue({ execution_mode: 'pipeline', is_enabled: true });
      }
    }
  }, [open, editingTask, form]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const payload = {
        ...values,
        game_accounts: values.game_accounts || [],
        devices: values.devices || [],
      };
      if (isEdit) {
        await updateTask(editingTask!.id, payload);
        message.success(t('tasks.msg_updated'));
      } else {
        await createTask(payload);
        message.success(t('tasks.msg_created'));
      }
      onSuccess();
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'errorFields' in err) return;
      message.error(isEdit ? t('tasks.msg_update_failed') : t('tasks.msg_create_failed'));
    }
  };

  return (
    <Modal
      title={isEdit ? t('tasks.title_edit_task') : t('tasks.title_create_task')}
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      destroyOnHidden
      okText={isEdit ? t('app.save') : t('tasks.title_create_task')}
      cancelText={t('app.cancel')}
      mask={{ closable: false }}
    >
      <Form form={form} layout="vertical" className="gaf-mt-lg">
        <Form.Item
          name="name"
          label={t('tasks.form_name_label')}
          rules={[{ required: true, message: t('tasks.form_name_required') }]}
        >
          <Input placeholder={t('tasks.form_name_placeholder')} maxLength={200} showCount />
        </Form.Item>
        <Form.Item name="description" label={t('tasks.form_description_label')}>
          <Input.TextArea placeholder={t('tasks.form_description_placeholder')} rows={3} />
        </Form.Item>
        <Form.Item name="execution_mode" label={t('tasks.form_execution_mode_label')}>
          <Select options={executionModeOptions} />
        </Form.Item>
        <Form.Item name="game_profile" label={t('tasks.form_game_profile_label')}>
          <Select
            placeholder={t('tasks.form_game_profile_placeholder')}
            allowClear
            options={gameProfiles.map((gp) => ({
              label: gp.game_name,
              value: gp.id,
            }))}
          />
        </Form.Item>
        <Form.Item name="resource_pack" label={t('tasks.form_resource_pack_label')}>
          <Select
            placeholder={t('tasks.form_resource_pack_placeholder')}
            allowClear
            options={resourcePacks.map((rp) => ({
              label: `${rp.name} v${rp.version}`,
              value: rp.id,
            }))}
          />
        </Form.Item>
        <Form.Item name="is_enabled" label={t('tasks.form_enabled_label')} valuePropName="checked">
          <Switch checkedChildren={t('tasks.switch_enabled')} unCheckedChildren={t('tasks.switch_disabled')} />
        </Form.Item>

        <Collapse
          ghost
          items={[
            {
              key: 'advanced',
              label: t('tasks.form_advanced_options'),
              children: (
                <>
                  <Form.Item name="game_accounts" label={t('tasks.form_game_accounts_label')}>
                    <Select
                      mode="multiple"
                      placeholder={t('tasks.form_game_accounts_placeholder')}
                      allowClear
                      options={gameAccounts.map((ga) => ({
                        label: `${ga.game_name} - ${ga.username}`,
                        value: ga.id,
                      }))}
                    />
                  </Form.Item>
                  <Form.Item name="devices" label={t('tasks.form_devices_label')}>
                    <Select
                      mode="multiple"
                      placeholder={t('tasks.form_devices_placeholder')}
                      allowClear
                      options={devices.map((d) => ({
                        label: `${d.name} (${d.adb_serial || d.window_handle || t('tasks.device_not_connected')})`,
                        value: d.id,
                      }))}
                    />
                  </Form.Item>
                </>
              ),
            },
          ]}
        />
      </Form>
    </Modal>
  );
}

export default TaskFormModal;
