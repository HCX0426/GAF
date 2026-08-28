/**
 * Reusable GameProfile editor modal (extracted from GameProfiles list page).
 *
 * Used by:
 *   - GameProfilesPage (list page): create + edit
 *   - GameProfileDetailPage (detail page): edit only (no navigate back)
 *
 * Props:
 *   - open: boolean
 *   - profile: GameProfile | undefined  (undefined = create mode)
 *   - onOk: (values) => Promise<void>  (caller handles API + reload)
 *   - onCancel: () => void
 *   - submitting: boolean
 */
import { useEffect } from 'react';
import { Modal, Form, Input, Select, Divider, InputNumber } from 'antd';
import { useTranslation } from '@/i18n';
import type { GameProfile } from '@/types/models';
import { useGameProfileOptions } from '../options';

export interface GameProfileEditorModalProps {
  open: boolean;
  profile?: GameProfile;
  submitting: boolean;
  onOk: (values: Record<string, unknown>) => Promise<void>;
  onCancel: () => void;
}

export default function GameProfileEditorModal({
  open,
  profile,
  submitting,
  onOk,
  onCancel,
}: GameProfileEditorModalProps) {
  const t = useTranslation();
  const [form] = Form.useForm();

  const isEdit = !!profile;

  const {
    screenshotMethods,
    inputMethods,
    controlModes,
    ocrLangOptions,
    resolutionStrategyOptions,
    deviceTypeOptions,
  } = useGameProfileOptions();

  /** Fill form data when editing, reset when creating */
  useEffect(() => {
    if (open && profile) {
      form.setFieldsValue({
        game_name: profile.game_name,
        default_screenshot_method: profile.default_screenshot_method || 'bitblt',
        default_input_method: profile.default_input_method || 'sendinput',
        default_control_mode: profile.default_control_mode || 'foreground',
        ocr_language: profile.ocr_language,
        ui_reference_resolution: profile.ui_reference_resolution,
        known_popups: profile.known_popups,
        resolution_strategy: profile.resolution_strategy,
        routine_path: profile.routine_path || '',
        allowed_device_types: profile.allowed_device_types || [],
      });
    } else if (open) {
      form.resetFields();
      form.setFieldsValue({
        default_screenshot_method: 'bitblt',
        default_input_method: 'sendinput',
        default_control_mode: 'foreground',
        ocr_language: 'ch',
        ui_reference_resolution: { w: 1920, h: 1080 },
        known_popups: [],
        resolution_strategy: 'scale',
        routine_path: '',
        allowed_device_types: [],
      });
    }
  }, [open, profile, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      await onOk(values);
    } catch {
      // validation error — keep modal open
    }
  };

  return (
    <Modal
      title={isEdit ? t('gameProfiles.modal_edit_title') : t('gameProfiles.modal_create_title')}
      open={open}
      onOk={handleOk}
      onCancel={onCancel}
      confirmLoading={submitting}
      width={640}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" className="gaf-mt-lg">
        <Form.Item
          name="game_name"
          label={t('gameProfiles.lbl_game_name')}
          rules={[{ required: true, message: t('gameProfiles.msg_game_name_required') }]}
        >
          <Input placeholder={t('gameProfiles.placeholder_game_name')} />
        </Form.Item>

        <Divider titlePlacement="left">{t('gameProfiles.divider_default_methods')}</Divider>

        <div className="gaf-flex gaf-gap-md">
          <Form.Item
            name="default_screenshot_method"
            label={t('gameProfiles.lbl_default_screenshot_method')}
            className="gaf-flex-1"
          >
            <Select
              placeholder={t('gameProfiles.placeholder_screenshot_method')}
              options={screenshotMethods}
              allowClear
            />
          </Form.Item>
          <Form.Item
            name="default_input_method"
            label={t('gameProfiles.lbl_default_input_method')}
            className="gaf-flex-1"
          >
            <Select placeholder={t('gameProfiles.placeholder_input_method')} options={inputMethods} allowClear />
          </Form.Item>
          <Form.Item
            name="default_control_mode"
            label={t('gameProfiles.lbl_default_control_mode')}
            className="gaf-flex-1"
          >
            <Select placeholder={t('gameProfiles.placeholder_control_mode')} options={controlModes} allowClear />
          </Form.Item>
        </div>

        <Form.Item
          name="ocr_language"
          label={t('gameProfiles.lbl_ocr_language')}
          rules={[{ required: true, message: t('gameProfiles.msg_ocr_language_required') }]}
        >
          <Select placeholder={t('gameProfiles.placeholder_ocr_language')} options={ocrLangOptions} />
        </Form.Item>

        <Divider titlePlacement="left">{t('gameProfiles.divider_ui_resolution')}</Divider>

        <div className="gaf-flex gaf-gap-md">
          <Form.Item name={['ui_reference_resolution', 'w']} label={t('gameProfiles.lbl_width')} className="gaf-flex-1">
            <InputNumber min={1} className="gaf-w-full" placeholder="1920" />
          </Form.Item>
          <Form.Item
            name={['ui_reference_resolution', 'h']}
            label={t('gameProfiles.lbl_height')}
            className="gaf-flex-1"
          >
            <InputNumber min={1} className="gaf-w-full" placeholder="1080" />
          </Form.Item>
        </div>

        <Form.Item
          name="resolution_strategy"
          label={t('gameProfiles.lbl_resolution_strategy')}
          rules={[{ required: true, message: t('gameProfiles.msg_resolution_strategy_required') }]}
        >
          <Select placeholder={t('gameProfiles.placeholder_resolution_strategy')} options={resolutionStrategyOptions} />
        </Form.Item>

        <Form.Item name="known_popups" label={t('gameProfiles.lbl_known_popups')}>
          <Select mode="tags" placeholder={t('gameProfiles.placeholder_known_popups')} />
        </Form.Item>

        <Divider titlePlacement="left">{t('gameProfiles.divider_routine')}</Divider>

        <Form.Item
          name="routine_path"
          label={t('gameProfiles.lbl_routine_path')}
          tooltip={t('gameProfiles.tip_routine_path')}
        >
          <Input placeholder={t('gameProfiles.placeholder_routine_path')} allowClear />
        </Form.Item>

        <Divider titlePlacement="left">{t('gameProfiles.divider_device_types')}</Divider>

        <Form.Item
          name="allowed_device_types"
          label={t('gameProfiles.lbl_allowed_device_types')}
          tooltip={t('gameProfiles.tip_allowed_device_types')}
        >
          <Select
            mode="multiple"
            placeholder={t('gameProfiles.placeholder_allowed_device_types')}
            options={deviceTypeOptions}
            allowClear
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
