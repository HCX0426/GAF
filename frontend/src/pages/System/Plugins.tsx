/**
 * plugin market / plugin management page
 * supports upload.gafplugin plugin pack, install, enable / disable, unmount, hot reload, sandbox execute
 */
import { useEffect, useState, useCallback } from 'react';
import {
  Card,
  Table,
  Button,
  Switch,
  Tag,
  Space,
  Popconfirm,
  message,
  Upload,
  Drawer,
  Descriptions,
  Empty,
  Spin,
  Typography,
  theme as antTheme,
} from 'antd';
import {
  UploadOutlined,
  ReloadOutlined,
  AppstoreAddOutlined,
  DeleteOutlined,
  DownloadOutlined,
  PlayCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { UploadFile } from 'antd';
import {
  fetchPlugins,
  installPlugin,
  togglePlugin,
  uninstallPlugin,
  reloadPlugin,
  sandboxExecPlugin,
  uploadPlugin,
} from '@/api/plugins';
import type { PluginItem } from '@/api/plugins';
import { classifyError } from '@/utils/errorHandler';
import { useTranslation } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';

const { Text } = Typography;

/** plugin management page component */
export function PluginsPage() {
  const t = useTranslation();
  const { token: designToken } = antTheme.useToken();
  const [plugins, setPlugins] = useState<PluginItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [selectedPlugin, setSelectedPlugin] = useState<PluginItem | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState<Record<number, boolean>>({});

  /** load plugin list */
  const loadPlugins = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      const data = await fetchPlugins(signal);
      if (!signal?.aborted) {
        setPlugins(Array.isArray(data) ? data : []);
      }
    } catch (err: unknown) {
      const classified = classifyError(err);
      if (
        classified.originalError instanceof Error &&
        classified.originalError.name !== 'AbortError' &&
        !(err instanceof Error && err.name === 'CanceledError')
      ) {
        setPlugins([]);
      }
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    loadPlugins(controller.signal);
    return () => {
      // Do not abort on unmount to avoid ERR_ABORTED in DevTools
    };
  }, [loadPlugins]);

  /** settings load status */
  const setLoadingState = (id: number, value: boolean) => {
    setActionLoading((prev) => ({ ...prev, [id]: value }));
  };

  /** install plugin */
  const handleInstall = async (id: number) => {
    setLoadingState(id, true);
    try {
      const updated = await installPlugin(id);
      setPlugins((prev) => prev.map((p) => (p.id === id ? updated : p)));
      if (selectedPlugin?.id === id) setSelectedPlugin(updated);
      message.success(t('plugins.msg_install_success'));
    } catch (err: unknown) {
      const errDetail = (err as { response?: { data?: { error?: string } } })?.response?.data?.error;
      if (errDetail) {
        message.error(errDetail || t('plugins.msg_install_failed'));
      } else {
        message.error(t('plugins.msg_install_request_failed'));
      }
    } finally {
      setLoadingState(id, false);
    }
  };

  /** enable / disable plugin */
  const handleToggle = async (id: number) => {
    setLoadingState(id, true);
    try {
      const updated = await togglePlugin(id);
      setPlugins((prev) => prev.map((p) => (p.id === id ? updated : p)));
      if (selectedPlugin?.id === id) setSelectedPlugin(updated);
      message.success(updated.is_active ? t('plugins.msg_toggle_active') : t('plugins.msg_toggle_inactive'));
    } catch (err: unknown) {
      const errDetail = (err as { response?: { data?: { error?: string } } })?.response?.data?.error;
      if (errDetail) {
        message.error(errDetail || t('plugins.msg_toggle_failed'));
      } else {
        message.error(t('plugins.msg_toggle_request_failed'));
      }
    } finally {
      setLoadingState(id, false);
    }
  };

  /** uninstall plugin */
  const handleUninstall = async (id: number) => {
    setLoadingState(id, true);
    try {
      await uninstallPlugin(id);
      setPlugins((prev) => prev.filter((p) => p.id !== id));
      if (selectedPlugin?.id === id) {
        setSelectedPlugin(null);
        setDrawerOpen(false);
      }
      message.success(t('plugins.msg_uninstall_success'));
    } catch (err: unknown) {
      const errDetail = (err as { response?: { data?: { error?: string } } })?.response?.data?.error;
      if (errDetail) {
        message.error(errDetail || t('plugins.msg_uninstall_failed'));
      } else {
        message.error(t('plugins.msg_uninstall_request_failed'));
      }
    } finally {
      setLoadingState(id, false);
    }
  };

  /** hot reload plugin */
  const handleReload = async (id: number) => {
    setLoadingState(id, true);
    try {
      const updated = await reloadPlugin(id);
      setPlugins((prev) => prev.map((p) => (p.id === id ? updated : p)));
      if (selectedPlugin?.id === id) setSelectedPlugin(updated);
      message.success(t('plugins.msg_reload_success'));
    } catch (err: unknown) {
      const errDetail = (err as { response?: { data?: { error?: string } } })?.response?.data?.error;
      if (errDetail) {
        message.error(errDetail || t('plugins.msg_reload_failed'));
      } else {
        message.error(t('plugins.msg_reload_request_failed'));
      }
    } finally {
      setLoadingState(id, false);
    }
  };

  /** sandbox execute plugin */
  const handleSandboxExec = async (id: number) => {
    setLoadingState(id, true);
    try {
      const result = await sandboxExecPlugin(id);
      message.success(result.message || t('plugins.msg_sandbox_success'));
      loadPlugins();
    } catch (err: unknown) {
      const errDetail = (err as { response?: { data?: { error?: string } } })?.response?.data?.error;
      if (errDetail) {
        message.warning(errDetail || t('plugins.msg_sandbox_failed'));
      } else {
        message.error(t('plugins.msg_sandbox_request_failed'));
      }
    } finally {
      setLoadingState(id, false);
    }
  };

  /** upload plugin pack */
  const handleUpload = async (file: UploadFile) => {
    if (!file.originFileObj) return false;

    setUploading(true);
    try {
      const data = await uploadPlugin(file.originFileObj);
      setPlugins((prev) => {
        const exists = prev.find((p) => p.id === data.id);
        if (exists) {
          return prev.map((p) => (p.id === data.id ? data : p));
        }
        return [...prev, data];
      });
      message.success(t('plugins.msg_upload_success', { name: data.name, version: data.version }));
    } catch (err: unknown) {
      const errDetail = (err as { response?: { data?: { error?: string } } })?.response?.data?.error;
      if (errDetail) {
        message.error(errDetail || t('plugins.msg_upload_failed'));
      } else {
        message.error(t('plugins.msg_upload_request_failed'));
      }
    } finally {
      setUploading(false);
    }
    return false;
  };

  /** open details drawer */
  const showDetail = (plugin: PluginItem) => {
    setSelectedPlugin(plugin);
    setDrawerOpen(true);
  };

  /** sandbox status Tag color */
  const sandboxStatusColor: Record<string, string> = {
    idle: 'default',
    running: 'green',
    stopped: 'orange',
    error: 'red',
  };

  const columns: ColumnsType<PluginItem> = [
    {
      title: t('plugins.col_name'),
      dataIndex: 'name',
      key: 'name',
      width: 160,
      ellipsis: true,
      render: (text: string, record: PluginItem) => (
        <Button type="link" onClick={() => showDetail(record)} className="gaf-p-0">
          {text}
        </Button>
      ),
    },
    {
      title: t('plugins.col_version'),
      dataIndex: 'version',
      key: 'version',
      width: 100,
    },
    {
      title: t('plugins.col_author'),
      dataIndex: 'author',
      key: 'author',
      width: 120,
      render: (text: string) => text || '-',
    },
    {
      title: t('plugins.col_status'),
      key: 'status',
      width: 180,
      render: (_: unknown, record: PluginItem) => (
        <Space>
          {record.is_installed ? (
            <Tag color={record.is_active ? 'green' : 'default'}>
              {record.is_active ? t('plugins.status_active') : t('plugins.status_inactive')}
            </Tag>
          ) : (
            <Tag color="blue">{t('plugins.status_not_installed')}</Tag>
          )}
          {record.sandbox_status && record.sandbox_status !== 'idle' && (
            <Tag color={sandboxStatusColor[record.sandbox_status] || 'default'}>
              {t('plugins.sandbox_label', { status: record.sandbox_status })}
            </Tag>
          )}
        </Space>
      ),
    },
    {
      title: t('plugins.col_toggle'),
      key: 'toggle',
      width: 100,
      render: (_: unknown, record: PluginItem) => (
        <Switch
          checked={record.is_active}
          disabled={!record.is_installed || actionLoading[record.id]}
          loading={actionLoading[record.id]}
          onChange={() => handleToggle(record.id)}
        />
      ),
    },
    {
      title: t('plugins.col_actions'),
      key: 'actions',
      width: 340,
      render: (_: unknown, record: PluginItem) => (
        <Space size="small" wrap>
          {!record.is_installed ? (
            <Button
              type="link"
              size="small"
              icon={<DownloadOutlined />}
              loading={actionLoading[record.id]}
              onClick={() => handleInstall(record.id)}
            >
              {t('plugins.btn_install')}
            </Button>
          ) : (
            <>
              <Button
                type="link"
                size="small"
                icon={<SyncOutlined />}
                loading={actionLoading[record.id]}
                onClick={() => handleReload(record.id)}
              >
                {t('plugins.btn_reload')}
              </Button>
              <Button
                type="link"
                size="small"
                icon={<PlayCircleOutlined />}
                loading={actionLoading[record.id]}
                onClick={() => handleSandboxExec(record.id)}
              >
                {t('plugins.btn_sandbox_exec')}
              </Button>
            </>
          )}
          <Popconfirm
            title={t('plugins.confirm_uninstall_title')}
            description={t('plugins.confirm_uninstall_desc')}
            onConfirm={() => handleUninstall(record.id)}
            okText={t('plugins.confirm_ok')}
            cancelText={t('plugins.confirm_cancel')}
          >
            <Button type="link" danger size="small" icon={<DeleteOutlined />} loading={actionLoading[record.id]}>
              {t('plugins.btn_uninstall')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <PageWrapper
      title={t('plugins.page_title')}
      titleIcon={<AppstoreAddOutlined />}
      extra={
        <Space>
          <Upload accept=".gafplugin" maxCount={1} beforeUpload={handleUpload} showUploadList={false}>
            <Button type="primary" icon={<UploadOutlined />} loading={uploading}>
              {t('plugins.btn_upload')}
            </Button>
          </Upload>
          <Button icon={<ReloadOutlined />} onClick={() => loadPlugins()}>
            {t('plugins.btn_refresh')}
          </Button>
        </Space>
      }
    >
      <Card>
        <Spin spinning={loading}>
          {plugins.length === 0 && !loading ? (
            <Empty description={t('plugins.empty')} style={{ padding: 48 }} />
          ) : (
            <Table columns={columns} dataSource={plugins || []} rowKey="id" pagination={false} size="middle" />
          )}
        </Spin>
      </Card>

      <Drawer
        title={t('plugins.drawer_title')}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        size="large"
        extra={
          selectedPlugin?.is_installed && (
            <Space>
              <Button
                icon={<SyncOutlined />}
                loading={selectedPlugin ? actionLoading[selectedPlugin.id] : false}
                onClick={() => selectedPlugin && handleReload(selectedPlugin.id)}
              >
                {t('plugins.btn_reload')}
              </Button>
              <Button
                icon={<PlayCircleOutlined />}
                loading={selectedPlugin ? actionLoading[selectedPlugin.id] : false}
                onClick={() => selectedPlugin && handleSandboxExec(selectedPlugin.id)}
              >
                {t('plugins.btn_sandbox_exec')}
              </Button>
            </Space>
          )
        }
      >
        {selectedPlugin && (
          <>
            <Descriptions column={2} bordered size="small" className="gaf-mb-lg">
              <Descriptions.Item label={t('plugins.detail_name')}>{selectedPlugin.name}</Descriptions.Item>
              <Descriptions.Item label={t('plugins.detail_version')}>{selectedPlugin.version}</Descriptions.Item>
              <Descriptions.Item label={t('plugins.detail_author')}>{selectedPlugin.author || '-'}</Descriptions.Item>
              <Descriptions.Item label={t('plugins.detail_status')}>
                <Space>
                  <Tag color={selectedPlugin.is_installed ? (selectedPlugin.is_active ? 'green' : 'default') : 'blue'}>
                    {selectedPlugin.is_installed
                      ? selectedPlugin.is_active
                        ? t('plugins.status_active')
                        : t('plugins.status_inactive')
                      : t('plugins.status_not_installed')}
                  </Tag>
                  {selectedPlugin.sandbox_status && selectedPlugin.sandbox_status !== 'idle' && (
                    <Tag color={sandboxStatusColor[selectedPlugin.sandbox_status] || 'default'}>
                      {t('plugins.sandbox_label', { status: selectedPlugin.sandbox_status })}
                    </Tag>
                  )}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label={t('plugins.detail_checksum')} span={2}>
                <Text copyable className="gaf-text-xs" style={{ wordBreak: 'break-all' }}>
                  {selectedPlugin.checksum || '-'}
                </Text>
              </Descriptions.Item>
              <Descriptions.Item label={t('plugins.detail_installed_at')}>
                {selectedPlugin.installed_at || '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('plugins.detail_sandbox_pid')}>
                {selectedPlugin.sandbox_pid ?? '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('plugins.detail_description')} span={2}>
                {selectedPlugin.description || '-'}
              </Descriptions.Item>
            </Descriptions>

            <Card title={t('plugins.detail_manifest')} size="small" className="gaf-mb-lg">
              <pre
                className="gaf-m-0 gaf-p-md gaf-text-xs gaf-overflow-auto"
                style={{ background: designToken.colorBgLayout, borderRadius: 4, maxHeight: 300 }}
              >
                {JSON.stringify(selectedPlugin.manifest, null, 2)}
              </pre>
            </Card>

            {selectedPlugin.is_installed && (
              <Space>
                <Switch
                  checked={selectedPlugin.is_active}
                  onChange={() => handleToggle(selectedPlugin.id)}
                  checkedChildren={t('plugins.switch_enable')}
                  unCheckedChildren={t('plugins.switch_disable')}
                />
                <Popconfirm
                  title={t('plugins.confirm_uninstall_title')}
                  onConfirm={() => {
                    handleUninstall(selectedPlugin.id);
                  }}
                  okText={t('plugins.confirm_ok')}
                  cancelText={t('plugins.confirm_cancel')}
                >
                  <Button danger icon={<DeleteOutlined />}>
                    {t('plugins.btn_uninstall_plugin')}
                  </Button>
                </Popconfirm>
              </Space>
            )}
          </>
        )}
      </Drawer>
    </PageWrapper>
  );
}

export default PluginsPage;
