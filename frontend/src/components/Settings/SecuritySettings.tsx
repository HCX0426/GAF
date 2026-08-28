/**
 * SecuritySettings — two-step verify (2FA/TOTP) settings panel
 *
 * provides enable / disable TOTP second verify interact:
 * - not enabled when: generate secret and otpauth URI, show QR code and verify 6 digit verify code with complete enable.
 * - enabled when: verify current password after disable 2FA.
 * status change more after refresh current user info.
 */

import { useState } from 'react';
import { Card, Button, Modal, Input, QRCode, Space, Typography, Alert, App, Form } from 'antd';
import { SafetyCertificateOutlined, LockOutlined } from '@ant-design/icons';
import { useAuthStore } from '@/stores/useAuthStore';
import { setup2FA, verify2FASetup, disable2FA, changePassword } from '@/api/auth';
import { useTranslation } from '@/i18n';

const { Title, Text, Paragraph } = Typography;

/** Change password form — old + new + confirm, calls /accounts/auth/change-password/ (D7) */
function PasswordChangeForm() {
  const { message } = App.useApp();
  const t = useTranslation();
  const [form] = Form.useForm();
  const [changing, setChanging] = useState(false);

  const handleSubmit = async (values: { old_password: string; new_password: string; confirm_password: string }) => {
    if (values.new_password !== values.confirm_password) {
      message.warning(t('settings.security_pwd_mismatch'));
      return;
    }
    setChanging(true);
    try {
      await changePassword({ old_password: values.old_password, new_password: values.new_password });
      message.success(t('settings.security_pwd_updated'));
      form.resetFields();
    } catch {
      message.error(t('settings.security_pwd_failed'));
    } finally {
      setChanging(false);
    }
  };

  return (
    <Form form={form} layout="vertical" onFinish={handleSubmit}>
      <Form.Item
        name="old_password"
        label={t('settings.security_old_pwd')}
        rules={[{ required: true }]}
      >
        <Input.Password autoComplete="current-password" />
      </Form.Item>
      <Form.Item
        name="new_password"
        label={t('settings.security_new_pwd')}
        rules={[{ required: true, min: 6 }]}
      >
        <Input.Password autoComplete="new-password" />
      </Form.Item>
      <Form.Item
        name="confirm_password"
        label={t('settings.security_confirm_pwd')}
        dependencies={['new_password']}
        rules={[
          { required: true },
          ({ getFieldValue }) => ({
            validator(_, value) {
              if (!value || getFieldValue('new_password') === value) {
                return Promise.resolve();
              }
              return Promise.reject(new Error(t('settings.security_pwd_mismatch') || ''));
            },
          }),
        ]}
      >
        <Input.Password autoComplete="new-password" />
      </Form.Item>
      <Button type="primary" htmlType="submit" loading={changing}>
        {t('settings.security_password_change_btn')}
      </Button>
    </Form>
  );
}

/** security settings / 2FA management panel */
export function SecuritySettings() {
  const { message } = App.useApp();
  const t = useTranslation();
  const { user, refreshUser } = useAuthStore();

  const [setupOpen, setSetupOpen] = useState(false);
  const [disableOpen, setDisableOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [secret, setSecret] = useState('');
  const [otpUri, setOtpUri] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [password, setPassword] = useState('');

  const totpEnabled = user?.totp_enabled ?? false;

  /** send from 2FA setup, get secret and QR code URI */
  const handleStartSetup = async () => {
    setLoading(true);
    try {
      const data = await setup2FA();
      setSecret(data.secret);
      setOtpUri(data.otp_uri);
      setTotpCode('');
      setSetupOpen(true);
    } catch {
      message.error(t('settings.security_2fa_fetch_failed'));
    } finally {
      setLoading(false);
    }
  };

  /** verify 6 digit verify code and enable 2FA */
  const handleVerifySetup = async () => {
    if (totpCode.length !== 6) {
      message.warning(t('settings.security_2fa_code_required'));
      return;
    }
    setLoading(true);
    try {
      await verify2FASetup(totpCode);
      message.success(t('settings.security_2fa_enabled'));
      setSetupOpen(false);
      await refreshUser();
    } catch {
      message.error(t('settings.security_2fa_enable_failed'));
    } finally {
      setLoading(false);
    }
  };

  /** verify password and disable 2FA */
  const handleDisable = async () => {
    if (!password) {
      message.warning(t('settings.security_password_required'));
      return;
    }
    setLoading(true);
    try {
      await disable2FA(password);
      message.success(t('settings.security_2fa_disabled'));
      setDisableOpen(false);
      setPassword('');
      await refreshUser();
    } catch {
      message.error(t('settings.security_2fa_disable_failed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 600 }}>
      {/* Change password section (D7) */}
      <Title level={5}>
        <LockOutlined /> {t('settings.security_password_change_t')}
      </Title>
      <Card className="gaf-mb-lg">
        <PasswordChangeForm />
      </Card>

      <Title level={5}>
        <SafetyCertificateOutlined /> 两步验证 (2FA)
      </Title>

      <Card>
        <Space orientation="vertical" size="middle" className="gaf-w-full">
          <div className="gaf-flex-between">
            <div>
              <Text strong>TOTP 二次验证</Text>
              <br />
              <Text type="secondary">
                {totpEnabled ? '当前已启用，登录时需要输入验证码。' : '当前未启用，建议开启以提升账户安全。'}
              </Text>
            </div>
            {totpEnabled ? (
              <Button danger onClick={() => setDisableOpen(true)}>
                禁用 2FA
              </Button>
            ) : (
              <Button type="primary" loading={loading} onClick={handleStartSetup}>
                启用 2FA
              </Button>
            )}
          </div>
        </Space>
      </Card>

      <Modal
        title="启用两步验证"
        open={setupOpen}
        onCancel={() => setSetupOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setSetupOpen(false)}>
            取消
          </Button>,
          <Button
            key="verify"
            type="primary"
            loading={loading}
            disabled={totpCode.length !== 6}
            onClick={handleVerifySetup}
          >
            确认启用
          </Button>,
        ]}
      >
        <Space orientation="vertical" size="middle" className="gaf-w-full">
          <Alert
            type="info"
            showIcon
            message="请使用身份验证器扫描二维码"
            description="推荐使用 Google Authenticator、Microsoft Authenticator 或 Authy。"
          />
          <div style={{ display: 'flex', justifyContent: 'center' }}>{otpUri && <QRCode value={otpUri} />}</div>
          <Paragraph copyable={{ text: secret }}>
            <Text strong>密钥：</Text>
            <Text code>{secret}</Text>
          </Paragraph>
          <div>
            <Text>请输入验证器生成的 6 位验证码</Text>
            <Input.OTP length={6} value={totpCode} onChange={(v) => setTotpCode(v)} className="gaf-w-full gaf-mt-sm" />
          </div>
        </Space>
      </Modal>

      <Modal
        title="禁用两步验证"
        open={disableOpen}
        onCancel={() => setDisableOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setDisableOpen(false)}>
            取消
          </Button>,
          <Button key="disable" danger loading={loading} onClick={handleDisable}>
            确认禁用
          </Button>,
        ]}
      >
        <Space orientation="vertical" size="middle" className="gaf-w-full">
          <Alert type="warning" showIcon title="禁用后账户安全性将降低" />
          <div>
            <Text>请输入当前登录密码以确认</Text>
            <Input.Password
              prefix={<LockOutlined />}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="登录密码"
              className="gaf-mt-sm"
            />
          </div>
        </Space>
      </Modal>
    </div>
  );
}

export default SecuritySettings;
