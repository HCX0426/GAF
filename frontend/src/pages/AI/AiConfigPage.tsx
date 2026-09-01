/**
 * AI Model Configuration Page (Phase 1 — multi-provider management)
 * Provider card list: add / edit / delete / set-active / test connection.
 * Backend: GET/POST/PUT/DELETE /settings/llm-config/ + POST {id}/set-active/.
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
  Modal,
  App,
  Empty,
  Tooltip,
} from 'antd';
import {
  SettingOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ThunderboltOutlined,
  KeyOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  PoweroffOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import {
  fetchLlmProviderConfig,
  createLlmProviderConfig,
  updateLlmProviderConfig,
  deleteLlmProviderConfig,
  setActiveLlmProvider,
  testLlmConnection,
  testLlmProvider,
  type LlmProviderConfig,
} from '@/api/ai';
import { useTranslation } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';

const { Text } = Typography;

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

export function AiConfigPage() {
  const t = useTranslation();
  const { message: msgApi, modal } = App.useApp();
  const [form] = Form.useForm();

  const [providers, setProviders] = useState<LlmProviderConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  // testingProviderId: which provider card's test button is loading
  const [testingProviderId, setTestingProviderId] = useState<number | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  // editing === undefined -> closed; null -> new; object -> edit existing
  const [editing, setEditing] = useState<LlmProviderConfig | null | undefined>(undefined);

  const active = providers.find((p) => p.is_active) ?? null;
  // Live model list from the form's available_models tags input — drives the
  // default_model Select options so the two fields stay in sync.
  const modelOptions = Form.useWatch('available_models', form);

  /** Load all LLM provider configs from backend */
  const loadProviders = async () => {
    setLoading(true);
    try {
      const data = await fetchLlmProviderConfig();
      setProviders(data ?? []);
    } catch {
      msgApi.warning(t('ailab.msg_load_config_failed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProviders();
  }, []);

  /** Open modal for a new provider (fresh preset defaults) */
  const handleOpenNew = () => {
    form.resetFields();
    form.setFieldsValue({
      provider: 'openai',
      api_base: PROVIDER_PRESETS.openai.apiBase,
      default_model: PROVIDER_PRESETS.openai.defaultModel,
      available_models: [PROVIDER_PRESETS.openai.defaultModel],
      temperature: 0.7,
      max_tokens: 4096,
      is_active: false,
    });
    setEditing(null);
    setModalOpen(true);
    setTestResult(null);
  };

  /** Open modal to edit an existing provider */
  const handleOpenEdit = (p: LlmProviderConfig) => {
    form.resetFields();
    form.setFieldsValue({
      provider: p.provider,
      api_key: '',
      api_base: p.api_base,
      default_model: p.default_model,
      available_models: Array.isArray(p.available_models) ? p.available_models : [p.default_model].filter(Boolean),
      temperature: p.temperature ?? 0.7,
      max_tokens: p.max_tokens ?? 4096,
      is_active: p.is_active ?? false,
    });
    setEditing(p);
    setModalOpen(true);
    setTestResult(null);
  };

  /** Handle provider selection change — auto-fill presets */
  const handleProviderChange = (providerKey: string) => {
    const preset = PROVIDER_PRESETS[providerKey];
    if (preset) {
      form.setFieldValue('api_base', preset.apiBase);
      form.setFieldValue('default_model', preset.defaultModel);
      form.setFieldValue('available_models', [preset.defaultModel]);
    }
  };

  /** Save (create or update) a provider */
  const handleSave = async () => {
    const values = await form.validateFields().catch(() => null);
    if (!values) return;

    setSaving(true);
    try {
      // Convert newline-separated model list (TextArea) into an array.
      const payload: Record<string, unknown> = { ...values, is_active: values.is_active ?? false };
      const modelsText: string = Array.isArray(values.available_models)
        ? values.available_models.join('\n')
        : values.available_models ?? '';
      payload.available_models = modelsText
        .split('\n')
        .map((m: string) => m.trim())
        .filter(Boolean);
      if (editing?.id) {
        // api_key is write-only + optional: empty on edit means "keep existing"
        if (!values.api_key) delete payload.api_key;
        await updateLlmProviderConfig(editing.id, payload);
      } else {
        await createLlmProviderConfig(payload);
      }
      msgApi.success(t('ailab.msg_config_saved'));
      setModalOpen(false);
      loadProviders();
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : t('ailab.msg_save_failed');
      msgApi.error(t('ailab.msg_save_failed_with_err', { message: errMsg }));
    } finally {
      setSaving(false);
    }
  };

  /** Set a provider as the single active one */
  const handleSetActive = async (p: LlmProviderConfig) => {
    if (!p.id) return;
    try {
      await setActiveLlmProvider(p.id);
      msgApi.success(t('ailab.msg_set_active_success'));
      loadProviders();
    } catch {
      msgApi.error(t('ailab.msg_set_active_failed'));
    }
  };

  /** Delete a provider (with confirmation) */
  const handleDelete = (p: LlmProviderConfig) => {
    if (!p.id) return;
    modal.confirm({
      title: t('ailab.msg_confirm_delete_provider'),
      okText: t('ailab.btn_delete'),
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteLlmProviderConfig(p.id!);
          msgApi.success(t('ailab.msg_delete_success'));
          loadProviders();
        } catch {
          msgApi.error(t('ailab.msg_delete_failed'));
        }
      },
    });
  };

  /** Test connection to the active provider's model */
  const handleTestConnection = async () => {
    if (!active) return;
    setTesting(true);
    setTestResult(null);
    try {
      const data = await testLlmConnection(
        {
          messages: [{ role: 'user', content: 'Hello, this is a connection test. Reply with "OK" only.' }],
          model: active.default_model,
          max_tokens: 10,
          temperature: 0,
        },
        { timeout: 15000 },
      );

      const startTime = Date.now();
      const result: TestResult = {
        success: true,
        latencyMs: Date.now() - startTime,
        model: active.default_model,
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
        model: active.default_model,
        message: t('ailab.msg_connection_failed_with_err', { message: errMsg }),
      });
      msgApi.error(t('ailab.msg_connection_test_failed'));
    } finally {
      setTesting(false);
    }
  };

  const providerName = (key: string) => {
    const preset = PROVIDER_PRESETS[key];
    return preset ? t(preset.labelKey) : key;
  };

  /** Test connectivity for a specific provider card (POST {id}/test/) */
  const handleTestProvider = async (p: LlmProviderConfig) => {
    if (!p.id) return;
    setTestingProviderId(p.id);
    try {
      const data = await testLlmProvider(p.id);
      if (data.success) {
        msgApi.success(t('ailab.msg_test_provider_success', { latencyMs: data.latency_ms ?? 0 }));
      } else {
        msgApi.error(
          t('ailab.msg_test_provider_failed', { message: data.message || t('ailab.msg_connection_failed') }),
        );
      }
      loadProviders();
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : t('ailab.msg_connection_failed');
      msgApi.error(t('ailab.msg_test_provider_failed', { message: errMsg }));
      loadProviders();
    } finally {
      setTestingProviderId(null);
    }
  };

  return (
    <PageWrapper>
      <div className="gaf-p-xl" style={{ maxWidth: 960, margin: '0 auto' }}>
        <Card
          size="small"
          title={
            <span>
              <SettingOutlined /> {t('ailab.card_model_config')}
            </span>
          }
          extra={
            <Button type="primary" icon={<PlusOutlined />} onClick={handleOpenNew}>
              {t('ailab.btn_add_provider')}
            </Button>
          }
        >
          {/* Active provider status banner */}
          {active ? (
            <Alert
              type="info"
              showIcon
              icon={<CheckCircleOutlined />}
              title={t('ailab.msg_service_enabled')}
              description={
                <Space>
                  <Text>
                    {t('ailab.label_currently_using')}:{' '}
                    <Tag color={PROVIDER_PRESETS[active.provider]?.color || 'default'}>
                      {PROVIDER_PRESETS[active.provider]?.icon} {providerName(active.provider)}
                    </Tag>
                    <Text code>{active.default_model}</Text>
                  </Text>
                  <Button size="small" icon={<PlayCircleOutlined />} loading={testing} onClick={handleTestConnection}>
                    {t('ailab.btn_test_connection')}
                  </Button>
                </Space>
              }
              className="gaf-mb-lg"
            />
          ) : (
            <Alert
              type="warning"
              showIcon
              title={t('ailab.msg_service_disabled')}
              description={t('ailab.msg_no_provider_configured')}
              className="gaf-mb-lg"
            />
          )}

          {/* Test result */}
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
                    <Text type="secondary" className="gaf-text-xs">
                      {' '}
                      | {t('ailab.label_response_preview')}: {testResult.responsePreview}
                    </Text>
                  )}
                </div>
              }
              className="gaf-mb-lg"
            />
          )}

          <Spin spinning={loading}>
            {providers.length === 0 && !loading ? (
              <Empty description={t('ailab.msg_no_provider_configured')} />
            ) : (
              <Space direction="vertical" size="middle" className="gaf-w-full">
                {providers.map((p) => {
                  const preset = PROVIDER_PRESETS[p.provider];
                  return (
                    <Card
                      key={p.id}
                      size="small"
                      styles={{ body: { paddingTop: 12 } }}
                      title={
                        <Space>
                          <span>{preset?.icon}</span>
                          <Text strong>{providerName(p.provider)}</Text>
                          {p.is_active ? (
                            <Tag color="green">{t('ailab.label_active')}</Tag>
                          ) : (
                            <Tag>{t('ailab.label_inactive')}</Tag>
                          )}
                        </Space>
                      }
                      extra={
                        <Space>
                          {!p.is_active && (
                            <Button size="small" type="primary" ghost icon={<PoweroffOutlined />} onClick={() => handleSetActive(p)}>
                              {t('ailab.btn_set_active')}
                            </Button>
                          )}
                          <Button
                            size="small"
                            icon={<PlayCircleOutlined />}
                            loading={testingProviderId === p.id}
                            onClick={() => handleTestProvider(p)}
                          >
                            {t('ailab.btn_test_provider')}
                          </Button>
                          <Button size="small" icon={<EditOutlined />} onClick={() => handleOpenEdit(p)}>
                            {t('ailab.btn_edit')}
                          </Button>
                          <Tooltip title={p.is_active ? t('ailab.msg_delete_failed') : undefined}>
                            <Button
                              size="small"
                              danger
                              icon={<DeleteOutlined />}
                              disabled={p.is_active}
                              onClick={() => handleDelete(p)}
                            />
                          </Tooltip>
                        </Space>
                      }
                    >
                      <Space direction="vertical" size={4} className="gaf-w-full">
                        <Space size="middle" wrap>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            <KeyOutlined /> {p.api_key_masked || t('ailab.placeholder_api_key')}
                          </Text>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            <ThunderboltOutlined /> <Text code>{p.default_model}</Text>
                          </Text>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {p.api_base}
                          </Text>
                        </Space>
                        {Array.isArray(p.available_models) && p.available_models.length > 0 && (
                          <Space size={[4, 4]} wrap>
                            {p.available_models.map((m) => (
                              <Tag key={m} color={m === p.default_model ? 'blue' : 'default'}>
                                {m}
                                {m === p.default_model ? ` (${t('ailab.label_active')})` : ''}
                              </Tag>
                            ))}
                          </Space>
                        )}
                      </Space>
                    </Card>
                  );
                })}
              </Space>
            )}
          </Spin>

          <Alert
            type="info"
            showIcon
            icon={<InfoCircleOutlined />}
            message={t('ailab.help_save_notice')}
            className="gaf-mt-lg"
          />
        </Card>
      </div>

      {/* Provider create/edit modal */}
      <Modal
        title={
          editing?.id
            ? `${t('ailab.btn_edit')} ${providerName(editing.provider)}`
            : t('ailab.btn_add_provider')
        }
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        confirmLoading={saving}
        okText={t('ailab.btn_save')}
        cancelText={t('ailab.btn_cancel')}
        width={560}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="provider"
            label={t('ailab.label_provider')}
            rules={[{ required: true, message: t('ailab.msg_provider_required') }]}
          >
            <Select
              placeholder={t('ailab.placeholder_select_provider')}
              onChange={handleProviderChange}
              options={Object.entries(PROVIDER_PRESETS).map(([key, pres]) => ({
                value: key,
                label: (
                  <span>
                    <span className="gaf-mr-sm">{pres.icon}</span>
                    {t(pres.labelKey)}
                  </span>
                ),
              }))}
            />
          </Form.Item>
          <Form.Item
            name="api_key"
            label="API Key"
            rules={editing?.id ? [] : [{ required: true, message: t('ailab.msg_api_key_required') }]}
            extra={editing?.id ? t('ailab.help_save_notice') : undefined}
          >
            <Input.Password placeholder={t('ailab.placeholder_api_key')} autoComplete="new-password" />
          </Form.Item>
          <Form.Item
            name="api_base"
            label="API Base URL"
            rules={[{ required: true, message: t('ailab.msg_base_url_required') }]}
          >
            <Input placeholder="https://api.openai.com/v1" />
          </Form.Item>
          <Form.Item
            name="default_model"
            label={t('ailab.label_default_model')}
            rules={[{ required: true, message: t('ailab.msg_model_name_required') }]}
          >
            <Select
              showSearch
              placeholder={t('ailab.placeholder_select_default_model')}
              options={(modelOptions || []).map((m: unknown) => ({
                value: String(m),
                label: String(m),
              }))}
            />
          </Form.Item>
          <Form.Item
            name="available_models"
            label={t('ailab.label_models_list')}
            extra={t('ailab.msg_models_placeholder')}
          >
            <Select
              mode="tags"
              placeholder={t('ailab.placeholder_models_tags')}
              open={false}
              suffixIcon={null}
              tokenSeparators={[',', '，', '\n']}
            />
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
            <Switch checkedChildren={t('ailab.switch_enabled')} unCheckedChildren={t('ailab.switch_disabled')} />
          </Form.Item>
        </Form>
      </Modal>
    </PageWrapper>
  );
}

export default AiConfigPage;
