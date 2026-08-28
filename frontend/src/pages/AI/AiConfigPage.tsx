/**
 * AI Model Configuration Page
 * LLM provider management: API keys, models, connection testing
 */
import { useEffect, useState } from 'react';
import {
  Card,
  Form,
  Input,
  Select,
  Switch,
  Button,
  Space,
  Typography,
  Alert,
  Tag,
  Spin,
  Divider,
  Descriptions,
  App,
  Tabs,
} from 'antd';
import {
  SettingOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ThunderboltOutlined,
  KeyOutlined,
  SaveOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  InfoCircleOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { fetchLlmProviderConfig, createLlmProviderConfig, updateLlmProviderConfig, testLlmConnection } from '@/api/ai';
import { useTranslation, getLocale } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';

const { Text, Paragraph } = Typography;

/** LLM provider preset configurations */
const PROVIDER_PRESETS: Record<
  string,
  { labelKey: string; apiBase: string; defaultModel: string; color: string; icon: string }
> = {
  openai: {
    labelKey: 'ailab.provider_openai',
    apiBase: 'https://api.openai.com/v1',
    defaultModel: 'gpt-4o-mini',
    color: '#10a37f',
    icon: '🟢',
  },
  deepseek: {
    labelKey: 'ailab.provider_deepseek',
    apiBase: 'https://api.deepseek.com/v1',
    defaultModel: 'deepseek-chat',
    color: '#4d6bfe',
    icon: '🔵',
  },
  qwen: {
    labelKey: 'ailab.provider_qwen',
    apiBase: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    defaultModel: 'qwen-max',
    color: '#ff6a00',
    icon: '🟠',
  },
  ollama: {
    labelKey: 'ailab.provider_ollama',
    apiBase: 'http://localhost:11434/v1',
    defaultModel: 'llama3',
    color: '#00a67e',
    icon: '🟢',
  },
  custom: { labelKey: 'ailab.provider_custom', apiBase: '', defaultModel: '', color: '#8c8c8c', icon: '⚙️' },
};

/** Connection test result interface */
interface TestResult {
  success: boolean;
  latencyMs: number;
  model: string;
  message: string;
  responsePreview?: string;
}

/** Provider configuration state */
interface ProviderConfig {
  id?: number;
  provider: string;
  api_key: string;
  api_base: string;
  default_model: string;
  temperature: number;
  max_tokens: number;
  is_active: boolean;
  last_tested_at?: string;
  test_status?: 'success' | 'failed' | null;
}

export function AiConfigPage() {
  const t = useTranslation();
  const { message: msgApi } = App.useApp();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [config, setConfig] = useState<ProviderConfig | null>(null);
  const [activeTab, setActiveTab] = useState('configure');
  const [showApiKey, setShowApiKey] = useState(false);

  /** Load current LLM configuration from backend */
  useEffect(() => {
    loadConfig();
  }, []);

  /** Fetch LLM config from backend API */
  const loadConfig = async () => {
    setLoading(true);
    try {
      const data = await fetchLlmProviderConfig();
      if (Array.isArray(data)) {
        setConfig(data.length > 0 ? data[0] : null);
        if (data[0]) {
          form.setFieldsValue({
            provider: data[0].provider || 'openai',
            api_key: data[0].api_key || '',
            api_base: data[0].api_base || '',
            default_model: data[0].default_model || '',
            temperature: data[0].temperature ?? 0.7,
            max_tokens: data[0].max_tokens ?? 4096,
            is_active: data[0].is_active ?? true,
          });
        }
      } else if (data && typeof data === 'object') {
        setConfig(data);
        form.setFieldsValue({
          provider: data.provider || 'openai',
          api_key: data.api_key || '',
          api_base: data.api_base || '',
          default_model: data.default_model || '',
          temperature: data.temperature ?? 0.7,
          max_tokens: data.max_tokens ?? 4096,
          is_active: data.is_active ?? true,
        });
      }
    } catch {
      msgApi.warning(t('ailab.msg_load_config_failed'));
      form.setFieldsValue({
        provider: 'openai',
        api_base: PROVIDER_PRESETS.openai.apiBase,
        default_model: PROVIDER_PRESETS.openai.defaultModel,
        temperature: 0.7,
        max_tokens: 4096,
        is_active: true,
      });
    } finally {
      setLoading(false);
    }
  };

  /** Handle provider selection change — auto-fill presets */
  const handleProviderChange = (providerKey: string) => {
    const preset = PROVIDER_PRESETS[providerKey];
    if (preset) {
      form.setFieldValue('api_base', preset.apiBase);
      form.setFieldValue('default_model', preset.defaultModel);
    }
  };

  /** Test connection to LLM API */
  const handleTestConnection = async () => {
    const values = await form.validateFields().catch(() => null);
    if (!values) return;

    setTesting(true);
    setTestResult(null);
    try {
      const data = await testLlmConnection(
        {
          messages: [{ role: 'user', content: 'Hello, this is a connection test. Reply with "OK" only.' }],
          model: values.default_model,
          max_tokens: 10,
          temperature: 0,
        },
        { timeout: 15000 },
      );

      const startTime = Date.now();
      const result: TestResult = {
        success: true,
        latencyMs: Date.now() - startTime,
        model: values.default_model,
        message: t('ailab.msg_connection_success'),
        responsePreview: (data?.content || data?.choices?.[0]?.message?.content || '').slice(0, 100),
      };
      setTestResult(result);
      msgApi.success(t('ailab.msg_connection_success_latency', { latencyMs: result.latencyMs }));
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : t('ailab.msg_connection_failed');
      setTestResult({
        success: false,
        latencyMs: 0,
        model: values.default_model,
        message: t('ailab.msg_connection_failed_with_err', { message: errMsg }),
      });
      msgApi.error(t('ailab.msg_connection_test_failed'));
    } finally {
      setTesting(false);
    }
  };

  /** Save configuration to backend */
  const handleSave = async () => {
    const values = await form.validateFields().catch(() => null);
    if (!values) return;

    setSaving(true);
    try {
      const payload = {
        ...values,
        is_active: values.is_active ?? true,
      };

      if (config?.id) {
        await updateLlmProviderConfig(config.id, payload);
      } else {
        await createLlmProviderConfig(payload);
      }

      msgApi.success(t('ailab.msg_config_saved'));
      loadConfig();
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : t('ailab.msg_save_failed');
      msgApi.error(t('ailab.msg_save_failed_with_err', { message: errMsg }));
    } finally {
      setSaving(false);
    }
  };

  /** Reset to defaults */
  const handleReset = () => {
    form.setFieldsValue({
      provider: 'openai',
      api_key: '',
      api_base: PROVIDER_PRESETS.openai.apiBase,
      default_model: PROVIDER_PRESETS.openai.defaultModel,
      temperature: 0.7,
      max_tokens: 4096,
      is_active: true,
    });
    setTestResult(null);
    msgApi.info(t('ailab.msg_reset_done'));
  };

  const selectedProvider = Form.useWatch('provider', form);
  const providerPreset = selectedProvider ? PROVIDER_PRESETS[selectedProvider] : null;

  return (
    <PageWrapper>
      <div className="gaf-p-xl" style={{ maxWidth: 900, margin: '0 auto' }}>
        <Card
          size="small"
          title={
            <span>
              <SettingOutlined /> {t('ailab.card_model_config')}
            </span>
          }
        >
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            size="small"
            items={[
              {
                key: 'configure',
                label: (
                  <span>
                    <SettingOutlined /> {t('ailab.tab_basic_config')}
                  </span>
                ),
                children: (
                  <Spin spinning={loading}>
                    <Form form={form} layout="vertical" style={{ maxWidth: 700 }}>
                      {/* Provider Selection */}
                      <Form.Item
                        name="provider"
                        label={t('ailab.label_provider')}
                        rules={[{ required: true, message: t('ailab.msg_provider_required') }]}
                      >
                        <Select
                          placeholder={t('ailab.placeholder_select_provider')}
                          onChange={handleProviderChange}
                          options={Object.entries(PROVIDER_PRESETS).map(([key, p]) => ({
                            value: key,
                            label: (
                              <span>
                                <span className="gaf-mr-sm">{p.icon}</span>
                                {t(p.labelKey)}
                                <Tag color={p.color} className="gaf-ml-sm">
                                  {p.apiBase.replace('https://', '').replace('http://', '')}
                                </Tag>
                              </span>
                            ),
                          }))}
                        />
                      </Form.Item>

                      {/* API Credentials */}
                      <Card
                        size="small"
                        title={
                          <span>
                            <KeyOutlined /> {t('ailab.card_api_credentials')}
                          </span>
                        }
                        className="gaf-mb-lg"
                      >
                        <Form.Item
                          name="api_key"
                          label="API Key"
                          rules={[{ required: true, message: t('ailab.msg_api_key_required') }]}
                        >
                          <Input.Password
                            placeholder={t('ailab.placeholder_api_key')}
                            visibilityToggle={{ visible: showApiKey, onVisibleChange: setShowApiKey }}
                            autoComplete="current-password"
                          />
                        </Form.Item>
                        <Form.Item
                          name="api_base"
                          label="API Base URL"
                          rules={[{ required: true, message: t('ailab.msg_base_url_required') }]}
                          extra={
                            providerPreset
                              ? t('ailab.label_preset') + ': ' + providerPreset.apiBase
                              : t('ailab.placeholder_custom_api_url')
                          }
                        >
                          <Input placeholder="https://api.openai.com/v1" />
                        </Form.Item>
                      </Card>

                      {/* Model & Parameters */}
                      <Card
                        size="small"
                        title={
                          <span>
                            <ThunderboltOutlined /> {t('ailab.card_model_params')}
                          </span>
                        }
                        className="gaf-mb-lg"
                      >
                        <Form.Item
                          name="default_model"
                          label={t('ailab.label_default_model')}
                          rules={[{ required: true, message: t('ailab.msg_model_name_required') }]}
                          extra={
                            providerPreset ? t('ailab.label_recommended') + ': ' + providerPreset.defaultModel : ''
                          }
                        >
                          <Input placeholder="gpt-4o-mini / deepseek-chat / qwen-max / llama3" />
                        </Form.Item>
                        <Space className="gaf-w-full" size="middle">
                          <Form.Item
                            name="temperature"
                            label="Temperature"
                            className="gaf-flex-1 gaf-m-0"
                            extra={t('ailab.help_temperature')}
                          >
                            <Input type="number" step={0.1} min={0} max={2} />
                          </Form.Item>
                          <Form.Item
                            name="max_tokens"
                            label="Max Tokens"
                            className="gaf-flex-1 gaf-m-0"
                            extra={t('ailab.help_max_tokens')}
                          >
                            <Input type="number" min={1} max={128000} />
                          </Form.Item>
                        </Space>
                        <Form.Item name="is_active" label={t('ailab.label_enable_config')} valuePropName="checked">
                          <Switch
                            checkedChildren={t('ailab.switch_enabled')}
                            unCheckedChildren={t('ailab.switch_disabled')}
                          />
                        </Form.Item>
                      </Card>

                      {/* Actions */}
                      <Divider />
                      <Space>
                        <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
                          {t('ailab.btn_save_config')}
                        </Button>
                        <Button
                          icon={<PlayCircleOutlined />}
                          loading={testing}
                          onClick={handleTestConnection}
                          disabled={!form.getFieldValue('api_key')}
                        >
                          {t('ailab.btn_test_connection')}
                        </Button>
                        <Button icon={<ReloadOutlined />} onClick={handleReset}>
                          {t('ailab.btn_reset')}
                        </Button>
                      </Space>

                      {/* Test Result */}
                      {testResult && (
                        <Alert
                          type={testResult.success ? 'success' : 'error'}
                          showIcon
                          icon={testResult.success ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
                          title={testResult.message}
                          description={
                            <div>
                              <Text>
                                {t('ailab.label_model')}: <Text strong>{testResult.model}</Text>
                              </Text>
                              {testResult.success && (
                                <Text style={{ marginLeft: 16 }}>
                                  {t('ailab.label_latency')}: <Text strong>{testResult.latencyMs}ms</Text>
                                </Text>
                              )}
                              {testResult.responsePreview && (
                                <Paragraph type="secondary" className="gaf-mt-xs gaf-text-xs">
                                  {t('ailab.label_response_preview')}: {testResult.responsePreview}
                                </Paragraph>
                              )}
                            </div>
                          }
                          className="gaf-mt-lg"
                        />
                      )}
                    </Form>
                  </Spin>
                ),
              },
              {
                key: 'status',
                label: (
                  <span>
                    <SafetyCertificateOutlined /> {t('ailab.tab_connection_status')}
                  </span>
                ),
                children: (
                  <div>
                    <Alert
                      type={config?.is_active ? 'info' : 'warning'}
                      showIcon
                      title={config?.is_active ? t('ailab.msg_service_enabled') : t('ailab.msg_service_disabled')}
                      description={
                        config
                          ? t('ailab.label_currently_using') +
                            ': ' +
                            (PROVIDER_PRESETS[config.provider]?.labelKey
                              ? t(PROVIDER_PRESETS[config.provider].labelKey)
                              : config.provider) +
                            ' / ' +
                            config.default_model
                          : t('ailab.msg_no_provider_configured')
                      }
                      className="gaf-mb-lg"
                    />

                    {config && (
                      <Descriptions column={2} size="small" bordered title={t('ailab.card_current_config_details')}>
                        <Descriptions.Item label={t('ailab.col_provider')}>
                          <Tag color={PROVIDER_PRESETS[config.provider]?.color || 'default'}>
                            {PROVIDER_PRESETS[config.provider]?.icon}{' '}
                            {PROVIDER_PRESETS[config.provider]?.labelKey
                              ? t(PROVIDER_PRESETS[config.provider].labelKey)
                              : config.provider}
                          </Tag>
                        </Descriptions.Item>
                        <Descriptions.Item label="API Base">{config.api_base}</Descriptions.Item>
                        <Descriptions.Item label={t('ailab.label_default_model')}>
                          <Text code>{config.default_model}</Text>
                        </Descriptions.Item>
                        <Descriptions.Item label="Temperature">{config.temperature}</Descriptions.Item>
                        <Descriptions.Item label="Max Tokens">{config.max_tokens}</Descriptions.Item>
                        <Descriptions.Item label={t('ailab.col_status')}>
                          <Tag color={config.is_active ? 'green' : 'default'}>
                            {config.is_active ? t('ailab.switch_enabled') : t('ailab.switch_disabled')}
                          </Tag>
                        </Descriptions.Item>
                        {config.last_tested_at && (
                          <Descriptions.Item label={t('ailab.col_last_tested_at')} span={2}>
                            {new Date(config.last_tested_at).toLocaleString(getLocale())}
                          </Descriptions.Item>
                        )}
                      </Descriptions>
                    )}

                    <Divider />
                    <Text type="secondary" className="gaf-text-xs">
                      <InfoCircleOutlined /> {t('ailab.help_save_notice')}
                    </Text>
                  </div>
                ),
              },
              {
                key: 'help',
                label: (
                  <span>
                    <InfoCircleOutlined /> {t('ailab.tab_help')}
                  </span>
                ),
                children: (
                  <div>
                    <Card size="small" title={t('ailab.card_how_to_get_api_key')} className="gaf-mb-md">
                      <ol style={{ paddingLeft: 20, lineHeight: 2 }}>
                        <li>
                          <Text strong>OpenAI</Text>: <Text code>platform.openai.com/api-keys</Text> →{' '}
                          {t('ailab.help_openai_step')}
                        </li>
                        <li>
                          <Text strong>DeepSeek</Text>: <Text code>platform.deepseek.com/api_keys</Text> →{' '}
                          {t('ailab.help_deepseek_step')}
                        </li>
                        <li>
                          <Text strong>{t('ailab.provider_qwen')}</Text>: <Text code>dashscope.console.aliyun.com</Text>{' '}
                          → {t('ailab.help_qwen_step')}
                        </li>
                        <li>
                          <Text strong>Ollama</Text>: {t('ailab.help_ollama_step')}
                        </li>
                      </ol>
                    </Card>
                    <Card size="small" title={t('ailab.card_faq')}>
                      <Space orientation="vertical" size="small" className="gaf-w-full">
                        <div>
                          <Text strong>{t('ailab.faq_q_test_failed')}</Text>
                          <br />
                          <Text type="secondary">{t('ailab.faq_a_test_failed')}</Text>
                        </div>
                        <div>
                          <Text strong>{t('ailab.faq_q_multiple_providers')}</Text>
                          <br />
                          <Text type="secondary">{t('ailab.faq_a_multiple_providers')}</Text>
                        </div>
                        <div>
                          <Text strong>{t('ailab.faq_q_api_key_safety')}</Text>
                          <br />
                          <Text type="secondary">{t('ailab.faq_a_api_key_safety')}</Text>
                        </div>
                      </Space>
                    </Card>
                  </div>
                ),
              },
            ]}
          />
        </Card>
      </div>
    </PageWrapper>
  );
}

export default AiConfigPage;
