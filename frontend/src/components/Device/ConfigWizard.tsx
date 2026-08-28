/**
 * 3-step device config wizard
 * guide user through screenshot method race, input method selection, one-click apply config.
 * get real available methods from backend PlatformCapabilities API.
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { Modal, Steps, Table, Tag, Radio, Switch, Button, Space, Descriptions, Result, message, Spin } from 'antd';
import { CheckCircleOutlined, ThunderboltOutlined, SettingOutlined } from '@ant-design/icons';
import { updateDevice, fetchPlatformCapabilities } from '@/api/devices';
import { useTranslation } from '@/i18n';
import type { ControlMode } from '@/types/models';

/** platform capabilities API returned method entry */
interface MethodEntry {
  id: string;
  name: string;
  priority: number;
  platform: string;
  description: string;
  available?: boolean;
}

/** platform capabilities API returned control mode entry */
interface ControlModeEntry {
  id: ControlMode;
  name: string;
  default_screenshot_method: string;
  default_input_method: string;
}

/** platform capabilities API returned structure */
interface PlatformCapabilities {
  platform: string;
  control_modes: ControlModeEntry[];
  screenshot_methods: MethodEntry[];
  adb_screenshot_methods: MethodEntry[];
  input_methods: MethodEntry[];
  adb_input_methods: MethodEntry[];
  runtime_screenshot_methods: string[];
  runtime_input_methods: string[];
}

/** ConfigWizard component props */
interface ConfigWizardProps {
  deviceId: number;
  deviceType: 'android' | 'windows';
  open: boolean;
  onClose: () => void;
}

/**
 * latency to corresponding color
 */
function getLatencyColor(priority: number): string {
  if (priority === 1) return 'green';
  if (priority <= 2) return '#faad14';
  return 'default';
}

/**
 * 3-step device config wizard
 * Step1: screenshot method race & selection, Step2: input method selection, Step3: summary confirm & apply
 */
export function ConfigWizard({ deviceId, deviceType, open, onClose }: ConfigWizardProps) {
  const [step, setStep] = useState(0);
  const t = useTranslation();
  const [selectedScreenshot, setSelectedScreenshot] = useState<string>('');
  const [selectedControlMode, setSelectedControlMode] = useState<ControlMode>('pseudo_background');
  const [advancedOverride, setAdvancedOverride] = useState(false);
  const [selectedInputOverride, setSelectedInputOverride] = useState<string>('');
  const [applying, setApplying] = useState(false);
  const [applyResult, setApplyResult] = useState<'success' | 'error' | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<PlatformCapabilities | null>(null);
  const [loadingCapabilities, setLoadingCapabilities] = useState(false);
  /** Track the close timer so it can be cleaned up on unmount */
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** Clear any pending close timer on unmount */
  useEffect(() => {
    return () => {
      if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
    };
  }, []);

  const isAndroid = deviceType === 'android';

  /** load platform capabilities from backend */
  useEffect(() => {
    if (!open) return;
    setLoadingCapabilities(true);
    fetchPlatformCapabilities<PlatformCapabilities>()
      .then((data) => setCapabilities(data))
      .catch(() => {
        message.warning(t('devices.platform_capabilities_unavailable'));
        setCapabilities(null);
      })
      .finally(() => setLoadingCapabilities(false));
  }, [open]);

  /** get screenshot method list by device type */
  const screenshotMethods = useMemo(() => {
    if (!capabilities) return [];
    return isAndroid ? capabilities.adb_screenshot_methods : capabilities.screenshot_methods;
  }, [capabilities, isAndroid]);

  /** get input method list by device type */
  const inputMethods = useMemo(() => {
    if (!capabilities) return [];
    return isAndroid ? capabilities.adb_input_methods : capabilities.input_methods;
  }, [capabilities, isAndroid]);

  /** recommend screenshot method (priority=1) */
  const recommendedMethod = useMemo(
    () => screenshotMethods.find((m) => m.priority === 1)?.id || '',
    [screenshotMethods],
  );

  /** reset state when modal opens */
  useEffect(() => {
    if (open) {
      setStep(0);
      setApplyResult(null);
      setApplyError(null);
    }
  }, [open]);

  /** Control mode list (same for Android/Windows) */
  const controlModes = useMemo(() => capabilities?.control_modes || [], [capabilities]);

  /** set default selection after capability data loaded */
  useEffect(() => {
    if (open && capabilities) {
      setSelectedScreenshot(recommendedMethod);
      const defaultMode = controlModes[0]?.id || 'pseudo_background';
      setSelectedControlMode(defaultMode);
      const modeDefaults = controlModes.find((m) => m.id === defaultMode);
      setSelectedInputOverride(modeDefaults?.default_input_method || inputMethods[0]?.id || '');
    }
  }, [open, capabilities, recommendedMethod, inputMethods, controlModes]);

  const handlePrev = useCallback(() => {
    setStep((s) => Math.max(0, s - 1));
  }, []);

  const handleNext = useCallback(() => {
    setStep((s) => Math.min(2, s + 1));
  }, []);

  const handleSkip = useCallback(() => {
    if (step >= 2) return;
    setStep((s) => s + 1);
  }, [step]);

  /** app config */
  const handleApply = useCallback(async () => {
    setApplying(true);
    setApplyResult(null);
    setApplyError(null);
    try {
      await updateDevice(deviceId, {
        screenshot_method: selectedScreenshot,
        control_mode: selectedControlMode,
        input_method: advancedOverride ? selectedInputOverride : '',
      });
      setApplyResult('success');
      if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
      closeTimerRef.current = setTimeout(() => {
        onClose();
      }, 1500);
    } catch {
      setApplyResult('error');
      setApplyError('配置应用失败，请检查设备连接后重试');
      message.error(t('devices.config_apply_failed'));
    } finally {
      setApplying(false);
    }
  }, [deviceId, selectedScreenshot, selectedControlMode, advancedOverride, selectedInputOverride, onClose]);

  const stepItems = [
    { title: t('devices.wizard_step_screenshot'), icon: <ThunderboltOutlined /> },
    { title: t('devices.wizard_step_control_mode'), icon: <SettingOutlined /> },
    { title: t('devices.wizard_step_apply'), icon: <CheckCircleOutlined /> },
  ];

  /** race table column definition */
  const screenshotColumns = [
    {
      title: '截图方式',
      dataIndex: 'name',
      key: 'name',
      width: 200,
      render: (val: string, record: MethodEntry) =>
        record.priority === 1 ? (
          <Space>
            {val}
            <Tag color="green">推荐</Tag>
          </Space>
        ) : (
          val
        ),
    },
    {
      title: '说明',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '状态',
      key: 'available',
      width: 80,
      render: (_: unknown, record: MethodEntry) => (
        <Tag color={record.available !== false ? 'green' : 'default'}>
          {record.available !== false ? '可用' : '不可用'}
        </Tag>
      ),
    },
    {
      title: '选择',
      key: 'select',
      width: 60,
      render: (_: unknown, record: MethodEntry) => (
        <Radio checked={selectedScreenshot === record.id} onChange={() => setSelectedScreenshot(record.id)} />
      ),
    },
  ];

  /** render step content */
  const renderStepContent = () => {
    if (loadingCapabilities) {
      return (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin description="加载平台能力..." />
        </div>
      );
    }

    switch (step) {
      case 0:
        return (
          <div>
            <p className="gaf-mb-lg" style={{ color: '#666' }}>
              当前平台: <Tag color="blue">{capabilities?.platform || 'unknown'}</Tag>
              {isAndroid ? ' · 模拟器/ADB 设备' : ' · PC 窗口设备'}
              <br />
              以下为各截图方式的优先级排序，<Tag color="green">推荐</Tag> 为最优选择。
            </p>
            <Table
              rowKey="id"
              columns={screenshotColumns}
              dataSource={screenshotMethods}
              size="small"
              pagination={false}
              rowClassName={(record: MethodEntry) => (record.priority === 1 ? 'config-wizard-recommended-row' : '')}
              onRow={(record: MethodEntry) => ({
                style: record.priority === 1 ? { background: '#f6ffed', cursor: 'pointer' } : { cursor: 'pointer' },
                onClick: () => setSelectedScreenshot(record.id),
              })}
            />
          </div>
        );

      case 1:
        return (
          <div>
            <p className="gaf-mb-lg" style={{ color: '#666' }}>
              {t('devices.wizard_control_mode_hint')}
            </p>
            <Radio.Group
              value={selectedControlMode}
              onChange={(e) => {
                const mode = e.target.value as ControlMode;
                setSelectedControlMode(mode);
                const modeDefaults = controlModes.find((m) => m.id === mode);
                setSelectedInputOverride(modeDefaults?.default_input_method || inputMethods[0]?.id || '');
              }}
            >
              <Space orientation="vertical" size="middle">
                {controlModes.map((item) => (
                  <Radio key={item.id} value={item.id}>
                    <Space>
                      <Tag color={item.id === 'foreground' ? 'green' : item.id === 'background' ? 'blue' : 'orange'}>
                        {item.name}
                      </Tag>
                      <span className="gaf-text-xs" style={{ color: '#999' }}>
                        {t('devices.wizard_control_mode_defaults', {
                          screenshot: item.default_screenshot_method,
                          input: item.default_input_method,
                        })}
                      </span>
                    </Space>
                  </Radio>
                ))}
              </Space>
            </Radio.Group>

            <div className="gaf-mt-xl" style={{ borderTop: '1px solid #f0f0f0', paddingTop: 16 }}>
              <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
                <Space>
                  <Switch
                    checked={advancedOverride}
                    onChange={(checked) => {
                      setAdvancedOverride(checked);
                      if (!checked) {
                        const modeDefaults = controlModes.find((m) => m.id === selectedControlMode);
                        setSelectedInputOverride(modeDefaults?.default_input_method || inputMethods[0]?.id || '');
                      }
                    }}
                  />
                  <span>{t('devices.wizard_advanced_override')}</span>
                </Space>
                {advancedOverride && (
                  <div>
                    <p className="gaf-mb-sm" style={{ color: '#666' }}>
                      {t('devices.wizard_input_override_hint')}
                    </p>
                    <Radio.Group
                      value={selectedInputOverride}
                      onChange={(e) => setSelectedInputOverride(e.target.value)}
                    >
                      <Space orientation="vertical" size="middle">
                        {inputMethods.map((item) => (
                          <Radio key={item.id} value={item.id}>
                            <Space>
                              {item.name}
                              <Tag color={getLatencyColor(item.priority)}>
                                {t('devices.wizard_priority', { priority: item.priority })}
                              </Tag>
                              <span className="gaf-text-xs" style={{ color: '#999' }}>
                                {item.description}
                              </span>
                            </Space>
                          </Radio>
                        ))}
                      </Space>
                    </Radio.Group>
                  </div>
                )}
              </Space>
            </div>
          </div>
        );

      case 2:
        return applyResult ? (
          <Result
            status={applyResult}
            title={applyResult === 'success' ? t('devices.wizard_apply_success') : t('devices.wizard_apply_failed')}
            subTitle={
              applyResult === 'error'
                ? applyError || t('devices.wizard_apply_unknown_error')
                : t('devices.wizard_apply_success_hint')
            }
            extra={
              applyResult === 'error' && (
                <Button type="primary" onClick={handleApply} loading={applying}>
                  {t('devices.wizard_retry')}
                </Button>
              )
            }
          />
        ) : (
          <div>
            <p className="gaf-mb-lg" style={{ color: '#666' }}>
              {t('devices.wizard_summary_hint')}
            </p>
            <Descriptions bordered size="small" column={1}>
              <Descriptions.Item label={t('devices.wizard_label_device_id')}>{deviceId}</Descriptions.Item>
              <Descriptions.Item label={t('devices.wizard_label_device_type')}>
                <Tag color={isAndroid ? 'green' : 'blue'}>{isAndroid ? 'Android' : 'Windows'}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('devices.wizard_label_platform')}>
                <Tag>{capabilities?.platform || 'unknown'}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('devices.wizard_label_screenshot_method')}>
                <Tag color="blue">
                  {screenshotMethods.find((m) => m.id === selectedScreenshot)?.name || selectedScreenshot}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('devices.wizard_label_control_mode')}>
                <Tag
                  color={
                    selectedControlMode === 'foreground'
                      ? 'green'
                      : selectedControlMode === 'background'
                        ? 'blue'
                        : 'orange'
                  }
                >
                  {controlModes.find((m) => m.id === selectedControlMode)?.name || selectedControlMode}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('devices.wizard_label_input_method')}>
                <Tag color="purple">
                  {advancedOverride
                    ? inputMethods.find((m) => m.id === selectedInputOverride)?.name || selectedInputOverride
                    : t('devices.wizard_input_derived', {
                        method: controlModes.find((m) => m.id === selectedControlMode)?.default_input_method || '',
                      })}
                </Tag>
              </Descriptions.Item>
            </Descriptions>
          </div>
        );
    }
  };

  return (
    <Modal
      title={t('devices.config_wizard_title')}
      open={open}
      onCancel={onClose}
      width={700}
      footer={null}
      destroyOnHidden
    >
      <Steps current={step} items={stepItems} className="gaf-mb-xl" />

      <div style={{ minHeight: 200 }}>{renderStepContent()}</div>

      {!applyResult && (
        <div
          className="gaf-mt-xl"
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            paddingTop: 16,
            borderTop: '1px solid #f0f0f0',
          }}
        >
          <Button disabled={step === 0} onClick={handlePrev}>
            {t('devices.wizard_prev')}
          </Button>
          <Space>
            {step < 2 && <Button onClick={handleSkip}>{t('devices.wizard_skip')}</Button>}
            {step < 2 ? (
              <Button type="primary" onClick={handleNext}>
                {t('devices.wizard_next')}
              </Button>
            ) : (
              <Button type="primary" onClick={handleApply} loading={applying}>
                {t('devices.wizard_apply')}
              </Button>
            )}
          </Space>
        </div>
      )}
    </Modal>
  );
}

export default ConfigWizard;
