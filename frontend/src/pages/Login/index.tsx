import { useState, useMemo, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, Button, Card, Modal, Checkbox, App, Divider, Space, Tabs, theme as antTheme } from 'antd';
import type { InputRef } from 'antd';
import { UserOutlined, LockOutlined, MailOutlined, GithubOutlined, GoogleOutlined } from '@ant-design/icons';
import { useAuthStore } from '@/stores/useAuthStore';
import {
  register as registerApi,
  getOAuthUrl,
  requestPasswordReset,
  confirmPasswordReset,
  getInitStatus,
} from '@/api/auth';
import { getRememberMe, getSavedUsername } from '@/utils/tokenStore';
import { classifyError, ErrorType } from '@/utils/errorHandler';
import { evaluatePasswordStrength } from '@/utils/passwordStrength';
import { useTranslation } from '@/i18n';

/** Password strength indicator using zxcvbn */
function PasswordStrength({ password }: { password: string }) {
  const t = useTranslation();
  const { token } = antTheme.useToken();
  const strength = evaluatePasswordStrength(password);
  const strengthColor = token[strength.colorToken as keyof typeof token] as string;

  return (
    <div className="gaf-mb-lg">
      {/* Progress bar */}
      <div className="gaf-mb-xs" style={{ height: 4, background: token.colorBorderSecondary, borderRadius: 2 }}>
        <div
          className="gaf-h-full"
          style={{
            width: `${strength.percent}%`,
            background: strengthColor,
            borderRadius: 2,
            transition: 'width 0.3s, background 0.3s',
          }}
        />
      </div>
      {/* Strength label and crack time */}
      <div className="gaf-mb-xs gaf-flex-between">
        <span className="gaf-text-xs gaf-font-medium" style={{ color: strengthColor }}>
          {t('login.password_strength', { label: strength.label })}
        </span>
        {password && (
          <span className="gaf-text-xs" style={{ color: token.colorTextTertiary }}>
            {t('login.password_crack_time', { time: strength.crackTime })}
          </span>
        )}
      </div>
      {/* Suggestions */}
      {strength.suggestions.length > 0 && password && (
        <div className="gaf-text-xs" style={{ color: token.colorWarning }}>
          {t('login.password_suggestions', { suggestions: strength.suggestions.join('，') })}
        </div>
      )}
    </div>
  );
}

export function LoginPage() {
  const { message } = App.useApp();
  const { token } = antTheme.useToken();
  const t = useTranslation();
  const [loading, setLoading] = useState(false);
  const [pwdModalOpen, setPwdModalOpen] = useState(false);
  const [pwdLoading, setPwdLoading] = useState(false);
  const [twoFAModalOpen, setTwoFAModalOpen] = useState(false);
  const [twoFACode, setTwoFACode] = useState('');
  const [twoFALoading, setTwoFALoading] = useState(false);
  const [registerPassword, setRegisterPassword] = useState('');
  const [changeNewPassword, setChangeNewPassword] = useState('');
  const [resetModalOpen, setResetModalOpen] = useState(false);
  const [resetStep, setResetStep] = useState<'email' | 'confirm'>('email');
  const [resetToken, setResetToken] = useState('');
  const [resetLoading, setResetLoading] = useState(false);
  const [resetNewPassword, setResetNewPassword] = useState('');
  const [registerEnabled, setRegisterEnabled] = useState(true);
  const { login, login2FA, changePassword } = useAuthStore();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const navigate = useNavigate();
  const passwordRef = useRef<InputRef>(null);

  /** Redirect to dashboard when already authenticated (remember me). */
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/dashboard', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  /** Fetch system init status and registration flag. */
  useEffect(() => {
    const controller = new AbortController();
    getInitStatus({ signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return;
        setRegisterEnabled(data.register_enabled);
      })
      .catch((err: unknown) => {
        if ((err as Error)?.name === 'AbortError') return;
        // Default to allowing registration on fetch failure
        setRegisterEnabled(true);
      });
    return () => {
      controller.abort();
    };
  }, []);

  const initVals = useMemo(
    () => ({
      username: getSavedUsername() || '',
      remember_me: getRememberMe(),
    }),
    [],
  );
  const [form] = Form.useForm();
  const [registerForm] = Form.useForm();
  const [pwdForm] = Form.useForm();

  const handleLogin = async (values: { username: string; password: string; remember_me: boolean }) => {
    setLoading(true);
    try {
      await login(values.username, values.password, values.remember_me);
      if (useAuthStore.getState().requires2FA) {
        setTwoFAModalOpen(true);
      } else if (useAuthStore.getState().mustChangePassword) {
        setPwdModalOpen(true);
      } else {
        message.success(t('login.login_success'));
        navigate('/dashboard');
      }
    } catch (err: unknown) {
      const classified = classifyError(err);
      if (classified.type === ErrorType.NETWORK || classified.type === ErrorType.TIMEOUT) {
        message.error(t('login.server_unreachable'));
      } else if (classified.type === ErrorType.AUTH) {
        message.error(t('login.wrong_credentials'));
      } else {
        message.error(classified.message);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (values: {
    username: string;
    email?: string;
    password: string;
    confirm_password: string;
  }) => {
    setLoading(true);
    try {
      await registerApi(values);
      message.success(t('login.register_success'));
      navigate('/dashboard');
    } catch (err: unknown) {
      const classified = classifyError(err);
      if (classified.type === ErrorType.NETWORK || classified.type === ErrorType.TIMEOUT) {
        message.error(t('login.service_unreachable'));
      } else if (
        classified.statusCode === 400 &&
        (classified.message.includes('已存在') || classified.message.includes('already exists'))
      ) {
        message.error(t('login.username_exists'));
      } else {
        message.error(t('login.register_failed', { message: classified.message }));
      }
    } finally {
      setLoading(false);
    }
  };

  const handle2FASubmit = async () => {
    if (twoFACode.length !== 6) {
      message.warning(t('login.2fa_code_required'));
      return;
    }
    setTwoFALoading(true);
    try {
      await login2FA(twoFACode);
      message.success(t('login.login_success'));
      setTwoFAModalOpen(false);
      setTwoFACode('');
      if (useAuthStore.getState().mustChangePassword) {
        setPwdModalOpen(true);
      } else {
        navigate('/dashboard');
      }
    } catch (err: unknown) {
      const classified = classifyError(err);
      if (classified.type === ErrorType.NETWORK || classified.type === ErrorType.TIMEOUT) {
        message.error(t('login.server_unreachable'));
      } else if (classified.type === ErrorType.AUTH) {
        message.error(t('login.2fa_invalid'));
      } else {
        message.error(classified.message);
      }
    } finally {
      setTwoFALoading(false);
    }
  };

  const handleChangePassword = async (values: { old_password: string; new_password: string }) => {
    setPwdLoading(true);
    try {
      await changePassword(values.old_password, values.new_password);
      message.success(t('login.password_changed'));
      setPwdModalOpen(false);
      navigate('/dashboard');
    } catch (err: unknown) {
      const classified = classifyError(err);
      if (classified.type === ErrorType.NETWORK || classified.type === ErrorType.TIMEOUT) {
        message.error(t('login.server_unreachable'));
      } else {
        message.error(t('login.password_change_failed', { message: classified.message }));
      }
    } finally {
      setPwdLoading(false);
    }
  };

  const handleResetRequest = async (values: { email: string }) => {
    setResetLoading(true);
    try {
      const res = await requestPasswordReset(values.email);
      if (res.reset_token) {
        setResetToken(res.reset_token);
        setResetStep('confirm');
        message.success(t('login.reset_code_generated'));
      } else {
        message.success(t('login.reset_link_sent'));
        setResetModalOpen(false);
      }
    } catch (err: unknown) {
      const classified = classifyError(err);
      if (classified.type === ErrorType.NETWORK || classified.type === ErrorType.TIMEOUT) {
        message.error(t('login.server_unreachable'));
      } else if (classified.type === ErrorType.CLIENT && classified.statusCode === 404) {
        message.error(t('login.reset_email_not_registered'));
      } else {
        message.error(t('login.reset_request_failed', { message: classified.message }));
      }
    } finally {
      setResetLoading(false);
    }
  };

  const handleResetConfirm = async (values: { new_password: string; confirm_password: string }) => {
    setResetLoading(true);
    try {
      await confirmPasswordReset({ token: resetToken, ...values });
      message.success(t('login.reset_success'));
      setResetModalOpen(false);
      setResetStep('email');
      setResetToken('');
    } catch (err: unknown) {
      const classified = classifyError(err);
      if (classified.type === ErrorType.NETWORK || classified.type === ErrorType.TIMEOUT) {
        message.error(t('login.server_unreachable'));
      } else if (
        classified.type === ErrorType.AUTH ||
        (classified.type === ErrorType.CLIENT && classified.statusCode === 400)
      ) {
        message.error(t('login.reset_link_invalid'));
      } else {
        message.error(t('login.reset_failed', { message: classified.message }));
      }
    } finally {
      setResetLoading(false);
    }
  };

  return (
    <div className="gaf-flex-center gaf-justify-center gaf-min-h-screen" style={{ background: token.colorBgLayout }}>
      <Card style={{ width: 420, boxShadow: '0 2px 8px rgba(0,0,0,0.15)' }}>
        <div className="gaf-mb-xl gaf-text-center">
          <h1 className="gaf-m-0 gaf-text-28">{t('login.platform_name')}</h1>
          <p className="gaf-mt-sm" style={{ color: token.colorTextTertiary }}>
            {t('login.platform_subtitle')}
          </p>
        </div>

        <Tabs
          centered
          items={[
            {
              key: 'login',
              label: t('login.tab_login'),
              children: (
                <Form form={form} onFinish={handleLogin} size="large" initialValues={initVals}>
                  <Form.Item name="username" rules={[{ required: true, message: t('login.username_required') }]}>
                    <Input
                      prefix={<UserOutlined />}
                      placeholder={t('login.username_placeholder')}
                      autoComplete="username"
                      spellCheck={false}
                      onPressEnter={() => passwordRef.current?.focus()}
                    />
                  </Form.Item>
                  <Form.Item name="password" rules={[{ required: true, message: t('login.password_required') }]}>
                    <Input.Password
                      prefix={<LockOutlined />}
                      placeholder={t('login.password_placeholder')}
                      autoComplete="current-password"
                      ref={passwordRef}
                      onPressEnter={() => form.submit()}
                    />
                  </Form.Item>
                  <Form.Item name="remember_me" valuePropName="checked">
                    <div className="gaf-flex-between">
                      <Checkbox>{t('login.remember_me')}</Checkbox>
                      <Button type="link" onClick={() => setResetModalOpen(true)} className="gaf-p-0 gaf-text-13">
                        {t('login.forgot_password')}
                      </Button>
                    </div>
                  </Form.Item>
                  <Form.Item>
                    <Button type="primary" htmlType="submit" loading={loading} block>
                      {t('login.login_btn')}
                    </Button>
                  </Form.Item>
                </Form>
              ),
            },
            ...(registerEnabled
              ? [
                  {
                    key: 'register',
                    label: t('login.tab_register'),
                    children: (
                      <Form form={registerForm} onFinish={handleRegister} size="large">
                        <Form.Item name="username" rules={[{ required: true, message: t('login.username_required') }]}>
                          <Input
                            prefix={<UserOutlined />}
                            placeholder={t('login.username_placeholder')}
                            autoComplete="username"
                            spellCheck={false}
                          />
                        </Form.Item>
                        <Form.Item name="email" rules={[{ type: 'email', message: t('login.email_invalid') }]}>
                          <Input
                            prefix={<MailOutlined />}
                            placeholder={t('login.email')}
                            autoComplete="email"
                            spellCheck={false}
                          />
                        </Form.Item>
                        <Form.Item
                          name="password"
                          rules={[{ required: true, min: 6, message: t('login.password_min_length') }]}
                        >
                          <Input.Password
                            prefix={<LockOutlined />}
                            placeholder={t('login.password_placeholder')}
                            autoComplete="new-password"
                            onChange={(e) => setRegisterPassword(e.target.value)}
                          />
                        </Form.Item>
                        <PasswordStrength password={registerPassword} />
                        <Form.Item
                          name="confirm_password"
                          dependencies={['password']}
                          rules={[
                            { required: true, message: t('login.confirm_password_required') },
                            ({ getFieldValue }) => ({
                              validator(_, value) {
                                if (!value || getFieldValue('password') === value) {
                                  return Promise.resolve();
                                }
                                return Promise.reject(new Error(t('login.password_mismatch')));
                              },
                            }),
                          ]}
                        >
                          <Input.Password
                            prefix={<LockOutlined />}
                            placeholder={t('login.confirm_password')}
                            autoComplete="new-password"
                          />
                        </Form.Item>
                        <Form.Item>
                          <Button type="primary" htmlType="submit" loading={loading} block>
                            {t('login.register_btn')}
                          </Button>
                        </Form.Item>
                      </Form>
                    ),
                  },
                ]
              : []),
          ]}
        />

        <Divider plain>{t('login.third_party_login')}</Divider>
        <Space orientation="vertical" className="gaf-w-full">
          <Button
            icon={<GithubOutlined />}
            block
            onClick={() => {
              window.location.href = getOAuthUrl('github');
            }}
          >
            {t('login.login_with_github')}
          </Button>
          <Button
            icon={<GoogleOutlined />}
            block
            onClick={() => {
              window.location.href = getOAuthUrl('google');
            }}
          >
            {t('login.login_with_google')}
          </Button>
        </Space>
      </Card>

      <Modal
        title={t('login.change_password_title')}
        open={pwdModalOpen}
        closable={false}
        footer={null}
        mask={{ closable: false }}
      >
        <p className="gaf-mb-lg" style={{ color: token.colorError }}>
          {t('login.first_login_change_password')}
        </p>
        <Form form={pwdForm} onFinish={handleChangePassword}>
          <Form.Item name="old_password" rules={[{ required: true, message: t('login.old_password_required') }]}>
            <Input.Password
              prefix={<LockOutlined />}
              placeholder={t('login.old_password')}
              autoComplete="current-password"
            />
          </Form.Item>
          <Form.Item
            name="new_password"
            rules={[{ required: true, min: 6, message: t('login.new_password_min_length') }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder={t('login.new_password_placeholder')}
              autoComplete="new-password"
              onChange={(e) => setChangeNewPassword(e.target.value)}
            />
          </Form.Item>
          <PasswordStrength password={changeNewPassword} />
          <Form.Item
            name="confirm_password"
            dependencies={['new_password']}
            rules={[
              { required: true, message: t('login.confirm_new_password_required') },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('new_password') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error(t('login.password_mismatch')));
                },
              }),
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder={t('login.confirm_new_password')}
              autoComplete="new-password"
            />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={pwdLoading} block>
              {t('login.confirm_change')}
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t('login.2fa_title')}
        open={twoFAModalOpen}
        closable={true}
        onCancel={() => {
          setTwoFAModalOpen(false);
          setTwoFACode('');
          useAuthStore.getState().clear2FA();
        }}
        footer={null}
        mask={{ closable: false }}
      >
        <p className="gaf-mb-lg">{t('login.2fa_enter_code')}</p>
        <Input.OTP
          length={6}
          value={twoFACode}
          onChange={(val) => setTwoFACode(val)}
          size="large"
          autoComplete="one-time-code"
          spellCheck={false}
          className="gaf-mb-lg"
        />
        <Button type="primary" loading={twoFALoading} block onClick={handle2FASubmit} disabled={twoFACode.length !== 6}>
          {t('login.2fa_verify')}
        </Button>
      </Modal>

      <Modal
        title={t('login.reset_password_title')}
        open={resetModalOpen}
        onCancel={() => {
          setResetModalOpen(false);
          setResetStep('email');
          setResetToken('');
        }}
        footer={null}
        mask={{ closable: false }}
        destroyOnHidden
      >
        {resetStep === 'email' ? (
          <Form onFinish={handleResetRequest} size="large">
            <p className="gaf-mb-lg">{t('login.reset_enter_email')}</p>
            <Form.Item name="email" rules={[{ required: true, type: 'email', message: t('login.email_invalid') }]}>
              <Input
                prefix={<MailOutlined />}
                placeholder={t('login.reset_email')}
                autoComplete="email"
                spellCheck={false}
              />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" loading={resetLoading} block>
                {t('login.reset_send_code')}
              </Button>
            </Form.Item>
          </Form>
        ) : (
          <Form onFinish={handleResetConfirm} size="large">
            <p className="gaf-mb-lg">{t('login.reset_set_new_password')}</p>
            <Form.Item label={t('login.reset_code')} className="gaf-mb-sm">
              <Input value={resetToken} disabled />
            </Form.Item>
            <Form.Item
              name="new_password"
              rules={[{ required: true, min: 6, message: t('login.password_min_length') }]}
            >
              <Input.Password
                prefix={<LockOutlined />}
                placeholder={t('login.new_password_placeholder')}
                onChange={(e) => setResetNewPassword(e.target.value)}
              />
            </Form.Item>
            <PasswordStrength password={resetNewPassword} />
            <Form.Item
              name="confirm_password"
              dependencies={['new_password']}
              rules={[
                { required: true, message: t('login.confirm_new_password_required') },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('new_password') === value) {
                      return Promise.resolve();
                    }
                    return Promise.reject(new Error(t('login.password_mismatch')));
                  },
                }),
              ]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder={t('login.confirm_new_password')} />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" loading={resetLoading} block>
                {t('login.reset_confirm')}
              </Button>
            </Form.Item>
            <Button type="link" onClick={() => setResetStep('email')} className="gaf-p-0">
              {t('login.reset_reenter_email')}
            </Button>
          </Form>
        )}
      </Modal>
    </div>
  );
}

export default LoginPage;
