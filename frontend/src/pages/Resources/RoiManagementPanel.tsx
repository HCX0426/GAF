/**
 * ROI management panel — R37-P2 C4
 *
 * Provides CRUD against /api/v2/resources/resource-packs/{pk}/rois/ endpoints
 * (implemented in C3). Renders a pack selector + task tabs (public + per-task)
 * + ROI table with add/edit modal and delete confirmation.
 */
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  Card,
  Select,
  Button,
  Tabs,
  Table,
  Space,
  Modal,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  App,
  Typography,
  Empty,
} from 'antd';
import { PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { fetchResourcePacks, fetchRois, addRoi, deleteRoi, type RoiData } from '@/api/resources';
import type { ResourcePack } from '@/types/models';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from '@/i18n';
import { classifyError } from '@/utils/errorHandler';

const { Text } = Typography;

interface RoiFormValues {
  name: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

interface RoiRow {
  name: string;
  coords: number[];
  key: string;
}

export function RoiManagementPanel() {
  const { message } = App.useApp();
  const t = useTranslation();
  const [packList, setPackList] = useState<ResourcePack[]>([]);
  const [selectedPackId, setSelectedPackId] = useState<number | null>(null);
  const [roiData, setRoiData] = useState<RoiData>({});
  const [currentTask, setCurrentTask] = useState<string>('public');
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingRoi, setEditingRoi] = useState<{ name: string; coords: number[] } | null>(null);
  const [form] = Form.useForm<RoiFormValues>();

  useEffect(() => {
    loadPackList();
  }, []);

  const loadPackList = async () => {
    try {
      const res = await fetchResourcePacks({ page: 1, page_size: 100 });
      setPackList(res.results || []);
    } catch (err: unknown) {
      const classified = classifyError(err);
      message.error(t('resources.roi_msg_load_failed', { message: classified.message }));
    }
  };

  const loadRois = async (packId: number) => {
    setLoading(true);
    try {
      const data = await fetchRois(packId);
      setRoiData(data || {});
      setCurrentTask('public');
    } catch (err: unknown) {
      const classified = classifyError(err);
      message.error(t('resources.roi_msg_load_failed', { message: classified.message }));
    } finally {
      setLoading(false);
    }
  };

  const handlePackChange = (packId: number) => {
    setSelectedPackId(packId);
    void loadRois(packId);
  };

  const handleRefresh = () => {
    if (selectedPackId) void loadRois(selectedPackId);
  };

  const handleAddRoi = () => {
    setEditingRoi(null);
    form.resetFields();
    setModalOpen(true);
  };

  const handleEditRoi = (name: string, coords: number[]) => {
    setEditingRoi({ name, coords });
    form.setFieldsValue({
      name,
      x: coords[0],
      y: coords[1],
      w: coords[2],
      h: coords[3],
    });
    setModalOpen(true);
  };

  const handleSaveRoi = async () => {
    if (!selectedPackId) return;
    try {
      const values = await form.validateFields();
      const coords = [values.x, values.y, values.w, values.h];
      // If editing and the name changed, delete the old ROI first to avoid dup.
      if (editingRoi && editingRoi.name !== values.name) {
        await deleteRoi(selectedPackId, currentTask, editingRoi.name);
      }
      await addRoi(selectedPackId, currentTask, values.name, coords);
      message.success(t('resources.roi_msg_save_success'));
      setModalOpen(false);
      form.resetFields();
      setEditingRoi(null);
      await loadRois(selectedPackId);
    } catch (err: unknown) {
      const classified = classifyError(err);
      if (!String(classified.message).includes('validateFields')) {
        message.error(t('resources.roi_msg_save_failed', { message: classified.message }));
      }
    }
  };

  const handleDeleteRoi = async (name: string) => {
    if (!selectedPackId) return;
    try {
      await deleteRoi(selectedPackId, currentTask, name);
      message.success(t('resources.roi_msg_delete_success'));
      await loadRois(selectedPackId);
    } catch (err: unknown) {
      const classified = classifyError(err);
      message.error(t('resources.roi_msg_delete_failed', { message: classified.message }));
    }
  };

  // Current task's ROI list as table dataSource.
  const currentRoiList = useMemo<RoiRow[]>(() => {
    const roiMap = currentTask === 'public' ? roiData.public || {} : (roiData.tasks || {})[currentTask] || {};
    return Object.entries(roiMap).map(([name, coords]) => ({
      name,
      coords,
      key: name,
    }));
  }, [roiData, currentTask]);

  const columns: ColumnsType<RoiRow> = [
    { title: t('resources.roi_col_name'), dataIndex: 'name', key: 'name', width: 220, ellipsis: true },
    {
      title: t('resources.roi_col_coords'),
      dataIndex: 'coords',
      key: 'coords',
      render: (coords: number[]) => (
        <Text code>
          [{coords[0]}, {coords[1]}, {coords[2]}, {coords[3]}]
        </Text>
      ),
    },
    {
      title: t('resources.roi_col_action'),
      key: 'action',
      width: 180,
      render: (_, record) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEditRoi(record.name, record.coords)}
          >
            {t('resources.roi_btn_edit')}
          </Button>
          <Popconfirm
            title={t('resources.roi_confirm_delete', { name: record.name })}
            onConfirm={() => handleDeleteRoi(record.name)}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              {t('resources.roi_btn_delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  // Build task tabs: public first, then sorted task names.
  const taskTabs = useMemo<{ key: string; label: string }[]>(() => {
    const tabs: { key: string; label: string }[] = [{ key: 'public', label: t('resources.roi_task_public') }];
    const taskNames = Object.keys(roiData.tasks || {}).sort();
    for (const taskName of taskNames) {
      tabs.push({ key: taskName, label: taskName });
    }
    return tabs;
  }, [roiData, t]);

  const renderRoiTable = (): ReactNode => (
    <>
      <Space className="gaf-mb-md">
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAddRoi} disabled={!selectedPackId}>
          {t('resources.roi_btn_add')}
        </Button>
        <Text type="secondary">{t('resources.roi_total_count', { count: currentRoiList.length })}</Text>
      </Space>
      <Table
        columns={columns}
        dataSource={currentRoiList}
        rowKey="key"
        loading={loading}
        pagination={false}
        size="small"
        locale={{ emptyText: <Empty description={t('resources.roi_empty')} /> }}
      />
    </>
  );

  const tabItems = taskTabs.map((tab) => ({
    key: tab.key,
    label: tab.label,
    children: tab.key === currentTask ? renderRoiTable() : null,
  }));

  return (
    <Card title={t('resources.roi_title')}>
      <Space className="gaf-mb-lg" wrap>
        <Select
          showSearch
          allowClear
          style={{ minWidth: 280 }}
          placeholder={t('resources.roi_select_pack')}
          value={selectedPackId ?? undefined}
          onChange={handlePackChange}
          options={packList.map((p) => ({ label: `${p.name} v${p.version}`, value: p.id }))}
          filterOption={(input, option) => (option?.label ?? '').toLowerCase().includes(input.toLowerCase())}
        />
        <Button icon={<ReloadOutlined />} onClick={handleRefresh} disabled={!selectedPackId}>
          {t('resources.btn_refresh')}
        </Button>
      </Space>

      {selectedPackId ? (
        <Tabs activeKey={currentTask} onChange={setCurrentTask} items={tabItems} />
      ) : (
        <Empty description={t('resources.roi_select_pack')} />
      )}

      <Modal
        title={editingRoi ? t('resources.roi_btn_edit') : t('resources.roi_btn_add')}
        open={modalOpen}
        onOk={handleSaveRoi}
        onCancel={() => {
          setModalOpen(false);
          form.resetFields();
          setEditingRoi(null);
        }}
        okText={t('resources.btn_create')}
        cancelText={t('resources.btn_cancel')}
        width={520}
      >
        <Form form={form} layout="vertical" className="gaf-mt-lg">
          <Form.Item
            name="name"
            label={t('resources.roi_label_name')}
            rules={[{ required: true, message: t('resources.roi_validate_name_required') }]}
          >
            <Input placeholder="e.g., confirm_button" maxLength={100} autoComplete="off" />
          </Form.Item>
          <Space className="gaf-flex-between" size="middle">
            <Form.Item
              name="x"
              label={t('resources.roi_label_x')}
              rules={[{ required: true, message: t('resources.roi_validate_coords_required') }]}
              style={{ flex: 1, minWidth: 100 }}
            >
              <InputNumber min={0} max={1920} className="gaf-w-full" />
            </Form.Item>
            <Form.Item
              name="y"
              label={t('resources.roi_label_y')}
              rules={[{ required: true, message: t('resources.roi_validate_coords_required') }]}
              style={{ flex: 1, minWidth: 100 }}
            >
              <InputNumber min={0} max={1080} className="gaf-w-full" />
            </Form.Item>
            <Form.Item
              name="w"
              label={t('resources.roi_label_w')}
              rules={[{ required: true, message: t('resources.roi_validate_coords_required') }]}
              style={{ flex: 1, minWidth: 100 }}
            >
              <InputNumber min={1} max={1920} className="gaf-w-full" />
            </Form.Item>
            <Form.Item
              name="h"
              label={t('resources.roi_label_h')}
              rules={[{ required: true, message: t('resources.roi_validate_coords_required') }]}
              style={{ flex: 1, minWidth: 100 }}
            >
              <InputNumber min={1} max={1080} className="gaf-w-full" />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </Card>
  );
}

export default RoiManagementPanel;
