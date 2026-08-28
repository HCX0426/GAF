/**
 * Skill Market page
 * Browse approved skills, publish/import/review skills.
 */
import { useEffect, useState, useCallback } from 'react';
import {
  App,
  Button,
  Card,
  Input,
  Modal,
  Rate,
  Space,
  Table,
  Tag,
  Typography,
  Descriptions,
  Tabs,
  Form,
  Select,
  theme,
} from 'antd';
import { CloudUploadOutlined, DownloadOutlined, ReloadOutlined, StarOutlined } from '@ant-design/icons';
import PageWrapper from '@/components/Common/PageWrapper';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from '@/i18n';
import {
  fetchMarketItems,
  fetchMyPublished,
  importMarketItem,
  publishSkill,
  reviewMarketItem,
  type SkillMarketItem,
} from '@/api/skills';
import { fetchSkills } from '@/api/skills';
import type { SkillDefinition } from '@/types/models';

const { Text, Paragraph } = Typography;

/** Status tag color mapping */
const statusColor: Record<SkillMarketItem['status'], string> = {
  pending: 'orange',
  approved: 'green',
  rejected: 'red',
  removed: 'default',
};

/** Format date string to locale-aware short date */
function formatDate(iso: string | null): string {
  if (!iso) return '-';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString();
}

export function SkillMarketPage() {
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const t = useTranslation();
  const [activeTab, setActiveTab] = useState('market');
  const [marketItems, setMarketItems] = useState<SkillMarketItem[]>([]);
  const [myItems, setMyItems] = useState<SkillMarketItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [publishModalOpen, setPublishModalOpen] = useState(false);
  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [currentItem, setCurrentItem] = useState<SkillMarketItem | null>(null);
  const [skills, setSkills] = useState<SkillDefinition[]>([]);
  const [publishForm] = Form.useForm();
  const [reviewForm] = Form.useForm();
  const [reviewRating, setReviewRating] = useState(5);

  /** Load market items (approved) */
  const loadMarketItems = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchMarketItems({ page_size: 100 });
      setMarketItems(res.results || []);
    } catch {
      message.error(t('skillMarket.msg_load_failed'));
    } finally {
      setLoading(false);
    }
  }, [message, t]);

  /** Load my published items (all statuses) */
  const loadMyItems = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchMyPublished({ page_size: 100 });
      setMyItems(res.results || []);
    } catch {
      message.error(t('skillMarket.msg_load_failed'));
    } finally {
      setLoading(false);
    }
  }, [message, t]);

  /** Load skill definitions for publish form */
  const loadSkillsForPublish = useCallback(async () => {
    try {
      const res = await fetchSkills({ page_size: 100 });
      setSkills(res.results || []);
    } catch {
      // Silent fail — publish modal will show empty skill list
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        if (activeTab === 'market') {
          const res = await fetchMarketItems({ page_size: 100 });
          if (!cancelled) setMarketItems(res.results || []);
        } else {
          const res = await fetchMyPublished({ page_size: 100 });
          if (!cancelled) setMyItems(res.results || []);
        }
      } catch {
        if (!cancelled) message.error(t('skillMarket.msg_load_failed'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [activeTab, message, t]);

  /** Handle publish submit */
  const handlePublish = async () => {
    try {
      const values = await publishForm.validateFields();
      await publishSkill({
        skill: Number(values.skill),
        title: values.title,
        description: values.description || '',
        tags: values.tags || [],
        version: values.version || '1.0',
      });
      message.success(t('skillMarket.msg_publish_success'));
      setPublishModalOpen(false);
      publishForm.resetFields();
      // Switch to my-published tab to show the new item
      setActiveTab('mine');
    } catch (err) {
      if (err && typeof err === 'object' && 'errorFields' in err) return; // validation error
      message.error(t('skillMarket.msg_publish_failed'));
    }
  };

  /** Handle import (copy skill to current user) */
  const handleImport = async (item: SkillMarketItem) => {
    try {
      const res = await importMarketItem(item.id);
      message.success(t('skillMarket.msg_import_success', { name: res.skill_name }));
      loadMarketItems();
    } catch {
      message.error(t('skillMarket.msg_import_failed'));
    }
  };

  /** Open review modal */
  const openReview = (item: SkillMarketItem) => {
    setCurrentItem(item);
    setReviewRating(5);
    reviewForm.resetFields();
    setReviewModalOpen(true);
  };

  /** Handle review submit */
  const handleReview = async () => {
    if (!currentItem) return;
    try {
      const values = await reviewForm.validateFields();
      await reviewMarketItem(currentItem.id, {
        rating: reviewRating,
        comment: values.comment || '',
      });
      message.success(t('skillMarket.msg_review_success'));
      setReviewModalOpen(false);
      loadMarketItems();
    } catch (err) {
      if (err && typeof err === 'object' && 'errorFields' in err) return;
      message.error(t('skillMarket.msg_review_failed'));
    }
  };

  /** Open detail modal */
  const openDetail = (item: SkillMarketItem) => {
    setCurrentItem(item);
    setDetailModalOpen(true);
  };

  /** Market list columns */
  const marketColumns: ColumnsType<SkillMarketItem> = [
    {
      title: t('skillMarket.col_title'),
      dataIndex: 'title',
      key: 'title',
      width: 200,
      ellipsis: true,
      render: (title: string, record) => (
        <a onClick={() => openDetail(record)} className="gaf-font-medium">
          {title}
        </a>
      ),
    },
    {
      title: t('skillMarket.col_skill'),
      dataIndex: 'skill_name',
      key: 'skill_name',
      width: 160,
      ellipsis: true,
    },
    {
      title: t('skillMarket.col_publisher'),
      dataIndex: 'publisher_name',
      key: 'publisher_name',
      width: 120,
      ellipsis: true,
    },
    {
      title: t('skillMarket.col_version'),
      dataIndex: 'version',
      key: 'version',
      width: 80,
    },
    {
      title: t('skillMarket.col_tags'),
      dataIndex: 'tags',
      key: 'tags',
      width: 200,
      render: (tags: string[]) => tags?.map((tag) => <Tag key={tag}>{tag}</Tag>),
    },
    {
      title: t('skillMarket.col_rating'),
      key: 'rating',
      width: 120,
      render: (_: unknown, record) => (
        <Space size={4}>
          <StarOutlined style={{ color: token.colorWarning }} />
          <span>{record.rating_avg.toFixed(1)}</span>
          <Text type="secondary">({record.rating_count})</Text>
        </Space>
      ),
    },
    {
      title: t('skillMarket.col_downloads'),
      dataIndex: 'download_count',
      key: 'download_count',
      width: 100,
    },
    {
      title: t('skillMarket.col_actions'),
      key: 'actions',
      width: 180,
      render: (_: unknown, record) => (
        <Space size={4}>
          <Button size="small" icon={<DownloadOutlined />} onClick={() => handleImport(record)}>
            {t('skillMarket.btn_import')}
          </Button>
          <Button size="small" icon={<StarOutlined />} onClick={() => openReview(record)}>
            {t('skillMarket.btn_review')}
          </Button>
        </Space>
      ),
    },
  ];

  /** My-published list columns (includes status) */
  const myColumns: ColumnsType<SkillMarketItem> = [
    {
      title: t('skillMarket.col_title'),
      dataIndex: 'title',
      key: 'title',
      width: 200,
      ellipsis: true,
      render: (title: string, record) => (
        <a onClick={() => openDetail(record)} className="gaf-font-medium">
          {title}
        </a>
      ),
    },
    {
      title: t('skillMarket.col_skill'),
      dataIndex: 'skill_name',
      key: 'skill_name',
      width: 160,
      ellipsis: true,
    },
    {
      title: t('skillMarket.col_status'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: SkillMarketItem['status']) => (
        <Tag color={statusColor[status]}>{t(`skillMarket.status_${status}`)}</Tag>
      ),
    },
    {
      title: t('skillMarket.col_version'),
      dataIndex: 'version',
      key: 'version',
      width: 80,
    },
    {
      title: t('skillMarket.col_downloads'),
      dataIndex: 'download_count',
      key: 'download_count',
      width: 100,
    },
    {
      title: t('skillMarket.col_rating'),
      key: 'rating',
      width: 120,
      render: (_: unknown, record) => (
        <Space size={4}>
          <StarOutlined style={{ color: token.colorWarning }} />
          <span>{record.rating_avg.toFixed(1)}</span>
          <Text type="secondary">({record.rating_count})</Text>
        </Space>
      ),
    },
    {
      title: t('skillMarket.col_published_at'),
      dataIndex: 'published_at',
      key: 'published_at',
      width: 120,
      render: formatDate,
    },
  ];

  return (
    <PageWrapper
      title={t('skillMarket.page_title')}
      extra={
        <Space>
          <Button
            type="primary"
            icon={<CloudUploadOutlined />}
            onClick={() => {
              loadSkillsForPublish();
              setPublishModalOpen(true);
            }}
          >
            {t('skillMarket.btn_publish')}
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => (activeTab === 'market' ? loadMarketItems() : loadMyItems())}
          >
            {t('skillMarket.btn_refresh')}
          </Button>
        </Space>
      }
    >
      <Card>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'market',
              label: t('skillMarket.tab_market'),
              children: (
                <Table
                  columns={marketColumns}
                  dataSource={marketItems}
                  rowKey="id"
                  loading={loading}
                  size="small"
                  pagination={{ pageSize: 10, showSizeChanger: true }}
                />
              ),
            },
            {
              key: 'mine',
              label: t('skillMarket.tab_mine'),
              children: (
                <Table
                  columns={myColumns}
                  dataSource={myItems}
                  rowKey="id"
                  loading={loading}
                  size="small"
                  pagination={{ pageSize: 10, showSizeChanger: true }}
                />
              ),
            },
          ]}
        />
      </Card>

      {/* Publish modal */}
      <Modal
        title={t('skillMarket.modal_publish_title')}
        open={publishModalOpen}
        onOk={handlePublish}
        onCancel={() => setPublishModalOpen(false)}
        okText={t('skillMarket.btn_publish')}
        width={560}
      >
        <Form form={publishForm} layout="vertical" preserve={false}>
          <Form.Item
            name="skill"
            label={t('skillMarket.col_skill')}
            rules={[{ required: true, message: t('skillMarket.msg_skill_required') }]}
          >
            <Select
              placeholder={t('skillMarket.placeholder_skill')}
              showSearch
              optionFilterProp="label"
              options={skills.map((s) => ({ value: Number(s.id), label: `${s.name} v${s.version}` }))}
            />
          </Form.Item>
          <Form.Item
            name="title"
            label={t('skillMarket.col_title')}
            rules={[{ required: true, message: t('skillMarket.msg_title_required') }]}
          >
            <Input placeholder={t('skillMarket.placeholder_title')} maxLength={255} />
          </Form.Item>
          <Form.Item name="description" label={t('skillMarket.col_description')}>
            <Input.TextArea rows={3} placeholder={t('skillMarket.placeholder_description')} />
          </Form.Item>
          <Form.Item name="tags" label={t('skillMarket.col_tags')}>
            <Select mode="tags" placeholder={t('skillMarket.placeholder_tags')} className="gaf-w-full" />
          </Form.Item>
          <Form.Item name="version" label={t('skillMarket.col_version')} initialValue="1.0">
            <Input placeholder="1.0" maxLength={50} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Review modal */}
      <Modal
        title={t('skillMarket.modal_review_title')}
        open={reviewModalOpen}
        onOk={handleReview}
        onCancel={() => setReviewModalOpen(false)}
        okText={t('skillMarket.btn_submit_review')}
        width={480}
      >
        {currentItem && (
          <div className="gaf-mb-lg">
            <Text strong>{currentItem.title}</Text>
            <div className="gaf-text-xs" style={{ color: token.colorTextTertiary }}>
              {currentItem.skill_name}
            </div>
          </div>
        )}
        <Form form={reviewForm} layout="vertical" preserve={false}>
          <Form.Item label={t('skillMarket.col_rating')} required>
            <Rate value={reviewRating} onChange={setReviewRating} />
          </Form.Item>
          <Form.Item name="comment" label={t('skillMarket.col_comment')}>
            <Input.TextArea rows={3} placeholder={t('skillMarket.placeholder_comment')} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Detail modal */}
      <Modal
        title={t('skillMarket.modal_detail_title')}
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={
          currentItem
            ? [
                <Button
                  key="import"
                  icon={<DownloadOutlined />}
                  onClick={() => {
                    handleImport(currentItem);
                  }}
                >
                  {t('skillMarket.btn_import')}
                </Button>,
                <Button
                  key="review"
                  icon={<StarOutlined />}
                  onClick={() => {
                    setDetailModalOpen(false);
                    openReview(currentItem);
                  }}
                >
                  {t('skillMarket.btn_review')}
                </Button>,
              ]
            : null
        }
        width={640}
      >
        {currentItem && (
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label={t('skillMarket.col_title')}>{currentItem.title}</Descriptions.Item>
            <Descriptions.Item label={t('skillMarket.col_skill')}>
              {currentItem.skill_name} v{currentItem.skill_version}
            </Descriptions.Item>
            <Descriptions.Item label={t('skillMarket.col_publisher')}>{currentItem.publisher_name}</Descriptions.Item>
            <Descriptions.Item label={t('skillMarket.col_version')}>{currentItem.version}</Descriptions.Item>
            <Descriptions.Item label={t('skillMarket.col_tags')}>
              {currentItem.tags?.map((tag) => (
                <Tag key={tag}>{tag}</Tag>
              ))}
            </Descriptions.Item>
            <Descriptions.Item label={t('skillMarket.col_description')}>
              {currentItem.description || '-'}
            </Descriptions.Item>
            <Descriptions.Item label={t('skillMarket.col_rating')}>
              <Space size={4}>
                <StarOutlined style={{ color: token.colorWarning }} />
                <span>{currentItem.rating_avg.toFixed(1)}</span>
                <Text type="secondary">({currentItem.rating_count})</Text>
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label={t('skillMarket.col_downloads')}>{currentItem.download_count}</Descriptions.Item>
            <Descriptions.Item label={t('skillMarket.col_published_at')}>
              {formatDate(currentItem.published_at)}
            </Descriptions.Item>
            <Descriptions.Item label={t('skillMarket.col_yaml')}>
              <Paragraph className="gaf-m-0 gaf-text-xs gaf-overflow-auto" style={{ maxHeight: 200 }} copyable>
                <pre className="gaf-m-0 gaf-whitespace-pre-wrap">{currentItem.skill_yaml_content}</pre>
              </Paragraph>
            </Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </PageWrapper>
  );
}

export default SkillMarketPage;
