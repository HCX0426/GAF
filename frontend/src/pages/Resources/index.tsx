/**
 * resource pack management page — Phase 4.1 added strong
 * resource pack list + activate / deactivate + import / export + template library + verify status
 */
import { useEffect, useState } from 'react';
import {
  Table,
  Button,
  Space,
  Tag,
  Upload,
  Popconfirm,
  Tabs,
  App,
  Badge,
  Typography,
  Modal,
  Descriptions,
  Form,
  Input,
  Select,
} from 'antd';
import {
  PlusOutlined,
  UploadOutlined,
  DownloadOutlined,
  CheckCircleOutlined,
  StopOutlined,
  ReloadOutlined,
  HistoryOutlined,
  FolderOpenOutlined,
  AppstoreOutlined,
} from '@ant-design/icons';
import {
  fetchResourcePacks,
  activateResourcePack,
  deactivateResourcePack,
  importResourcePack,
  exportResourcePack,
  deleteResourcePack,
  scanResourcePacks,
  createResourcePack,
  fetchResourcePackVersionHistory,
  type ScanResult,
} from '@/api/resources';
import { fetchGameOptions, type GameOption } from '@/api/accounts';
import type { ResourcePack } from '@/types/models';
import type { ColumnsType } from 'antd/es/table';
import { classifyError, ErrorType } from '@/utils/errorHandler';
import { useTranslation, getLocale } from '@/i18n';
import TemplateGallery from './TemplateGallery';
import ValidationPanel from './ValidationPanel';
import RoiManagementPanel from './RoiManagementPanel';
import PageWrapper from '@/components/Common/PageWrapper';

const { Text } = Typography;

export function ResourcesPage() {
  const { message } = App.useApp();
  const t = useTranslation();
  const [packs, setPacks] = useState<ResourcePack[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [versionModalOpen, setVersionModalOpen] = useState(false);
  const [versionData, setVersionData] = useState<Record<string, unknown> | null>(null);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form] = Form.useForm();
  const [gameOptions, setGameOptions] = useState<GameOption[]>([]);

  useEffect(() => {
    loadPacks();
    loadGameOptions();
  }, []);

  const loadPacks = async () => {
    setLoading(true);
    try {
      const res = await fetchResourcePacks({ page: 1, page_size: 50 });
      setPacks(res.results || []);
      setTotal(res.count);
    } catch (err: unknown) {
      const classified = classifyError(err);
      message.error(t('resources.msg_load_failed', { message: classified.message }));
    } finally {
      setLoading(false);
    }
  };

  /** Load game options from backend for dropdown selection */
  const loadGameOptions = async () => {
    try {
      const res = await fetchGameOptions();
      setGameOptions(res.games || []);
    } catch (err: unknown) {
      console.warn('[Resources] Failed to load game options:', err);
    }
  };

  const [scanning, setScanning] = useState(false);

  const handleScan = async () => {
    setScanning(true);
    try {
      const result: ScanResult = await scanResourcePacks();
      if (result.results) {
        const tasksCreated = result.results.reduce((sum, r) => sum + (r.tasks_imported?.created || 0), 0);
        const templatesCreated = result.results.reduce((sum, r) => sum + (r.templates_imported?.created || 0), 0);
        const monitorsCreated = result.results.reduce((sum, r) => {
          const v = (r as Record<string, unknown>).monitors_imported as { created?: number } | undefined;
          return sum + (v?.created ?? 0);
        }, 0);
        const parts = [t('resources.unit_packs', { count: result.success })];
        if (tasksCreated > 0) parts.push(t('resources.unit_tasks', { count: tasksCreated }));
        if (templatesCreated > 0) parts.push(t('resources.unit_templates', { count: templatesCreated }));
        if (monitorsCreated > 0) parts.push(t('resources.unit_monitors', { count: monitorsCreated }));
        message.success(t('resources.msg_scan_complete', { detail: parts.join(' + ') }));

        if (result.ghost_packs && result.ghost_packs.length > 0) {
          const ghostNames = result.ghost_packs.map((g) => g.name).join('、');
          message.warning(
            t('resources.msg_ghost_packs_detected', { count: result.ghost_packs.length, names: ghostNames }),
            10,
          );
        }
      }
    } catch (err: unknown) {
      const classified = classifyError(err);
      message.error(t('resources.msg_scan_failed', { message: classified.message }));
    } finally {
      setScanning(false);
      loadPacks();
    }
  };

  const handleActivate = async (packId: number) => {
    try {
      await activateResourcePack(packId);
      message.success(t('resources.msg_activated'));
      loadPacks();
    } catch (err: unknown) {
      const classified = classifyError(err);
      message.error(t('resources.msg_activate_failed', { message: classified.message }));
    }
  };

  const handleDeactivate = async (packId: number) => {
    try {
      await deactivateResourcePack(packId);
      message.success(t('resources.msg_deactivated'));
      loadPacks();
    } catch (err: unknown) {
      const classified = classifyError(err);
      message.error(t('resources.msg_deactivate_failed', { message: classified.message }));
    }
  };

  const handleImport = async (file: File) => {
    try {
      await importResourcePack(file);
      message.success(t('resources.msg_import_success'));
      loadPacks();
    } catch (err: unknown) {
      const classified = classifyError(err);
      message.error(t('resources.msg_import_failed', { message: classified.message }));
    }
    return false;
  };

  const handleExport = async (packId: number) => {
    try {
      const blob = await exportResourcePack(packId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `resource-pack-${packId}.zip`;
      a.click();
      window.URL.revokeObjectURL(url);
      message.success(t('resources.msg_export_success'));
    } catch (err: unknown) {
      const classified = classifyError(err);
      message.error(t('resources.msg_export_failed', { message: classified.message }));
    }
  };

  const handleDelete = async (packId: number) => {
    try {
      await deleteResourcePack(packId);
      message.success(t('resources.msg_deleted'));
      loadPacks();
    } catch (err: unknown) {
      const classified = classifyError(err);
      message.error(t('resources.msg_delete_failed', { message: classified.message }));
    }
  };

  const handleViewVersionHistory = async (record: ResourcePack) => {
    try {
      const data = await fetchResourcePackVersionHistory(record.id);
      setVersionData(data);
      setVersionModalOpen(true);
    } catch (err: unknown) {
      const classified = classifyError(err);
      message.warning(t('resources.msg_version_load_failed', { message: classified.message }));
    }
  };

  const handleOpenDirectory = (record: ResourcePack) => {
    if (!record.directory_path) return;
    try {
      window.open(`file://${record.directory_path}`, '_blank');
    } catch {
      message.warning(t('resources.msg_open_dir_failed'));
    }
  };

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      setCreating(true);
      const created = await createResourcePack(values as Record<string, unknown>);
      message.success(t('resources.msg_create_success', { name: created.name }));
      setCreateModalOpen(false);
      form.resetFields();
      loadPacks();
    } catch (err: unknown) {
      const classified = classifyError(err);
      if (classified.type === ErrorType.CLIENT && !String(classified.message).includes('validateFields')) {
        message.error(t('resources.msg_create_failed', { message: classified.message }));
      } else if (!String(classified.message).includes('validateFields')) {
        message.error(t('resources.msg_create_failed', { message: classified.message }));
      }
    } finally {
      setCreating(false);
    }
  };

  const columns: ColumnsType<ResourcePack> = [
    { title: t('resources.col_name'), dataIndex: 'name', key: 'name', width: 180, ellipsis: true },
    {
      title: t('resources.col_version'),
      dataIndex: 'version',
      key: 'version',
      width: 80,
      render: (val: string) => (val ? <Tag color="blue">{val}</Tag> : '-'),
    },
    {
      title: t('resources.col_target_app'),
      dataIndex: 'target_app',
      key: 'target_app',
      width: 120,
      render: (val: string | undefined) =>
        val ? (
          <Tag
            icon={
              <span aria-hidden="true">
                <AppstoreOutlined />
              </span>
            }
            color="geekblue"
          >
            {val}
          </Tag>
        ) : (
          <Text type="secondary">-</Text>
        ),
    },
    {
      title: t('resources.col_game_profile'),
      key: 'game_profile',
      width: 130,
      ellipsis: true,
      render: (_: unknown, record: ResourcePack) => {
        // R37-P1: prefer game_profile_detail.game_name; fallback to FK id; else '-'.
        if (record.game_profile_detail?.game_name) {
          return <Tag color="purple">{record.game_profile_detail.game_name}</Tag>;
        }
        if (record.game_profile) {
          return <Tag color="purple">#{record.game_profile}</Tag>;
        }
        return <Text type="secondary">-</Text>;
      },
    },
    {
      title: t('resources.col_status'),
      dataIndex: 'is_active',
      key: 'is_active',
      width: 90,
      render: (isActive: boolean) => (
        <Tag color={isActive ? 'green' : 'default'}>
          {isActive ? t('resources.status_active') : t('resources.status_inactive')}
        </Tag>
      ),
    },
    {
      title: t('resources.col_description'),
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: t('resources.col_path'),
      dataIndex: 'directory_path',
      key: 'directory_path',
      width: 220,
      ellipsis: true,
      render: (val: string) =>
        val ? (
          <Text code className="gaf-text-xxs">
            {val}
          </Text>
        ) : (
          '-'
        ),
    },
    {
      title: t('resources.col_task_count'),
      dataIndex: 'task_count',
      key: 'task_count',
      width: 100,
      render: (count: number) =>
        count != null && count > 0 ? (
          <Badge count={count} showZero={false} overflowCount={99}>
            <Text type="secondary">{t('resources.unit_count', { count })}</Text>
          </Badge>
        ) : (
          <Text type="secondary">0</Text>
        ),
    },
    {
      title: t('resources.col_action'),
      key: 'action',
      width: 300,
      render: (_, record) => (
        <Space wrap>
          {!record.is_active ? (
            <Button type="link" size="small" icon={<CheckCircleOutlined />} onClick={() => handleActivate(record.id)}>
              {t('resources.btn_activate')}
            </Button>
          ) : (
            <Button
              type="link"
              size="small"
              icon={
                <span aria-hidden="true">
                  <StopOutlined />
                </span>
              }
              onClick={() => handleDeactivate(record.id)}
            >
              {t('resources.btn_deactivate')}
            </Button>
          )}
          <Button
            type="link"
            size="small"
            icon={
              <span aria-hidden="true">
                <HistoryOutlined />
              </span>
            }
            onClick={() => handleViewVersionHistory(record)}
          >
            {t('resources.btn_version')}
          </Button>
          <Button
            type="link"
            size="small"
            icon={<FolderOpenOutlined />}
            onClick={() => handleOpenDirectory(record)}
            disabled={!record.directory_path}
          >
            {t('resources.btn_directory')}
          </Button>
          <Button type="link" size="small" icon={<DownloadOutlined />} onClick={() => handleExport(record.id)}>
            {t('resources.btn_export')}
          </Button>
          <Popconfirm title={t('resources.confirm_delete')} onConfirm={() => handleDelete(record.id)}>
            <Button type="link" size="small" danger>
              {t('resources.btn_delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <PageWrapper
      title={t('resources.page_title')}
      extra={
        <Space>
          <Button
            type="primary"
            icon={
              <span aria-hidden="true">
                <PlusOutlined />
              </span>
            }
            onClick={() => setCreateModalOpen(true)}
          >
            {t('resources.btn_new')}
          </Button>
          <Upload beforeUpload={handleImport} showUploadList={false} accept=".zip,.tar.gz">
            <Button icon={<UploadOutlined />}>{t('resources.btn_import')}</Button>
          </Upload>
          <Button
            icon={
              <span aria-hidden="true">
                <ReloadOutlined />
              </span>
            }
            onClick={handleScan}
            loading={scanning}
          >
            {t('resources.btn_refresh')}
          </Button>
        </Space>
      }
    >
      <Tabs
        items={[
          {
            key: 'packs',
            label: t('resources.tab_packs'),
            children: (
              <Table
                columns={columns}
                dataSource={packs || []}
                rowKey="id"
                loading={loading}
                pagination={{ total, showTotal: (cnt) => t('resources.total_count', { count: cnt }) }}
              />
            ),
          },
          { key: 'templates', label: t('resources.tab_templates'), children: <TemplateGallery /> },
          { key: 'validation', label: t('resources.tab_validation'), children: <ValidationPanel /> },
          { key: 'rois', label: t('resources.tab_rois'), children: <RoiManagementPanel /> },
        ]}
      />
      <Modal
        title={t('resources.title_new_pack')}
        open={createModalOpen}
        onOk={handleCreate}
        onCancel={() => {
          setCreateModalOpen(false);
          form.resetFields();
        }}
        confirmLoading={creating}
        okText={t('resources.btn_create')}
        cancelText={t('resources.btn_cancel')}
        width={500}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 20 }}>
          <Form.Item
            name="name"
            label={t('resources.label_pack_name')}
            rules={[{ required: true, message: t('resources.validate_pack_name_required') }]}
          >
            <Input placeholder={t('resources.placeholder_pack_name')} maxLength={100} autoComplete="off" />
          </Form.Item>
          <Form.Item name="version" label={t('resources.label_version')} initialValue="1.0">
            <Input placeholder="1.0" maxLength={20} autoComplete="off" />
          </Form.Item>
          <Form.Item name="target_app" label={t('resources.label_target_app')}>
            <Select
              showSearch
              allowClear
              placeholder={t('resources.placeholder_target_app')}
              options={gameOptions.map((g) => ({ label: g.name, value: g.name }))}
              filterOption={(input, option) => (option?.label ?? '').toLowerCase().includes(input.toLowerCase())}
            />
          </Form.Item>
          <Form.Item name="description" label={t('resources.label_description')}>
            <Input.TextArea
              rows={3}
              placeholder={t('resources.placeholder_description')}
              maxLength={500}
              autoComplete="off"
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t('resources.title_version_info')}
        open={versionModalOpen}
        onCancel={() => setVersionModalOpen(false)}
        footer={null}
        width={600}
      >
        {versionData && (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label={t('resources.label_pack_name_field')}>
              {String(versionData.pack_name || '-')}
            </Descriptions.Item>
            <Descriptions.Item label={t('resources.label_current_version')}>
              <Tag color="blue">{String(versionData.current_version || '-')}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t('resources.label_description')}>
              {String(versionData.description || '-')}
            </Descriptions.Item>
            <Descriptions.Item label={t('resources.label_template_count')}>
              <Badge count={Number(versionData.template_count || 0)} showZero overflowCount={9999} />
            </Descriptions.Item>
            <Descriptions.Item label={t('resources.col_status')}>
              <Tag color={versionData.is_active ? 'green' : 'default'}>
                {versionData.is_active ? t('resources.status_active') : t('resources.status_inactive')}
              </Tag>
            </Descriptions.Item>
            {Boolean(versionData.created_at) && (
              <Descriptions.Item label={t('resources.label_created_at')}>
                {new Date(String(versionData.created_at)).toLocaleString(getLocale())}
              </Descriptions.Item>
            )}
            {Boolean(versionData.updated_at) && (
              <Descriptions.Item label={t('resources.label_updated_at')}>
                {new Date(String(versionData.updated_at)).toLocaleString(getLocale())}
              </Descriptions.Item>
            )}
          </Descriptions>
        )}
      </Modal>
    </PageWrapper>
  );
}

export default ResourcesPage;
