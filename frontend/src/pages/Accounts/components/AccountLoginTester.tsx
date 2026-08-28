/**
 * account login test Modal
 * select in online device after test specified account login pipeline
 */
import { useState, useEffect } from 'react';
import { Modal, Select, Button, Spin, Result, App, Space, theme } from 'antd';
import { LoadingOutlined } from '@ant-design/icons';
import { testLoginAccount } from '@/api/accounts';
import { useDeviceStore } from '@/stores/useDeviceStore';
import { useTranslation } from '@/i18n';

interface AccountLoginTesterProps {
  accountId: number;
  accountName: string;
  open: boolean;
  onClose: () => void;
}

/** login test step */
type TestStep = 'select' | 'testing' | 'success' | 'error';

/**
 * account login test component
 * select one item in online device after send from login test request
 */
export function AccountLoginTester({ accountId, accountName, open, onClose }: AccountLoginTesterProps) {
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const t = useTranslation();
  const [deviceId, setDeviceId] = useState<number | undefined>(undefined);
  const [step, setStep] = useState<TestStep>('select');
  const [errorMsg, setErrorMsg] = useState('');

  const { agents, fetchAgents } = useDeviceStore();

  /** load in online device list */
  useEffect(() => {
    if (open) {
      fetchAgents();
      setStep('select');
      setDeviceId(undefined);
      setErrorMsg('');
    }
  }, [open, fetchAgents]);

  /** in online device option */
  const deviceOptions = agents
    .filter((a) => a.status !== 'offline')
    .map((a) => ({
      label: `${a.hostname} (${a.ip_address})`,
      value: a.id,
    }));

  /**
   * start test login
   */
  const handleStartTest = async () => {
    if (!deviceId) {
      message.warning(t('accounts.select_device_warning'));
      return;
    }

    setStep('testing');
    try {
      const result = await testLoginAccount(accountId, { device_id: deviceId });
      if (result.success) {
        setStep('success');
        message.success(t('accounts.login_test_success'));
      } else {
        setStep('error');
        setErrorMsg(result.message || t('accounts.login_test_failed_msg'));
      }
    } catch (err: unknown) {
      setStep('error');
      if (err instanceof Error && err.message?.includes('timeout')) {
        setErrorMsg(t('accounts.connection_timeout'));
      } else {
        setErrorMsg((err as Error)?.message || t('accounts.login_test_request_failed'));
      }
    }
  };

  /**
   * close when reset status
   */
  const handleClose = () => {
    setStep('select');
    onClose();
  };

  return (
    <Modal
      title={t('accounts.test_login_title', { name: accountName })}
      open={open}
      onCancel={handleClose}
      footer={step === 'select' ? undefined : null}
      destroyOnHidden
    >
      {step === 'select' && (
        <Space orientation="vertical" className="gaf-w-full">
          <Select
            value={deviceId}
            onChange={setDeviceId}
            placeholder={t('accounts.select_device')}
            options={deviceOptions}
            className="gaf-w-full"
            notFoundContent={t('accounts.no_online_devices')}
          />
          <Button type="primary" onClick={handleStartTest} block>
            {t('accounts.start_test')}
          </Button>
        </Space>
      )}

      {step === 'testing' && (
        <div className="gaf-text-center" style={{ padding: '32px 0' }}>
          <Spin indicator={<LoadingOutlined style={{ fontSize: 36 }} spin />} />
          <p className="gaf-mt-lg" style={{ color: token.colorTextTertiary }}>
            {t('accounts.testing_login')}
          </p>
        </div>
      )}

      {step === 'success' && (
        <Result
          status="success"
          title={t('accounts.login_test_success')}
          subTitle={t('accounts.login_test_success_sub', { name: accountName })}
          extra={
            <Button type="primary" onClick={handleClose}>
              {t('accounts.close')}
            </Button>
          }
        />
      )}

      {step === 'error' && (
        <Result
          status="error"
          title={t('accounts.login_test_failed')}
          subTitle={errorMsg}
          extra={
            <Space>
              <Button onClick={() => setStep('select')}>{t('accounts.retry')}</Button>
              <Button type="primary" onClick={handleClose}>
                {t('accounts.close')}
              </Button>
            </Space>
          }
        />
      )}
    </Modal>
  );
}

export default AccountLoginTester;
