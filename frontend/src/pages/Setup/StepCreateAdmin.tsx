import React, { useState } from 'react';
import { Form, Input, Button, Alert, Card, theme } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { createAdmin } from '@/api/init';
import { useTranslation } from '@/i18n';

interface StepCreateAdminProps {
  onSuccess: () => void;
}

/**
 * Step 1: create admin account
 * user name + password + confirm password form, with real-time verify
 */
const StepCreateAdmin: React.FC<StepCreateAdminProps> = ({ onSuccess }) => {
  const t = useTranslation();
  const { token } = theme.useToken();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (values: { username: string; password: string }) => {
    setLoading(true);
    setError(null);
    try {
      await createAdmin(values.username, values.password);
      onSuccess();
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : t('setup.admin.create_failed');
      setError(errMsg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      {error && <Alert type="error" title={error} closable className="gaf-mb-lg" />}
      <Form form={form} layout="vertical" onFinish={handleSubmit} size="large">
        <Form.Item
          name="username"
          label={t('setup.admin.label_username')}
          rules={[
            { required: true, message: t('setup.admin.validate_username_required') },
            { min: 3, max: 30, message: t('setup.admin.validate_username_length') },
            { pattern: /^[a-zA-Z]/, message: t('setup.admin.validate_username_letter_start') },
          ]}
        >
          <Input prefix={<UserOutlined />} placeholder={t('setup.admin.placeholder_username')} />
        </Form.Item>
        <Form.Item
          name="password"
          label={t('setup.admin.label_password')}
          rules={[
            { required: true, message: t('setup.admin.validate_password_required') },
            { min: 8, message: t('setup.admin.validate_password_min_length') },
            { pattern: /^(?=.*[a-zA-Z])(?=.*\d)/, message: t('setup.admin.validate_password_alphanumeric') },
          ]}
        >
          <Input.Password prefix={<LockOutlined />} placeholder={t('setup.admin.placeholder_password')} />
        </Form.Item>
        <Form.Item
          name="confirmPassword"
          label={t('setup.admin.label_confirm_password')}
          dependencies={['password']}
          rules={[
            { required: true, message: t('setup.admin.validate_confirm_required') },
            ({ getFieldValue }) => ({
              validator(_: unknown, value: string) {
                if (!value || getFieldValue('password') === value) {
                  return Promise.resolve();
                }
                return Promise.reject(new Error(t('setup.admin.validate_password_mismatch')));
              },
            }),
          ]}
        >
          <Input.Password prefix={<LockOutlined />} placeholder={t('setup.admin.placeholder_confirm_password')} />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} block>
            {t('setup.admin.btn_create')}
          </Button>
        </Form.Item>
      </Form>
      <Card size="small" className="gaf-mt-lg" style={{ background: token.colorBgLayout }}>
        <strong>{t('setup.admin.card_title')}</strong>
        <p className="gaf-m-0">{t('setup.admin.card_desc')}</p>
      </Card>
    </div>
  );
};

export default StepCreateAdmin;
