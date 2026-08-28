import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Steps, Button, App, Spin } from 'antd';
import { useNavigate } from 'react-router-dom';
import StepCreateAdmin from './StepCreateAdmin';
import StepConfigureInfra from './StepConfigureInfra';
import StepDeviceScan from './StepDeviceScan';
import StepRecommendedTemplates from './StepRecommendedTemplates';
import { checkHasAdmin } from '@/api/init';
import { useTranslation } from '@/i18n';

const STEP_KEYS = [
  'setup.step_create_admin',
  'setup.step_configure_infra',
  'setup.step_device_scan',
  'setup.step_select_templates',
];

/**
 * system initial start transform to export — main entry
 * use Ant Design Steps component implementation 4 step to export pipeline
 * no Layout fullscreen show, detect existing management user when redirect /login
 */
const SetupPage: React.FC = () => {
  const t = useTranslation();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(0);
  const [loading, setLoading] = useState(true);
  /** Track the finish redirect timer so it can be cleaned up on unmount */
  const finishTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const setupSteps = useMemo(() => STEP_KEYS.map((key) => ({ title: t(key) })), [t]);

  useEffect(() => {
    checkHasAdmin()
      .then((exists) => {
        if (exists) {
          navigate('/login', { replace: true });
        } else {
          setLoading(false);
        }
      })
      .catch((err) => {
        console.error('Setup init failed:', err);
        setLoading(false);
      });
  }, [navigate]);

  /** Clear any pending redirect timer on unmount */
  useEffect(() => {
    return () => {
      if (finishTimerRef.current) clearTimeout(finishTimerRef.current);
    };
  }, []);

  const handleNext = () => setCurrentStep((prev) => Math.min(prev + 1, 3));

  const handlePrev = () => setCurrentStep((prev) => Math.max(prev - 1, 0));

  const handleFinish = () => {
    message.success(t('setup.msg_init_complete'));
    if (finishTimerRef.current) clearTimeout(finishTimerRef.current);
    finishTimerRef.current = setTimeout(() => navigate('/login', { replace: true }), 1500);
  };

  const renderStepContent = () => {
    switch (currentStep) {
      case 0:
        return <StepCreateAdmin onSuccess={handleNext} />;
      case 1:
        return <StepConfigureInfra onNext={handleNext} />;
      case 2:
        return <StepDeviceScan onNext={handleNext} />;
      case 3:
        return <StepRecommendedTemplates onFinish={handleFinish} />;
      default:
        return null;
    }
  };

  if (loading) {
    return (
      <div className="gaf-flex-center gaf-justify-center" style={{ height: '100vh' }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 720, margin: '40px auto', padding: '0 24px' }}>
      <h1 className="gaf-text-center" style={{ marginBottom: 32 }}>
        {t('setup.page_title')}
      </h1>
      <Steps
        current={currentStep}
        style={{ marginBottom: 40 }}
        items={setupSteps.map((step) => ({ title: step.title }))}
      />
      <div style={{ minHeight: 300 }}>{renderStepContent()}</div>
      <div className="gaf-flex gaf-flex-between" style={{ marginTop: 32 }}>
        <Button onClick={handlePrev} disabled={currentStep === 0}>
          {t('setup.btn_prev')}
        </Button>
      </div>
    </div>
  );
};

export default SetupPage;
