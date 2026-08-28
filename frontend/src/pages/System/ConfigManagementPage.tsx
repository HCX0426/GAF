/**
 * Configuration management page
 * Uses ConfigGenerator backend API for dynamic form schema generation,
 * validation, import/export of task configuration.
 * Also provides Config Migration GUI (Alas-style chained migration).
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Select,
  Form,
  Input,
  InputNumber,
  Switch,
  Button,
  Space,
  Tabs,
  Typography,
  Tag,
  Alert,
  Row,
  Col,
  Descriptions,
  Divider,
  Collapse,
  App,
  Table,
} from 'antd';
import type { FormInstance } from 'antd/es/form';
import {
  SettingOutlined,
  DownloadOutlined,
  UploadOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  CopyOutlined,
  FileTextOutlined,
  SwapOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import {
  fetchConfigSchema,
  fetchConfigTaskTypes,
  validateConfigValues,
  exportConfig,
  importConfig,
  fetchMigrationInfo,
  detectConfigVersion,
  migrateConfig,
  type ConfigField,
  type ConfigSchemaResponse,
  type MigrationInfo,
  type DetectVersionResponse,
  type MigrateConfigResponse,
  type MigrationLogEntry,
} from '@/api/settings';
import { classifyError } from '@/utils/errorHandler';
import PageWrapper from '@/components/Common/PageWrapper';
import { useTranslation } from '@/i18n';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

/** Task type display metadata — i18n keys for label/desc */
const TASK_TYPE_META: Record<string, { labelKey: string; descKey: string; color: string }> = {
  pipeline: { labelKey: 'config.type_pipeline', descKey: 'config.type_pipeline_desc', color: 'blue' },
  scheduler: { labelKey: 'config.type_scheduler', descKey: 'config.type_scheduler_desc', color: 'green' },
  device_config: { labelKey: 'config.type_device_config', descKey: 'config.type_device_config_desc', color: 'orange' },
  ocr_task: { labelKey: 'config.type_ocr_task', descKey: 'config.type_ocr_task_desc', color: 'purple' },
  general: { labelKey: 'config.type_general', descKey: 'config.type_general_desc', color: 'default' },
};

/** Render form field based on field type definition */
function renderField(
  field: ConfigField,
  _form: FormInstance,
  t: (key: string, params?: Record<string, string | number | undefined>) => string,
): React.ReactNode {
  const formItemProps = {
    name: field.key,
    label: (
      <div className="gaf-toolbar-group">
        <span>{field.label}</span>
        {field.required && <Tag color="red">{t('config.required_tag')}</Tag>}
      </div>
    ),
    rules: [
      ...(field.required ? [{ required: true, message: t('config.field_required', { label: field.label }) }] : []),
    ],
    tooltip: field.help_text || undefined,
    initialValue: field.default_value,
  };

  switch (field.type) {
    case 'string':
      return (
        <Form.Item {...formItemProps}>
          <Input placeholder={field.placeholder} disabled={field.disabled} />
        </Form.Item>
      );
    case 'text':
      return (
        <Form.Item {...formItemProps}>
          <TextArea rows={3} placeholder={field.placeholder} disabled={field.disabled} />
        </Form.Item>
      );
    case 'integer':
      return (
        <Form.Item {...formItemProps}>
          <InputNumber className="gaf-w-full" disabled={field.disabled} />
        </Form.Item>
      );
    case 'float':
      return (
        <Form.Item {...formItemProps}>
          <InputNumber className="gaf-w-full" step={0.1} disabled={field.disabled} />
        </Form.Item>
      );
    case 'boolean':
      return (
        <Form.Item key={field.key} name={field.key} valuePropName="checked" initialValue={field.default_value}>
          <Switch disabled={field.disabled} />
        </Form.Item>
      );
    case 'select':
      return (
        <Form.Item {...formItemProps}>
          <Select
            placeholder={field.placeholder}
            options={field.options.map((o) => ({ label: String(o.label), value: o.value }))}
            disabled={field.disabled}
            allowClear
          />
        </Form.Item>
      );
    case 'multiselect':
      return (
        <Form.Item {...formItemProps}>
          <Select
            mode="multiple"
            placeholder={field.placeholder}
            options={field.options.map((o) => ({ label: String(o.label), value: o.value }))}
            disabled={field.disabled}
          />
        </Form.Item>
      );
    default:
      return (
        <Form.Item {...formItemProps}>
          <Input placeholder={field.placeholder} disabled={field.disabled} />
        </Form.Item>
      );
  }
}

/** Group fields by their group property */
function groupFields(fields: ConfigField[]): Record<string, ConfigField[]> {
  const groups: Record<string, ConfigField[]> = {};
  fields
    .filter((f) => f.visible)
    .sort((a, b) => a.order - b.order)
    .forEach((f) => {
      const g = f.group || 'General';
      if (!groups[g]) groups[g] = [];
      groups[g].push(f);
    });
  return groups;
}

/** Migration panel — config version detection and incremental migration */
function MigrationPanel() {
  const { message: msgApi } = App.useApp();
  const t = useTranslation();
  const [migrationInfo, setMigrationInfo] = useState<MigrationInfo | null>(null);
  const [configJson, setConfigJson] = useState('');
  const [detectResult, setDetectResult] = useState<DetectVersionResponse | null>(null);
  const [migrateResult, setMigrateResult] = useState<MigrateConfigResponse | null>(null);
  const [detecting, setDetecting] = useState(false);
  const [migrating, setMigrating] = useState(false);
  const [targetVersion, setTargetVersion] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const info = await fetchMigrationInfo();
        if (!cancelled && info.success) {
          setMigrationInfo(info);
          setTargetVersion(info.latest_version);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          const classified = classifyError(err);
          msgApi.error(t('config.migration_detect_failed', { message: classified.message }));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDetect = async () => {
    if (!configJson.trim()) {
      msgApi.warning(t('config.migration_config_required'));
      return;
    }
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(configJson);
    } catch (e: unknown) {
      msgApi.error(t('config.migration_detect_failed', { message: (e as Error).message }));
      return;
    }
    setDetecting(true);
    setDetectResult(null);
    try {
      const result = await detectConfigVersion(parsed);
      setDetectResult(result);
      if (result.success) {
        msgApi.success(`${t('config.migration_detected_version')}: v${result.detected_version} (${result.method})`);
      }
    } catch (err: unknown) {
      const classified = classifyError(err);
      msgApi.error(t('config.migration_detect_failed', { message: classified.message }));
    } finally {
      setDetecting(false);
    }
  };

  const handleMigrate = async () => {
    if (!configJson.trim()) {
      msgApi.warning(t('config.migration_config_required'));
      return;
    }
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(configJson);
    } catch (e: unknown) {
      msgApi.error(t('config.migration_migrate_failed', { message: (e as Error).message }));
      return;
    }
    setMigrating(true);
    setMigrateResult(null);
    try {
      const result = await migrateConfig(parsed, {
        to_ver: targetVersion ?? undefined,
      });
      setMigrateResult(result);
      if (result.success) {
        if (result.from_version === result.to_version) {
          msgApi.info(t('config.migration_no_change'));
        } else {
          msgApi.success(t('config.migration_success', { from: result.from_version, to: result.to_version }));
        }
      } else {
        msgApi.error(t('config.migration_migrate_failed', { message: result.message ?? '' }));
      }
    } catch (err: unknown) {
      const classified = classifyError(err);
      msgApi.error(t('config.migration_migrate_failed', { message: classified.message }));
    } finally {
      setMigrating(false);
    }
  };

  const methodLabel = (method: string): string => {
    if (method === 'explicit') return t('config.migration_method_explicit');
    if (method === 'heuristic') return t('config.migration_method_heuristic');
    return t('config.migration_method_default');
  };

  const logColumns = [
    {
      title: t('config.migration_log_timestamp'),
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 200,
      render: (ts: string) => {
        try {
          return new Date(ts).toLocaleString();
        } catch {
          return ts;
        }
      },
    },
    {
      title: t('config.migration_log_from'),
      dataIndex: 'from_version',
      key: 'from_version',
      width: 100,
      render: (v: number) => <Tag>v{v}</Tag>,
    },
    {
      title: t('config.migration_log_to'),
      dataIndex: 'to_version',
      key: 'to_version',
      width: 100,
      render: (v: number) => <Tag color="blue">v{v}</Tag>,
    },
    {
      title: t('config.migration_log_changed'),
      dataIndex: 'changed_keys',
      key: 'changed_keys',
      render: (keys: string[]) => (
        <Space wrap>
          {keys.map((k) => (
            <Tag key={k}>{k}</Tag>
          ))}
        </Space>
      ),
    },
  ];

  return (
    <Row gutter={24}>
      {/* Left: Input + Actions */}
      <Col xs={24} lg={12}>
        <Card
          title={
            <>
              <SwapOutlined /> {t('config.migration_input_title')}
            </>
          }
          size="small"
        >
          <Paragraph type="secondary" className="gaf-mb-md">
            {t('config.migration_desc')}
          </Paragraph>

          <TextArea
            value={configJson}
            onChange={(e) => setConfigJson(e.target.value)}
            placeholder={t('config.migration_input_placeholder')}
            rows={12}
            className="gaf-mb-md gaf-text-xs gaf-font-mono"
          />

          <div className="gaf-toolbar">
            <Button icon={<SearchOutlined />} onClick={handleDetect} loading={detecting}>
              {t('config.migration_btn_detect')}
            </Button>
            <Button type="primary" icon={<SwapOutlined />} onClick={handleMigrate} loading={migrating}>
              {t('config.migration_btn_migrate')}
            </Button>
            <Select
              value={targetVersion ?? undefined}
              onChange={(v) => setTargetVersion(v)}
              style={{ width: 160 }}
              placeholder={t('config.migration_target_version')}
              options={(migrationInfo?.available_versions ?? []).map((v) => ({
                label: `v${v}${v === migrationInfo?.latest_version ? ` (${t('config.migration_latest_version')})` : ''}`,
                value: v,
              }))}
            />
          </div>

          {detectResult && (
            <Card size="small" type="inner" title={t('config.migration_detect_result')} className="gaf-mt-lg">
              <Descriptions column={1} size="small">
                <Descriptions.Item label={t('config.migration_detected_version')}>
                  <Tag color="blue">v{detectResult.detected_version}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label={t('config.migration_detect_method')}>
                  {methodLabel(detectResult.method)}
                </Descriptions.Item>
                <Descriptions.Item label={t('config.migration_needs_migration')}>
                  {detectResult.needs_migration ? (
                    <Tag color="orange">{t('config.migration_yes')}</Tag>
                  ) : (
                    <Tag color="green">{t('config.migration_no')}</Tag>
                  )}
                </Descriptions.Item>
                <Descriptions.Item label={t('config.migration_latest_version')}>
                  <Tag>v{detectResult.latest_version}</Tag>
                </Descriptions.Item>
              </Descriptions>
            </Card>
          )}
        </Card>
      </Col>

      {/* Right: Migration Info + Result + Log */}
      <Col xs={24} lg={12}>
        <Card
          title={
            <>
              <FileTextOutlined /> {t('config.migration_info_title')}
            </>
          }
          size="small"
          className="gaf-mb-lg"
        >
          {migrationInfo ? (
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label={t('config.migration_latest_version')}>
                <Tag color="blue">v{migrationInfo.latest_version}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('config.migration_available_versions')}>
                <div className="gaf-toolbar-group">
                  {migrationInfo.available_versions.map((v) => (
                    <Tag key={v}>v{v}</Tag>
                  ))}
                </div>
              </Descriptions.Item>
              <Descriptions.Item label={t('config.migration_version_descriptions')}>
                <Collapse
                  ghost
                  size="small"
                  items={Object.entries(migrationInfo.version_descriptions).map(([ver, desc]) => ({
                    key: ver,
                    label: <Tag>v{ver}</Tag>,
                    children: <Text type="secondary">{desc}</Text>,
                  }))}
                />
              </Descriptions.Item>
            </Descriptions>
          ) : (
            <Text type="secondary">Loading...</Text>
          )}
        </Card>

        {migrateResult && (
          <Card
            title={
              <>
                <CheckCircleOutlined /> {t('config.migration_result_title')}
              </>
            }
            size="small"
            className="gaf-mb-lg"
          >
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label={t('config.migration_result_from')}>
                <Tag>v{migrateResult.from_version}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('config.migration_result_to')}>
                <Tag color="blue">v{migrateResult.to_version}</Tag>
              </Descriptions.Item>
            </Descriptions>
            <Divider style={{ margin: '12px 0' }} />
            <Text strong>{t('config.migration_result_config')}:</Text>
            <Input.TextArea
              value={JSON.stringify(migrateResult.migrated_config, null, 2)}
              readOnly
              rows={10}
              className="gaf-mt-sm gaf-text-xxs gaf-font-mono"
            />
          </Card>
        )}

        {migrateResult && migrateResult.migration_log.length > 0 && (
          <Card title={t('config.migration_log_title')} size="small">
            <Table<MigrationLogEntry>
              dataSource={migrateResult.migration_log}
              columns={logColumns}
              rowKey={(r, i) => `${r.timestamp}-${i}`}
              size="small"
              pagination={false}
            />
          </Card>
        )}
      </Col>
    </Row>
  );
}

export function ConfigManagementPage() {
  const { message: msgApi } = App.useApp();
  const t = useTranslation();
  const [form] = Form.useForm();
  const [pageTab, setPageTab] = useState<string>('editor');
  const [activeTab, setActiveTab] = useState<string>('pipeline');
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [currentSchema, setCurrentSchema] = useState<ConfigSchemaResponse | null>(null);
  const [taskTypes, setTaskTypes] = useState<Record<string, { field_count?: number } | null>>({});
  const [validateResult, setValidateResult] = useState<{ success: boolean; errors: string[] } | null>(null);
  const [exportedJson, setExportedJson] = useState('');
  const [importJson, setImportJson] = useState('');
  const [importing, setImporting] = useState(false);

  useEffect(() => {
    loadTaskTypes();
    loadSchema('pipeline');
  }, []);

  /** Load available task types list */
  const loadTaskTypes = useCallback(async () => {
    try {
      const result = await fetchConfigTaskTypes();
      if (result.success) {
        setTaskTypes(result.task_types as unknown as Record<string, { field_count?: number } | null>);
      }
    } catch {
      // Task types load failed — form will show empty options
    }
  }, []);

  /** Load form schema for selected task type */
  const loadSchema = useCallback(
    async (taskType: string) => {
      setSchemaLoading(true);
      setValidateResult(null);
      try {
        const result = await fetchConfigSchema(taskType);
        if (result.success) {
          setCurrentSchema(result);
          const defaults: Record<string, unknown> = {};
          result.fields.forEach((f) => {
            if (f.default_value !== undefined && f.default_value !== null) {
              defaults[f.key] = f.default_value;
            }
          });
          form.setFieldsValue(defaults);
        }
      } catch (err: unknown) {
        const classified = classifyError(err);
        msgApi.error(t('config.load_failed', { message: classified.message }));
      } finally {
        setSchemaLoading(false);
      }
    },
    [form, msgApi, t],
  );

  /** Handle tab change — load new schema */
  const handleTabChange = (key: string) => {
    setActiveTab(key);
    loadSchema(key);
  };

  /** Validate current form values */
  const handleValidate = async () => {
    const values = form.getFieldsValue();
    setValidateResult(null);
    try {
      const result = await validateConfigValues(values, activeTab);
      setValidateResult(result);
      if (result.success) {
        msgApi.success(t('config.validate_passed'));
      } else {
        msgApi.warning(t('config.validate_failed_count', { count: result.errors.length }));
      }
    } catch (err: unknown) {
      const classified = classifyError(err);
      msgApi.error(t('config.validate_exception', { message: classified.message }));
    }
  };

  /** Export current values as JSON */
  const handleExport = async () => {
    const values = form.getFieldsValue();
    try {
      const result = await exportConfig(values, activeTab);
      if (result.success) {
        const json = JSON.stringify(result.config, null, 2);
        setExportedJson(json);
        msgApi.success(t('config.export_success'));
      }
    } catch (err: unknown) {
      const classified = classifyError(err);
      msgApi.error(t('config.export_failed', { message: classified.message }));
    }
  };

  /** Import config from JSON text */
  const handleImport = async () => {
    if (!importJson.trim()) {
      msgApi.warning(t('config.import_required'));
      return;
    }
    setImporting(true);
    try {
      const parsed = JSON.parse(importJson);
      const result = await importConfig(parsed);
      if (result.success) {
        form.setFieldsValue(result.values);
        setActiveTab(result.task_type);
        await loadSchema(result.task_type);
        msgApi.success(t('config.import_success', { type: result.task_type }));
        setImportJson('');
      }
    } catch (err: unknown) {
      const classified = classifyError(err);
      msgApi.error(t('config.import_failed', { message: classified.message }));
    } finally {
      setImporting(false);
    }
  };

  /** Copy exported JSON to clipboard */
  const handleCopyExport = () => {
    navigator.clipboard.writeText(exportedJson);
    msgApi.success(t('config.copy_success'));
  };

  const meta = TASK_TYPE_META[activeTab] || {
    labelKey: 'config.type_general',
    descKey: 'config.type_general_desc',
    color: 'default',
  };
  const metaLabel = t(meta.labelKey);
  const metaDesc = t(meta.descKey);
  const groupedFields = currentSchema ? groupFields(currentSchema.fields) : {};

  return (
    <PageWrapper title={t('config.page_title')} titleIcon={<SettingOutlined />}>
      <Paragraph type="secondary">{t('config.page_desc')}</Paragraph>

      <Tabs
        activeKey={pageTab}
        onChange={setPageTab}
        items={[
          {
            key: 'editor',
            label: (
              <div className="gaf-toolbar-group">
                <SettingOutlined />
                <span>{t('config.page_title')}</span>
              </div>
            ),
            children: (
              <Row gutter={24}>
                {/* Left: Dynamic form */}
                <Col xs={24} lg={16}>
                  <Card
                    title={
                      <div className="gaf-toolbar-group">
                        <Tag color={meta.color}>{metaLabel}</Tag>
                        <Text type="secondary">{metaDesc}</Text>
                      </div>
                    }
                    loading={schemaLoading}
                    extra={
                      <div className="gaf-toolbar">
                        <Button icon={<CheckCircleOutlined />} onClick={handleValidate}>
                          {t('config.btn_validate')}
                        </Button>
                        <Button icon={<DownloadOutlined />} onClick={handleExport}>
                          {t('config.btn_export')}
                        </Button>
                      </div>
                    }
                  >
                    <Tabs
                      activeKey={activeTab}
                      onChange={handleTabChange}
                      items={Object.entries(TASK_TYPE_META).map(([key, m]) => ({
                        key,
                        label: (
                          <div className="gaf-toolbar-group">
                            <Tag color={m.color}>{t(m.labelKey)}</Tag>
                            {taskTypes[key] != null && (
                              <Text type="secondary" className="gaf-text-xxs">
                                {taskTypes[key]?.field_count
                                  ? t('config.field_count', { count: taskTypes[key].field_count })
                                  : ''}
                              </Text>
                            )}
                          </div>
                        ),
                      }))}
                    />

                    <Form form={form} layout="vertical" size="middle" className="gaf-mt-lg" preserve={false}>
                      {currentSchema && (
                        <Collapse
                          defaultActiveKey={Object.keys(groupedFields)}
                          ghost
                          items={Object.entries(groupedFields).map(([groupName, fields]) => ({
                            key: groupName,
                            label: <Text strong>{groupName}</Text>,
                            children: (
                              <Row gutter={[16, 0]}>
                                {fields.map((field) => (
                                  <Col xs={24} md={12} key={field.key}>
                                    {renderField(field, form, t)}
                                  </Col>
                                ))}
                              </Row>
                            ),
                          }))}
                        />
                      )}
                    </Form>

                    {validateResult && (
                      <Alert
                        className="gaf-mt-lg"
                        type={validateResult.success ? 'success' : 'warning'}
                        icon={validateResult.success ? <CheckCircleOutlined /> : <ExclamationCircleOutlined />}
                        title={
                          validateResult.success ? t('config.alert_validate_passed') : t('config.alert_validate_failed')
                        }
                        description={
                          !validateResult.success ? (
                            <ul className="gaf-m-0" style={{ paddingLeft: 20 }}>
                              {validateResult.errors.map((e, i) => (
                                <li key={`err-${i}-${e.slice(0, 16)}`}>{e}</li>
                              ))}
                            </ul>
                          ) : undefined
                        }
                      />
                    )}
                  </Card>
                </Col>

                {/* Right: Import/Export panel */}
                <Col xs={24} lg={8}>
                  <Card
                    title={
                      <>
                        <UploadOutlined /> {t('config.divider_export')} / {t('config.divider_import')}
                      </>
                    }
                    size="small"
                  >
                    <Divider titlePlacement="left">{t('config.divider_export')}</Divider>
                    <Button
                      type="primary"
                      icon={<DownloadOutlined />}
                      onClick={handleExport}
                      block
                      className="gaf-mb-sm"
                    >
                      {t('config.btn_export_json')}
                    </Button>
                    {exportedJson && (
                      <>
                        <Input.TextArea
                          value={exportedJson}
                          readOnly
                          rows={8}
                          className="gaf-mb-sm gaf-text-xxs gaf-font-mono"
                        />
                        <Button icon={<CopyOutlined />} onClick={handleCopyExport} block size="small">
                          {t('config.btn_copy')}
                        </Button>
                      </>
                    )}

                    <Divider titlePlacement="left">{t('config.divider_import')}</Divider>
                    <Input.TextArea
                      value={importJson}
                      onChange={(e) => setImportJson(e.target.value)}
                      placeholder={t('config.placeholder_import')}
                      rows={6}
                      className="gaf-mb-sm gaf-text-xxs gaf-font-mono"
                    />
                    <Button icon={<UploadOutlined />} onClick={handleImport} loading={importing} block>
                      {t('config.btn_import')}
                    </Button>

                    <Divider titlePlacement="left">{t('config.divider_info')}</Divider>
                    <Descriptions column={1} size="small" bordered>
                      <Descriptions.Item label={t('config.lbl_current_type')}>{metaLabel}</Descriptions.Item>
                      <Descriptions.Item label={t('config.lbl_field_count')}>
                        {currentSchema?.fields.length ?? 0}
                      </Descriptions.Item>
                      <Descriptions.Item label={t('config.lbl_schema_version')}>
                        {currentSchema?.schema.version ?? '-'}
                      </Descriptions.Item>
                    </Descriptions>
                  </Card>
                </Col>
              </Row>
            ),
          },
          {
            key: 'migration',
            label: (
              <div className="gaf-toolbar-group">
                <SwapOutlined />
                <span>{t('config.migration_tab')}</span>
              </div>
            ),
            children: <MigrationPanel />,
          },
        ]}
      />
    </PageWrapper>
  );
}

export default ConfigManagementPage;
