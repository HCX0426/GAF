/**
 * TagManager — task label management
 *
 * provides label CRUD feature: create ( name + color select ), edit, delete.
 * built-in 8 color preset color palette, with table form show label list,
 * every row show name, color dot, associate task count and action button.
 */

import { useState, useCallback, useMemo } from 'react';
import { Table, Button, Modal, Form, Input, Popconfirm, Space, Card, Tag, Typography } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from '@/i18n';

const { Text } = Typography;

/** preset color palette */
const PRESET_COLORS = ['#1890ff', '#52c41a', '#faad14', '#ff4d4f', '#722ed1', '#13c2c2', '#eb2f96', '#fa541c'];

/** label data structure */
interface TaskTag {
  id: string;
  name: string;
  color: string;
  taskCount: number;
  createdAt: string;
}

/** form field value */
interface TagFormValues {
  name: string;
  color: string;
}

/**
 * mock initial start label data.
 * NOTE: Chinese names here are sample data values (not UI strings) — they
 * demonstrate realistic tag names a user might create. In production these
 * come from the API. ESLint disabled per-line because this is data, not i18n.
 */
const INITIAL_TAGS: TaskTag[] = [
  // eslint-disable-next-line no-restricted-syntax
  { id: 'tag-001', name: '高优先级', color: '#ff4d4f', taskCount: 12, createdAt: '2026-05-01' },
  // eslint-disable-next-line no-restricted-syntax
  { id: 'tag-002', name: '日常巡检', color: '#1890ff', taskCount: 28, createdAt: '2026-05-03' },
  // eslint-disable-next-line no-restricted-syntax
  { id: 'tag-003', name: '资源密集', color: '#faad14', taskCount: 5, createdAt: '2026-05-05' },
  // eslint-disable-next-line no-restricted-syntax
  { id: 'tag-004', name: '夜间执行', color: '#722ed1', taskCount: 15, createdAt: '2026-05-08' },
  // eslint-disable-next-line no-restricted-syntax
  { id: 'tag-005', name: '测试环境', color: '#13c2c2', taskCount: 8, createdAt: '2026-05-10' },
  // eslint-disable-next-line no-restricted-syntax
  { id: 'tag-006', name: '生产环境', color: '#52c41a', taskCount: 22, createdAt: '2026-05-12' },
  // eslint-disable-next-line no-restricted-syntax
  { id: 'tag-007', name: '需要人工审核', color: '#eb2f96', taskCount: 3, createdAt: '2026-05-15' },
  // eslint-disable-next-line no-restricted-syntax
  { id: 'tag-008', name: '一次性任务', color: '#fa541c', taskCount: 6, createdAt: '2026-05-18' },
];

/** generate unique ID */
function generateId(): string {
  return `tag-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

export function TagManager() {
  const t = useTranslation();
  const [tags, setTags] = useState<TaskTag[]>(INITIAL_TAGS);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingTag, setEditingTag] = useState<TaskTag | null>(null);
  const [form] = Form.useForm<TagFormValues>();

  /** open create new label modal */
  const handleCreate = useCallback(() => {
    setEditingTag(null);
    form.resetFields();
    form.setFieldsValue({ color: PRESET_COLORS[0] });
    setModalOpen(true);
  }, [form]);

  /** open edit label modal */
  const handleEdit = useCallback(
    (tag: TaskTag) => {
      setEditingTag(tag);
      form.setFieldsValue({ name: tag.name, color: tag.color });
      setModalOpen(true);
    },
    [form],
  );

  /** delete label */
  const handleDelete = useCallback((id: string) => {
    setTags((prev) => prev.filter((t) => t.id !== id));
  }, []);

  /** submit form ( create new or update ) */
  const handleSubmit = useCallback(async () => {
    try {
      const values = await form.validateFields();
      if (editingTag) {
        /** update existing label */
        setTags((prev) =>
          prev.map((t) => (t.id === editingTag.id ? { ...t, name: values.name, color: values.color } : t)),
        );
      } else {
        /** create new label */
        const newTag: TaskTag = {
          id: generateId(),
          name: values.name,
          color: values.color,
          taskCount: 0,
          createdAt: new Date().toISOString().split('T')[0],
        };
        setTags((prev) => [newTag, ...prev]);
      }
      setModalOpen(false);
      form.resetFields();
    } catch {
      // validate fail not handle
    }
  }, [form, editingTag]);

  /** cancel modal */
  const handleCancel = useCallback(() => {
    setModalOpen(false);
    setEditingTag(null);
    form.resetFields();
  }, [form]);

  /** table column definition */
  const columns: ColumnsType<TaskTag> = useMemo(
    () => [
      {
        title: t('tag.col_name'),
        dataIndex: 'name',
        key: 'name',
        render: (name: string, record: TaskTag) => (
          <Space>
            <span
              style={{
                display: 'inline-block',
                width: 12,
                height: 12,
                borderRadius: '50%',
                backgroundColor: record.color,
              }}
            />
            <span className="gaf-font-medium">{name}</span>
          </Space>
        ),
      },
      {
        title: t('tag.col_color'),
        dataIndex: 'color',
        key: 'color',
        width: 120,
        render: (color: string) => <Tag color={color}>{color}</Tag>,
      },
      {
        title: t('tag.col_task_count'),
        dataIndex: 'taskCount',
        key: 'taskCount',
        width: 120,
        sorter: (a, b) => a.taskCount - b.taskCount,
        defaultSortOrder: 'descend',
      },
      {
        title: t('tag.col_created_at'),
        dataIndex: 'createdAt',
        key: 'createdAt',
        width: 130,
      },
      {
        title: t('tag.col_action'),
        key: 'action',
        width: 140,
        render: (_: unknown, record: TaskTag) => (
          <Space size="small">
            <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
              {t('tag.edit')}
            </Button>
            <Popconfirm
              title={t('tag.confirm_delete')}
              description={t('tag.confirm_delete_desc', { name: record.name })}
              onConfirm={() => handleDelete(record.id)}
              okText={t('app.delete')}
              cancelText={t('app.cancel')}
              okButtonProps={{ danger: true }}
            >
              <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                {t('app.delete')}
              </Button>
            </Popconfirm>
          </Space>
        ),
      },
    ],
    [handleEdit, handleDelete, t],
  );

  return (
    <Card
      title={t('tag.title')}
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
          {t('tag.create_button')}
        </Button>
      }
    >
      <Table
        dataSource={tags}
        columns={columns}
        rowKey="id"
        pagination={{ pageSize: 10, size: 'small' }}
        size="middle"
        locale={{ emptyText: t('tag.empty') }}
      />

      {/* 新建/编辑弹窗 */}
      <Modal
        title={editingTag ? t('tag.edit_title') : t('tag.create_title')}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={handleCancel}
        okText={editingTag ? t('app.save') : t('tag.create')}
        cancelText={t('app.cancel')}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" initialValues={{ name: '', color: PRESET_COLORS[0] }}>
          <Form.Item
            name="name"
            label={t('tag.col_name')}
            rules={[
              { required: true, message: t('tag.name_required') },
              { max: 20, message: t('tag.name_max') },
            ]}
          >
            <Input placeholder={t('tag.name_placeholder')} maxLength={20} />
          </Form.Item>

          <Form.Item name="color" label={t('tag.color_label')}>
            <div className="gaf-flex gaf-gap-sm gaf-flex-wrap">
              {PRESET_COLORS.map((color) => (
                <Form.Item noStyle key={color} shouldUpdate>
                  {({ getFieldValue }) => (
                    <button
                      type="button"
                      onClick={() => form.setFieldsValue({ color })}
                      aria-label={t('tag.select_color')}
                      className="gaf-p-0"
                      style={{
                        width: 32,
                        height: 32,
                        borderRadius: 6,
                        border: getFieldValue('color') === color ? '3px solid #1890ff' : '2px solid #d9d9d9',
                        backgroundColor: color,
                        cursor: 'pointer',
                        transition: 'opacity 0.2s, background-color 0.2s',
                      }}
                    />
                  )}
                </Form.Item>
              ))}
            </div>
          </Form.Item>

          <Form.Item noStyle shouldUpdate>
            {({ getFieldValue }) =>
              getFieldValue('name') && getFieldValue('color') ? (
                <div className="gaf-mt-sm">
                  <Text className="gaf-mr-sm">{t('tag.preview')}</Text>
                  <Tag color={getFieldValue('color')} className="gaf-text-sm gaf-py-xs gaf-px-md">
                    {getFieldValue('name')}
                  </Tag>
                </div>
              ) : null
            }
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}

export default TagManager;
