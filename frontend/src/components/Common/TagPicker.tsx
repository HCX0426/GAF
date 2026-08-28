/**
 * Tag picker component (P-014)
 * Allows selecting and creating tags with color display
 */
import { useEffect, useState } from 'react';
import { Select, Modal, Input, Button, Space, ColorPicker, App, Typography } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { fetchTags, createTag, type Tag } from '@/api/resources';
import { useTranslation } from '@/i18n';

const { Text } = Typography;

interface TagPickerProps {
  /** Currently selected tag IDs */
  value?: number[];
  /** Callback when selection changes */
  onChange?: (value: number[]) => void;
  /** Whether multiple selection is allowed (default: true) */
  multiple?: boolean;
}

/**
 * TagPicker - Select and create tags with colored display
 * @param props - Component props including value, onChange, multiple
 */
export function TagPicker({ value = [], onChange, multiple = true }: TagPickerProps) {
  const { message } = App.useApp();
  const t = useTranslation();
  const [tags, setTags] = useState<Tag[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [newTagName, setNewTagName] = useState('');
  const [newTagColor, setNewTagColor] = useState('#1890ff');

  useEffect(() => {
    loadTags();
  }, []);

  /** Load all available tags from the API */
  const loadTags = async () => {
    setLoading(true);
    try {
      const data = await fetchTags();
      setTags(data);
    } catch {
      message.error(t('common.tag.load_failed'));
    } finally {
      setLoading(false);
    }
  };

  /** Handle tag selection change */
  const handleChange = (selected: number | number[]) => {
    const selectedIds = Array.isArray(selected) ? selected : [selected];
    onChange?.(selectedIds);
  };

  /** Create a new tag and add it to selection */
  const handleCreateTag = async () => {
    if (!newTagName.trim()) {
      message.warning(t('common.tag.name_required'));
      return;
    }

    try {
      const newTag = await createTag({
        name: newTagName.trim(),
        color: newTagColor,
      });
      setTags((prev) => [...prev, newTag]);
      onChange?.([...value, newTag.id]);
      setNewTagName('');
      setNewTagColor('#1890ff');
      setModalOpen(false);
      message.success(t('common.tag.create_success'));
    } catch {
      message.error(t('common.tag.create_failed'));
    }
  };

  /** Render a tag option with colored dot */
  const tagOptionRender = (option: { label: string; value: number }) => {
    const tag = tags.find((t) => t.id === option.value);
    const color = tag?.color || '#999';

    return (
      <span>
        <span
          className="gaf-mr-sm"
          style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', backgroundColor: color }}
        />
        {option.label}
      </span>
    );
  };

  /** Render selected tag display */
  const tagRender = (option: { label: string; value: number }) => {
    const tag = tags.find((t) => t.id === option.value);
    const color = tag?.color || '#999';

    return (
      <span
        className="gaf-inline-flex gaf-text-xs"
        style={{
          alignItems: 'center',
          padding: '2px 8px',
          borderRadius: 4,
          backgroundColor: `${color}22`,
          border: `1px solid ${color}55`,
          margin: '2px 4px 2px 0',
        }}
      >
        <span
          className="gaf-mr-xs"
          style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', backgroundColor: color }}
        />
        {option.label}
      </span>
    );
  };

  return (
    <>
      <Select
        mode={multiple ? 'multiple' : undefined}
        value={value}
        onChange={handleChange}
        options={tags.map((tag) => ({
          label: tag.name,
          value: tag.id,
        }))}
        optionRender={tagOptionRender as never}
        tagRender={tagRender as never}
        loading={loading}
        placeholder="选择标签"
        style={{ minWidth: 200 }}
        popupRender={(menu) => (
          <>
            {menu}
            <div className="gaf-py-sm gaf-px-md" style={{ borderTop: '1px solid #f0f0f0' }}>
              <Button type="link" icon={<PlusOutlined />} onClick={() => setModalOpen(true)} className="gaf-p-0">
                新建标签
              </Button>
            </div>
          </>
        )}
      />

      <Modal
        title="新建标签"
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false);
          setNewTagName('');
          setNewTagColor('#1890ff');
        }}
        footer={[
          <Button
            key="cancel"
            onClick={() => {
              setModalOpen(false);
              setNewTagName('');
              setNewTagColor('#1890ff');
            }}
          >
            取消
          </Button>,
          <Button key="submit" type="primary" onClick={handleCreateTag}>
            创建
          </Button>,
        ]}
      >
        <Space orientation="vertical" className="gaf-w-full" size="middle">
          <div>
            <Text className="gaf-mb-xs" style={{ display: 'block' }}>
              标签名称
            </Text>
            <Input
              value={newTagName}
              onChange={(e) => setNewTagName(e.target.value)}
              placeholder="输入标签名称"
              maxLength={20}
              showCount
            />
          </div>
          <div>
            <Text className="gaf-mb-xs" style={{ display: 'block' }}>
              标签颜色
            </Text>
            <ColorPicker
              value={newTagColor}
              onChange={(color) => setNewTagColor(color.toHexString())}
              presets={[
                {
                  label: '推荐',
                  colors: [
                    '#f56954',
                    '#00a65a',
                    '#f39c12',
                    '#00c0ef',
                    '#3c8dbc',
                    '#d2d6de',
                    '#1890ff',
                    '#52c41a',
                    '#fa8c16',
                    '#722ed1',
                    '#eb2f96',
                    '#13c2c2',
                  ],
                },
              ]}
            />
          </div>
          <div>
            <Text type="secondary">预览：</Text>
            <span
              className="gaf-inline-flex gaf-text-xs"
              style={{
                alignItems: 'center',
                padding: '2px 8px',
                borderRadius: 4,
                backgroundColor: `${newTagColor}22`,
                border: `1px solid ${newTagColor}55`,
              }}
            >
              <span
                className="gaf-mr-xs"
                style={{
                  display: 'inline-block',
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  backgroundColor: newTagColor,
                }}
              />
              {newTagName || '标签名称'}
            </span>
          </div>
        </Space>
      </Modal>
    </>
  );
}

export default TagPicker;
