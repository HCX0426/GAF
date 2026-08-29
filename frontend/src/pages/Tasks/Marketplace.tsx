import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Card,
  Select,
  Input,
  Button,
  Space,
  Row,
  Col,
  Tag,
  Rate,
  Typography,
  Modal,
  Form,
  App,
  Spin,
  Empty,
  theme as antTheme,
} from 'antd';
import { SearchOutlined, ImportOutlined, EyeOutlined, CloudUploadOutlined, DownloadOutlined } from '@ant-design/icons';
import {
  fetchTaskMarketItems,
  importTaskMarketItem,
  publishTaskToMarket,
  reviewTaskMarketItem,
  fetchTaskMarketItemDetail,
} from '@/api/skills';
import { listPipelines, type PipelineSummary } from '@/api/pipelines';
import { fetchGameProfiles } from '@/api/gameProfiles';
import { useTranslation } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';

interface MarketItem {
  id: number;
  publisher_name: string;
  pipeline_name: string;
  game_name: string;
  game_profile?: number | null;
  title: string;
  description: string;
  tags: string[];
  download_count: number;
  rating_avg: number;
  rating_count: number;
  version: string;
  created_at: string;
}

/** Tag options — i18n keys */
const TAG_OPTION_KEYS: Array<{ value: string; labelKey: string }> = [
  { value: '', labelKey: 'marketplace.tag_all' },
  { value: 'daily', labelKey: 'marketplace.tag_daily' },
  { value: 'weekly', labelKey: 'marketplace.tag_weekly' },
  { value: 'event', labelKey: 'marketplace.tag_event' },
  { value: 'farming', labelKey: 'marketplace.tag_farming' },
  { value: 'arena', labelKey: 'marketplace.tag_arena' },
  { value: 'gacha', labelKey: 'marketplace.tag_gacha' },
];

/** Sort options — i18n keys */
const SORT_OPTION_KEYS: Array<{ value: string; labelKey: string }> = [
  { value: 'downloads', labelKey: 'marketplace.sort_downloads' },
  { value: 'rating', labelKey: 'marketplace.sort_rating' },
  { value: 'newest', labelKey: 'marketplace.sort_newest' },
];

export function MarketplacePage() {
  const { token: designToken } = antTheme.useToken();
  const t = useTranslation();
  const [profiles, setProfiles] = useState<Array<{ id: number; game_name: string }>>([]);
  const gameOptions = useMemo(
    () => [{ value: '', label: t('marketplace.game_all') }, ...profiles.map((p) => ({ value: String(p.id), label: p.game_name }))],
    [profiles, t],
  );
  const tagOptions = useMemo(() => TAG_OPTION_KEYS.map((o) => ({ value: o.value, label: t(o.labelKey) })), [t]);
  const sortOptions = useMemo(() => SORT_OPTION_KEYS.map((o) => ({ value: o.value, label: t(o.labelKey) })), [t]);
  const [items, setItems] = useState<MarketItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [gameFilter, setGameFilter] = useState<string>('');
  const [tagFilter, setTagFilter] = useState<string>('');
  const [sortBy, setSortBy] = useState<string>('downloads');
  const [searchText, setSearchText] = useState('');
  const [publishModalOpen, setPublishModalOpen] = useState(false);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [detailItem, setDetailItem] = useState<MarketItem | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [pipelines, setPipelines] = useState<PipelineSummary[]>([]);
  const [pipelinesLoading, setPipelinesLoading] = useState(false);
  const [reviewRating, setReviewRating] = useState(0);
  const [reviewComment, setReviewComment] = useState('');
  const [submittingReview, setSubmittingReview] = useState(false);
  const { message } = App.useApp();
  const [publishForm] = Form.useForm();
  const [importing, setImporting] = useState<Set<number>>(new Set());

  /** Load marketplace items from real API */
  useEffect(() => {
    let cancelled = false;
    const loadItems = async () => {
      setLoading(true);
      try {
        const data = await fetchTaskMarketItems();
        if (!cancelled) {
          setItems(Array.isArray(data) ? data : []);
        }
      } catch {
        // API unavailable – keep empty list
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    loadItems();
    return () => {
      cancelled = true;
    };
  }, []);

  /** Load GameProfile options for the game filter + publish dropdown (P7: 去硬编码游戏选项) */
  useEffect(() => {
    let cancelled = false;
    fetchGameProfiles({ page_size: 200 })
      .then((res) => {
        if (!cancelled) setProfiles(res.results ?? []);
      })
      .catch(() => {
        /* profiles optional — publish still works with an empty selection */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /** Load user's pipelines when publish modal opens */
  useEffect(() => {
    if (!publishModalOpen) return;
    let cancelled = false;
    setPipelinesLoading(true);
    listPipelines({ page_size: 100 })
      .then((res) => {
        if (!cancelled) setPipelines(res.results ?? []);
      })
      .catch((err) => {
        // spec35 #12: surface fetch failure instead of swallowing silently.
        // Publish modal can still open; user just sees an empty pipeline list.
        if (!cancelled) {
          message.error(t('marketplace.load_pipelines_failed'));
          console.warn('[Marketplace] listPipelines failed:', err);
        }
      })
      .finally(() => {
        if (!cancelled) setPipelinesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [publishModalOpen]);

  /** Import a marketplace item into local account */
  const handleImport = useCallback(
    async (id: number) => {
      setImporting((prev) => new Set(prev).add(id));
      try {
        await importTaskMarketItem(id);
        message.success(t('marketplace.msg_import_success'));
        setItems((prev) =>
          prev.map((item) => (item.id === id ? { ...item, download_count: item.download_count + 1 } : item)),
        );
      } catch {
        message.error(t('marketplace.msg_import_failed'));
      } finally {
        setImporting((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      }
    },
    [t],
  );

  /** Fetch full detail and open detail modal */
  const handleViewDetail = useCallback(async (item: MarketItem) => {
    setDetailItem(item);
    setDetailModalOpen(true);
    setDetailLoading(true);
    try {
      const detail = await fetchTaskMarketItemDetail(item.id);
      setDetailItem(detail);
    } catch {
      // keep list-item data on error
    } finally {
      setDetailLoading(false);
    }
  }, []);

  /** Publish a pipeline to the marketplace */
  const handlePublish = useCallback(async () => {
    try {
      const values = await publishForm.validateFields();
      setPublishing(true);
      const published = await publishTaskToMarket({
        pipeline_id: values.pipeline,
        title: values.title,
        game_profile: values.game ? Number(values.game) : null,
        description: values.description,
        tags: values.tags || [],
      });
      setItems((prev) => [published, ...prev]);
      setPublishModalOpen(false);
      publishForm.resetFields();
      message.success(t('marketplace.msg_publish_success'));
    } catch (err: unknown) {
      if ((err as { errorFields?: unknown }).errorFields) return; // form validation failed
      message.error(t('marketplace.msg_publish_failed'));
    } finally {
      setPublishing(false);
    }
  }, [publishForm, t]);

  return (
    <PageWrapper>
      <Card size="small" className="gaf-mb-lg">
        <div className="gaf-toolbar gaf-w-full gaf-flex-between">
          <div className="gaf-toolbar-group">
            <Select
              value={gameFilter}
              onChange={setGameFilter}
              options={gameOptions}
              style={{ width: 130 }}
              size="small"
              placeholder={t('marketplace.placeholder_game')}
            />
            <Select
              value={tagFilter}
              onChange={setTagFilter}
              options={tagOptions}
              style={{ width: 130 }}
              size="small"
              placeholder={t('marketplace.placeholder_tag')}
            />
            <Select value={sortBy} onChange={setSortBy} options={sortOptions} style={{ width: 110 }} size="small" />
            <Input
              prefix={<SearchOutlined />}
              placeholder={t('marketplace.placeholder_search')}
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              className="gaf-w-md"
              size="small"
              allowClear
            />
          </div>
          <Button type="primary" size="small" icon={<CloudUploadOutlined />} onClick={() => setPublishModalOpen(true)}>
            {t('marketplace.btn_publish')}
          </Button>
        </div>
      </Card>

      <Spin spinning={loading}>
        {items.length === 0 ? (
          <Empty description={t('marketplace.empty')} style={{ marginTop: 60 }} />
        ) : (
          <Row gutter={[16, 16]}>
            {items.map((item) => (
              <Col key={item.id} xs={24} sm={12} lg={8}>
                <Card
                  hoverable
                  size="small"
                  actions={[
                    <Button
                      key="import"
                      type="link"
                      size="small"
                      icon={<DownloadOutlined />}
                      loading={importing.has(item.id)}
                      onClick={() => handleImport(item.id)}
                    >
                      {t('marketplace.btn_import')}
                    </Button>,
                    <Button
                      key="detail"
                      type="link"
                      size="small"
                      icon={<EyeOutlined />}
                      onClick={() => handleViewDetail(item)}
                    >
                      {t('marketplace.btn_detail')}
                    </Button>,
                  ]}
                >
                  <Card.Meta
                    title={
                      <div className="gaf-toolbar-group">
                        <Typography.Text ellipsis className="gaf-text-sm" style={{ maxWidth: 160 }}>
                          {item.title}
                        </Typography.Text>
                        <Tag color="blue" className="gaf-text-xxs">
                          {item.game_name}
                        </Tag>
                      </div>
                    }
                    description={
                      <div>
                        <div className="gaf-mb-xs">
                          <Rate disabled value={item.rating_avg} allowHalf className="gaf-text-xs" />
                          <Typography.Text
                            className="gaf-text-xxs gaf-ml-xs"
                            style={{ color: designToken.colorTextTertiary }}
                          >
                            ({item.rating_count})
                          </Typography.Text>
                        </div>
                        <Typography.Paragraph
                          ellipsis={{ rows: 2 }}
                          className="gaf-mb-sm gaf-text-xs"
                          style={{ color: designToken.colorTextSecondary }}
                        >
                          {item.description}
                        </Typography.Paragraph>
                        <div className="gaf-toolbar-group gaf-flex-wrap">
                          {item.tags.map((tag) => (
                            <Tag key={tag} color="green" className="gaf-text-xxs">
                              {tagOptions.find((to) => to.value === tag)?.label || tag}
                            </Tag>
                          ))}
                        </div>
                        <div className="gaf-mt-xs gaf-text-xxs" style={{ color: designToken.colorTextTertiary }}>
                          <ImportOutlined /> {item.download_count} · {item.publisher_name}
                        </div>
                      </div>
                    }
                  />
                </Card>
              </Col>
            ))}
          </Row>
        )}
      </Spin>

      <Modal
        title={t('marketplace.modal_detail_title')}
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button
            key="import"
            type="primary"
            icon={<DownloadOutlined />}
            onClick={() => {
              if (detailItem) {
                handleImport(detailItem.id);
                setDetailModalOpen(false);
              }
            }}
          >
            {t('marketplace.btn_import')}
          </Button>,
        ]}
        width={520}
      >
        <Spin spinning={detailLoading}>
          {detailItem && (
            <div>
              <Typography.Title level={5}>{detailItem.title}</Typography.Title>
              <div className="gaf-toolbar-group gaf-mb-sm">
                <Tag color="blue">{detailItem.game_name}</Tag>
                {detailItem.tags.map((tag) => (
                  <Tag key={tag} color="green">
                    {tag}
                  </Tag>
                ))}
              </div>
              <Typography.Paragraph>{detailItem.description}</Typography.Paragraph>
              <Space
                orientation="vertical"
                size={4}
                className="gaf-text-13"
                style={{ color: designToken.colorTextSecondary }}
              >
                <span>{t('marketplace.lbl_publisher', { name: detailItem.publisher_name })}</span>
                <span>{t('marketplace.lbl_version', { version: detailItem.version })}</span>
                <span>{t('marketplace.lbl_downloads', { count: detailItem.download_count })}</span>
                <span>
                  {t('marketplace.lbl_rating')}
                  <Rate disabled value={detailItem.rating_avg} allowHalf className="gaf-text-sm" />
                  {t('marketplace.lbl_reviews', { count: detailItem.rating_count })}
                </span>
                <span>{t('marketplace.lbl_publish_time', { time: detailItem.created_at })}</span>
              </Space>
              <div
                className="gaf-mt-lg"
                style={{ paddingTop: 16, borderTop: `1px solid ${designToken.colorBorderSecondary}` }}
              >
                <Typography.Text strong className="gaf-mb-sm gaf-display-block">
                  {t('marketplace.review_title')}
                </Typography.Text>
                <Space orientation="vertical" size={12} className="gaf-w-full">
                  <div>
                    <Typography.Text type="secondary" className="gaf-text-xs gaf-mr-sm">
                      {t('marketplace.lbl_rate')}
                    </Typography.Text>
                    <Rate allowHalf value={reviewRating} onChange={setReviewRating} />
                  </div>
                  <Input.TextArea
                    placeholder={t('marketplace.placeholder_review')}
                    rows={2}
                    maxLength={500}
                    value={reviewComment}
                    onChange={(e) => setReviewComment(e.target.value)}
                  />
                  <Button
                    type="primary"
                    size="small"
                    icon={<ImportOutlined />}
                    loading={submittingReview}
                    onClick={async () => {
                      if (reviewRating <= 0) {
                        message.warning(t('marketplace.msg_rate_required'));
                        return;
                      }
                      setSubmittingReview(true);
                      try {
                        await reviewTaskMarketItem(detailItem.id, reviewRating, reviewComment || undefined);
                        message.success(t('marketplace.msg_review_success'));
                        const updated = await fetchTaskMarketItemDetail(detailItem.id);
                        setDetailItem(updated);
                        setItems((prev) => prev.map((i) => (i.id === detailItem.id ? updated : i)));
                        setReviewRating(0);
                        setReviewComment('');
                      } catch {
                        message.error(t('marketplace.msg_review_failed'));
                      } finally {
                        setSubmittingReview(false);
                      }
                    }}
                  >
                    {t('marketplace.btn_submit_review')}
                  </Button>
                </Space>
              </div>
            </div>
          )}
        </Spin>
      </Modal>

      <Modal
        title={t('marketplace.modal_publish_title')}
        open={publishModalOpen}
        onOk={handlePublish}
        onCancel={() => {
          setPublishModalOpen(false);
          publishForm.resetFields();
        }}
        okText={t('marketplace.btn_publish_ok')}
        cancelText={t('marketplace.btn_cancel')}
        confirmLoading={publishing}
        width={520}
      >
        <div className="gaf-overflow-y-auto gaf-pr-sm" style={{ maxHeight: '60vh' }}>
          <Form form={publishForm} layout="vertical">
            <Form.Item
              name="pipeline"
              label={t('marketplace.lbl_pipeline')}
              rules={[{ required: true, message: t('marketplace.msg_pipeline_required') }]}
            >
              <Select
                placeholder={t('marketplace.placeholder_pipeline')}
                loading={pipelinesLoading}
                options={pipelines.map((p) => ({ value: p.id, label: `${p.name} (v${p.version})` }))}
                notFoundContent={pipelinesLoading ? <Spin size="small" /> : t('marketplace.no_pipeline')}
              />
            </Form.Item>
            <Form.Item
              name="title"
              label={t('marketplace.lbl_title')}
              rules={[{ required: true, message: t('marketplace.msg_title_required') }]}
            >
              <Input placeholder={t('marketplace.placeholder_title')} />
            </Form.Item>
            <Form.Item name="game" label={t('marketplace.lbl_game')}>
              <Select
                placeholder={t('marketplace.placeholder_game_select')}
                options={gameOptions.filter((g) => g.value !== '')}
              />
            </Form.Item>
            <Form.Item
              name="description"
              label={t('marketplace.lbl_description')}
              rules={[{ required: true, message: t('marketplace.msg_description_required') }]}
            >
              <Input.TextArea rows={3} placeholder={t('marketplace.placeholder_description')} />
            </Form.Item>
            <Form.Item name="screenshot" label={t('marketplace.lbl_screenshot')}>
              <Input placeholder={t('marketplace.placeholder_screenshot')} />
            </Form.Item>
            <Form.Item name="tags" label={t('marketplace.lbl_tags')}>
              <Select
                mode="multiple"
                placeholder={t('marketplace.placeholder_tags')}
                options={tagOptions.filter((to) => to.value !== '')}
              />
            </Form.Item>
          </Form>
        </div>
      </Modal>
    </PageWrapper>
  );
}

export default MarketplacePage;
