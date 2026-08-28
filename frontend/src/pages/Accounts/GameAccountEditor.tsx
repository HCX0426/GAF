/**
 * game account create / edit Modal form
 * based on is no passed-in account distinguish create new / edit mode
 */
import { useEffect, useState } from 'react';
import { Modal, Form, Input, Select, App } from 'antd';
import { createAccount, updateAccount, fetchAccountGroups, fetchGameOptions } from '@/api/accounts';
import { fetchResourcePacks } from '@/api/resources';
import { useTranslation } from '@/i18n';
import type { GameAccount, AccountGroup, ResourcePack } from '@/types/models';

interface GameAccountEditorProps {
  open: boolean;
  account?: GameAccount;
  onClose: () => void;
  onSuccess: () => void;
}

/**
 * game account editor Modal
 * reuse create new and edit two types mode
 */
export function GameAccountEditor({ open, account, onClose, onSuccess }: GameAccountEditorProps) {
  const { message } = App.useApp();
  const t = useTranslation();
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [groups, setGroups] = useState<AccountGroup[]>([]);
  const [gameOptions, setGameOptions] = useState<string[]>([]);
  const [resourcePacks, setResourcePacks] = useState<ResourcePack[]>([]);
  const isEdit = !!account;

  /** form validation prompt info */
  const validateMessages = {
    required: t('accounts.field_required'),
  };

  /** login method option */
  const loginMethodOptions = [
    { label: t('accounts.login_method_password'), value: 'password' },
    { label: t('accounts.login_method_qr_scan'), value: 'qr_scan' },
    { label: t('accounts.login_method_token'), value: 'token' },
    { label: t('accounts.login_method_steam'), value: 'steam' },
  ];

  /** server options */
  const serverRegionOptions = [
    { label: t('accounts.server_official'), value: '官服' },
    { label: t('accounts.server_b'), value: 'B服' },
    { label: t('accounts.server_channel'), value: '渠道服' },
  ];

  /** load group list */
  useEffect(() => {
    if (open) {
      // spec35 #12: surface fetch failures instead of swallowing silently.
      fetchAccountGroups()
        .then((res) => setGroups(res.results ?? []))
        .catch((err) => {
          message.error(t('accounts.load_groups_failed'));
          console.warn('[GameAccountEditor] fetchAccountGroups failed:', err);
        });
      fetchGameOptions()
        .then((res) => setGameOptions(res.games ?? []))
        .catch((err) => {
          message.error(t('accounts.load_game_options_failed'));
          console.warn('[GameAccountEditor] fetchGameOptions failed:', err);
        });
      fetchResourcePacks()
        .then((res) => setResourcePacks(res.results ?? []))
        .catch((err) => {
          message.error(t('accounts.load_resource_packs_failed'));
          console.warn('[GameAccountEditor] fetchResourcePacks failed:', err);
        });
    }
  }, [open]);

  /** edit mode below backfill form data */
  useEffect(() => {
    if (open && account) {
      form.setFieldsValue({
        game_name: account.game_name,
        username: account.username,
        password: '',
        server_region: account.server_region,
        login_method: account.login_method,
        group: account.group ?? undefined,
        resource_pack: account.resource_pack ?? undefined,
      });
    } else if (open) {
      form.resetFields();
    }
  }, [open, account, form]);

  /**
   * submit form
   */
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);

      const payload: Record<string, unknown> = {
        game_name: values.game_name,
        username: values.username,
        server_region: values.server_region,
        login_method: values.login_method,
        group: values.group || null,
        resource_pack: values.resource_pack || null,
      };

      if (isEdit) {
        if (values.password) {
          payload.password = values.password;
        }
        await updateAccount(account!.id, payload);
        message.success(t('accounts.updated'));
      } else {
        payload.password = values.password;
        await createAccount(payload);
        message.success(t('accounts.created'));
      }

      onSuccess();
    } catch {
      // do not handle when form validation fails
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={isEdit ? t('accounts.edit_title') : t('accounts.create_title')}
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      confirmLoading={submitting}
      destroyOnHidden
      width={520}
    >
      <Form
        form={form}
        layout="vertical"
        preserve={false}
        validateMessages={validateMessages}
        initialValues={{ login_method: 'password', server_region: '官服' }}
      >
        <Form.Item name="game_name" label={t('accounts.col_game_name')} rules={[{ required: true }]}>
          <Select
            placeholder={t('accounts.select_game')}
            showSearch
            options={gameOptions.map((name) => ({ label: name, value: name }))}
            notFoundContent={t('accounts.no_games')}
            allowClear
          />
        </Form.Item>

        <Form.Item name="username" label={t('accounts.col_username')} rules={[{ required: true }]}>
          <Input placeholder={t('accounts.game_username_placeholder')} autoComplete="username" name="game_username" />
        </Form.Item>

        <Form.Item name="password" label={t('accounts.password')} rules={isEdit ? [] : [{ required: true }]}>
          <Input.Password
            placeholder={isEdit ? t('accounts.password_placeholder_edit') : t('accounts.password_placeholder_new')}
            autoComplete={isEdit ? 'current-password' : 'new-password'}
          />
        </Form.Item>

        <Form.Item name="server_region" label={t('accounts.col_server_region')}>
          <Select placeholder={t('accounts.select_server')} options={serverRegionOptions} allowClear />
        </Form.Item>

        <Form.Item name="login_method" label={t('accounts.col_login_method')} rules={[{ required: true }]}>
          <Select options={loginMethodOptions} placeholder={t('accounts.select_login_method')} />
        </Form.Item>

        <Form.Item name="group" label={t('accounts.col_group')}>
          <Select
            allowClear
            placeholder={t('accounts.group_optional')}
            options={groups.map((g) => ({ label: g.name, value: g.id }))}
          />
        </Form.Item>

        <Form.Item name="resource_pack" label={t('accounts.bind_resource_pack')}>
          <Select
            allowClear
            placeholder={t('accounts.select_resource_pack')}
            showSearch
            optionFilterProp="label"
            options={resourcePacks.map((rp) => ({
              label: `${rp.name} v${rp.version}`,
              value: rp.id,
            }))}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default GameAccountEditor;
