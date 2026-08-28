/**
 * Template gallery component
 * Displays template image grid from resource packs with filtering, preview and status management
 * Integrates P-014 Tag System for server-managed tags
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import {
  Image,
  Card,
  Select,
  Switch,
  Modal,
  Tag,
  Row,
  Col,
  Spin,
  Empty,
  Typography,
  Button,
  Upload,
  Checkbox,
  Progress,
  message,
  Result,
  Alert,
  Popconfirm,
} from 'antd';
import {
  UploadOutlined,
  ReloadOutlined,
  TagsOutlined,
  InboxOutlined,
  DeleteOutlined,
  CheckSquareOutlined,
  BorderOutlined,
} from '@ant-design/icons';
import { theme as antTheme } from 'antd';
import TagPicker from '@/components/Common/TagPicker';
import {
  fetchResourcePacks,
  fetchTags,
  fetchTemplates,
  updateTemplate,
  deleteTemplate,
  checkTemplateReferences,
  uploadTemplate,
  batchImportTemplates,
  type Tag as ServerTag,
  type Template as TemplateItem,
} from '@/api/resources';
import type { ResourcePack } from '@/types/models';
import { useTranslation } from '@/i18n';

const { Text } = Typography;

interface TemplateGalleryProps {
  packId?: number;
}

export function TemplateGallery({ packId }: TemplateGalleryProps) {
  const { token: antdToken } = antTheme.useToken();
  const t = useTranslation();
  const [templates, setTemplates] = useState<TemplateItem[]>([]);
  const [packs, setPacks] = useState<ResourcePack[]>([]);
  const [selectedPackId, setSelectedPackId] = useState<number | undefined>(packId);
  const [showInvalidOnly, setShowInvalidOnly] = useState(false);
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [previewImage, setPreviewImage] = useState<string | null>(null);

  /** Template ROI preview state - stores full template data for overlay rendering */
  const [previewTemplate, setPreviewTemplate] = useState<TemplateItem | null>(null);
  /** Canvas ref for ROI overlay drawing */
  const roiCanvasRef = useRef<HTMLCanvasElement>(null);
  /** Image element ref for natural dimension detection */
  const previewImgRef = useRef<HTMLImageElement>(null);

  /** Batch import states */
  const [batchImportOpen, setBatchImportOpen] = useState(false);
  const [batchUploading, setUploading] = useState(false);
  const [batchProgress, setBatchProgress] = useState(0);
  const [batchResult, setBatchResult] = useState<{ imported: number; skipped: number; packName: string } | null>(null);

  /** Reference check state for before-disable confirmation */
  const [refCheckModal, setRefCheckModal] = useState<{
    open: boolean;
    templateId: number;
    templateName: string;
    refs: Record<string, number> | null;
  }>({
    open: false,
    templateId: 0,
    templateName: '',
    refs: null,
  });

  /** Batch selection state */
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  /** Server-side tag list for display */
  const [serverTags, setServerTags] = useState<ServerTag[]>([]);

  useEffect(() => {
    loadPacks();
    loadServerTags();
  }, []);

  useEffect(() => {
    if (selectedPackId !== undefined) {
      loadTemplates(selectedPackId);
    }
  }, [selectedPackId]);

  /** Load resource pack list */
  const loadPacks = async () => {
    try {
      const res = await fetchResourcePacks({ page: 1, page_size: 100 });
      setPacks(res.results || []);
    } catch (err) {
      console.error('Template gallery load failed:', err);
    }
  };

  /** Load server-side tag list */
  const loadServerTags = async () => {
    try {
      const data = await fetchTags();
      setServerTags(data);
    } catch {
      // pass - tags are optional
    }
  };

  /** Load templates from the selected pack */
  const loadTemplates = async (pid: number) => {
    setLoading(true);
    try {
      const arr = await fetchTemplates({ pack_id: pid });
      setTemplates(arr);
    } catch (err) {
      console.error('Template gallery load failed:', err);
    } finally {
      setLoading(false);
    }
  };

  /** Check template references before toggling valid status */
  const checkReferences = async (templateId: number, templateName: string) => {
    try {
      const data = await checkTemplateReferences(templateId);
      if (data.has_references) {
        setRefCheckModal({ open: true, templateId, templateName, refs: data.references });
      } else {
        executeToggleValid(templateId);
      }
    } catch {
      executeToggleValid(templateId);
    }
  };

  /** Execute the actual toggle after reference check (or skip if no references) */
  const executeToggleValid = async (templateId: number) => {
    const template = templates.find((t) => t.id === templateId);
    const isActive = template?.is_active ?? true;
    try {
      await updateTemplate(templateId, { is_active: !isActive });
      setTemplates((prev) => prev.map((t) => (t.id === templateId ? { ...t, is_active: !isActive } : t)));
    } catch (err) {
      console.error('Template gallery load failed:', err);
    }
  };

  /** Confirm disable despite having references */
  const confirmDisableWithRefs = () => {
    executeToggleValid(refCheckModal.templateId);
    setRefCheckModal({ open: false, templateId: 0, templateName: '', refs: null });
  };

  /** Toggle single template selection for batch operations */
  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  /** Select all visible templates */
  const selectAll = () => {
    setSelectedIds(new Set(tagFilteredTemplates.map((t) => t.id)));
  };

  /** Deselect all templates */
  const deselectAll = () => {
    setSelectedIds(new Set());
  };

  /** Batch delete selected templates with confirmation */
  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) return;
    try {
      await Promise.all([...selectedIds].map((id) => deleteTemplate(id)));
      setTemplates((prev) => prev.filter((t) => !selectedIds.has(t.id)));
      message.success(t('resources.msg_batch_delete_success', { count: selectedIds.size }));
      setSelectedIds(new Set());
      if (selectedPackId !== undefined) loadTemplates(selectedPackId);
    } catch {
      message.error(t('resources.msg_batch_delete_failed'));
    }
  };

  /** Batch toggle valid/invalid status for selected templates */
  const handleBatchToggleValid = async (targetValid: boolean) => {
    if (selectedIds.size === 0) return;
    try {
      await Promise.all([...selectedIds].map((id) => updateTemplate(id, { is_valid: targetValid })));
      setTemplates((prev) => prev.map((t) => (selectedIds.has(t.id) ? { ...t, is_valid: targetValid } : t)));
      message.success(
        targetValid
          ? t('resources.msg_batch_enable_success', { count: selectedIds.size })
          : t('resources.msg_batch_disable_success', { count: selectedIds.size }),
      );
      setSelectedIds(new Set());
    } catch {
      message.error(t('resources.msg_batch_operation_failed'));
    }
  };

  /** Open image preview modal with ROI overlay support */
  const handlePreview = useCallback((template: TemplateItem) => {
    setPreviewImage(template.image_url);
    setPreviewTemplate(template);
  }, []);

  /** Close image preview modal and reset ROI overlay state */
  const handleClosePreview = useCallback(() => {
    setPreviewImage(null);
    setPreviewTemplate(null);
  }, []);

  /**
   * Parse region_info string or region array into ROI coordinates
   * Supports formats: "[x, y, w, h]", "x,y,w,h", or array [x, y, w, h]
   * @returns { x, y, width, height } or null if parsing fails
   */
  const parseROI = useCallback(
    (regionInfo?: string): { x: number; y: number; width: number; height: number } | null => {
      if (!regionInfo) return null;

      try {
        const trimmed = regionInfo.trim();
        if (trimmed.startsWith('[')) {
          const arr = JSON.parse(trimmed);
          if (Array.isArray(arr) && arr.length >= 4) {
            return { x: arr[0], y: arr[1], width: arr[2], height: arr[3] };
          }
        }

        const parts = trimmed.split(/[,\s]+/).map(Number);
        if (parts.length >= 4 && parts.every((n) => !isNaN(n))) {
          return { x: parts[0], y: parts[1], width: parts[2], height: parts[3] };
        }
      } catch {
        // pass - invalid format
      }

      return null;
    },
    [],
  );

  /** Draw ROI overlay rectangle on canvas when preview image loads */
  useEffect(() => {
    if (!previewTemplate || !roiCanvasRef.current || !previewImgRef.current) return;

    const canvas = roiCanvasRef.current;
    const img = previewImgRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const roi = parseROI(previewTemplate.region_info);
    if (!roi) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      return;
    }

    const drawOverlay = () => {
      canvas.width = img.naturalWidth || img.width;
      canvas.height = img.naturalHeight || img.clientHeight;

      const scaleX = canvas.width / img.clientWidth;
      const scaleY = canvas.height / img.clientHeight;

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const rx = roi.x * scaleX;
      const ry = roi.y * scaleY;
      const rw = roi.width * scaleX;
      const rh = roi.height * scaleY;

      ctx.strokeStyle = '#00ff00';
      ctx.lineWidth = 3;
      ctx.fillStyle = 'rgba(0, 255, 0, 0.12)';
      ctx.fillRect(rx, ry, rw, rh);
      ctx.strokeRect(rx, ry, rw, rh);

      ctx.font = 'bold 14px monospace';
      const label = `ROI: ${Math.round(roi.width)}x${Math.round(roi.height)} @ (${Math.round(roi.x)}, ${Math.round(roi.y)})`;
      const textWidth = ctx.measureText(label).width;
      ctx.fillStyle = 'rgba(0, 0, 0, 0.75)';
      ctx.fillRect(rx, ry - 22, textWidth + 10, 20);
      ctx.fillStyle = '#00ff00';
      ctx.fillText(label, rx + 5, ry - 7);

      const threshold = previewTemplate.match_threshold || 0.8;
      const thresholdLabel = `Threshold: ${(threshold * 100).toFixed(0)}%`;
      const tw = ctx.measureText(thresholdLabel).width;
      ctx.fillStyle = 'rgba(0, 0, 0, 0.75)';
      ctx.fillRect(rx, ry + rh + 2, tw + 10, 20);
      ctx.fillStyle = threshold >= 0.9 ? '#00ff00' : threshold >= 0.7 ? '#faad14' : '#ff4d4f';
      ctx.fillText(thresholdLabel, rx + 5, ry + rh + 17);
    };

    if (img.complete && img.naturalWidth > 0) {
      drawOverlay();
    } else {
      img.onload = drawOverlay;
    }
  }, [previewTemplate, parseROI]);

  /** Get tag color based on threshold value */
  const getThresholdColor = (threshold: number): string => {
    if (threshold >= 0.9) return 'green';
    if (threshold >= 0.7) return 'blue';
    if (threshold >= 0.5) return 'orange';
    return 'red';
  };

  /** Handle single template file upload */
  const handleUploadTemplate = async (file: File) => {
    try {
      await uploadTemplate(file, selectedPackId);
      if (selectedPackId !== undefined) {
        loadTemplates(selectedPackId);
      }
    } catch (err) {
      console.error('Template gallery load failed:', err);
    }
    return false;
  };

  /** Handle ZIP batch import to selected resource pack */
  const handleBatchImport = async (file: File) => {
    if (selectedPackId === undefined) {
      message.warning(t('resources.msg_select_pack_first'));
      return false;
    }

    setUploading(true);
    setBatchProgress(30);
    setBatchResult(null);

    try {
      setBatchProgress(60);

      const data = await batchImportTemplates(file, selectedPackId);

      setBatchProgress(90);
      setBatchProgress(100);
      setBatchResult({ imported: data.imported, skipped: data.skipped, packName: data.pack_name });
      message.success(t('resources.msg_batch_import_success', { count: data.imported }));

      if (selectedPackId !== undefined) {
        loadTemplates(selectedPackId);
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      if (detail) {
        message.error(detail || t('resources.msg_batch_import_failed'));
      } else {
        message.error(t('resources.msg_network_error'));
      }
    } finally {
      setUploading(false);
    }

    return false;
  };

  /** Close batch import modal and reset state */
  const closeBatchImport = () => {
    setBatchImportOpen(false);
    setBatchProgress(0);
    setBatchResult(null);
  };

  const filteredTemplates = showInvalidOnly ? templates.filter((t) => !t.is_active) : templates;

  /** Apply server-side tag filtering */
  const tagFilteredTemplates =
    selectedTagIds.length > 0
      ? filteredTemplates.filter((t) => selectedTagIds.every((tagId) => t.tag_ids?.includes(tagId)))
      : filteredTemplates;

  /** Resolve a server tag object by ID */
  const getTagById = (id: number): ServerTag | undefined => {
    return serverTags.find((t) => t.id === id);
  };

  return (
    <div>
      <Row gutter={16} className="gaf-mb-lg" align="middle">
        <Col>
          <Select
            placeholder={t('resources.placeholder_select_pack')}
            style={{ width: 240 }}
            value={selectedPackId}
            onChange={(val) => setSelectedPackId(val)}
            options={packs.map((p) => ({ label: `${p.name} v${p.version || '1.0'}`, value: p.id }))}
            allowClear
          />
        </Col>
        <Col>
          <Switch
            checkedChildren={t('resources.switch_invalid_only')}
            unCheckedChildren={t('resources.switch_show_all')}
            checked={showInvalidOnly}
            onChange={(checked) => setShowInvalidOnly(checked)}
          />
        </Col>
        <Col>
          <div className="gaf-toolbar-group">
            <TagsOutlined className="gaf-mr-xs" style={{ color: antdToken.colorTextTertiary }} />
            <TagPicker value={selectedTagIds} onChange={setSelectedTagIds} multiple />
            {selectedTagIds.length > 0 && (
              <Button type="link" size="small" onClick={() => setSelectedTagIds([])} className="gaf-p-0 gaf-text-xs">
                {t('resources.btn_clear')}
              </Button>
            )}
          </div>
        </Col>
        <Col>
          <Text type="secondary">
            {t('resources.label_template_count_display', {
              filtered: tagFilteredTemplates.length,
              total: templates.length,
            })}
          </Text>
        </Col>
        <Col flex="auto" />
        <Col>
          <div className="gaf-toolbar-group">
            <Upload beforeUpload={handleUploadTemplate} showUploadList={false} accept="image/*">
              <Button icon={<UploadOutlined />} size="small">
                {t('resources.btn_upload_template')}
              </Button>
            </Upload>
            <Button icon={<InboxOutlined />} size="small" onClick={() => setBatchImportOpen(true)}>
              {t('resources.btn_batch_import')}
            </Button>
            <Button
              icon={<ReloadOutlined />}
              size="small"
              onClick={() => selectedPackId !== undefined && loadTemplates(selectedPackId)}
            >
              {t('resources.btn_refresh')}
            </Button>
            {selectedIds.size > 0 && (
              <>
                <Button icon={<CheckSquareOutlined />} size="small" onClick={selectAll}>
                  {t('resources.btn_select_all')}
                </Button>
                <Button icon={<BorderOutlined />} size="small" onClick={deselectAll}>
                  {t('resources.btn_cancel')}
                </Button>
                <Popconfirm
                  title={t('resources.confirm_batch_delete', { count: selectedIds.size })}
                  description={t('resources.confirm_batch_delete_desc')}
                  onConfirm={handleBatchDelete}
                  okText={t('resources.btn_confirm_delete')}
                  cancelText={t('resources.btn_cancel')}
                  okButtonProps={{ danger: true }}
                >
                  <Button icon={<DeleteOutlined />} size="small" danger>
                    {t('resources.btn_delete_with_count', { count: selectedIds.size })}
                  </Button>
                </Popconfirm>
                <Button size="small" onClick={() => handleBatchToggleValid(true)}>
                  {t('resources.btn_batch_enable')}
                </Button>
                <Button size="small" onClick={() => handleBatchToggleValid(false)}>
                  {t('resources.btn_batch_disable')}
                </Button>
              </>
            )}
          </div>
        </Col>
      </Row>

      <Spin spinning={loading}>
        {tagFilteredTemplates.length === 0 && !loading ? (
          <Empty description={t('resources.empty_no_templates')} />
        ) : (
          <Row gutter={[16, 16]}>
            {tagFilteredTemplates.map((template) => (
              <Col xs={24} sm={12} md={8} lg={6} key={template.id}>
                <Card
                  hoverable
                  size="small"
                  style={{
                    border: selectedIds.has(template.id) ? '2px solid #1890ff' : undefined,
                    opacity: selectedIds.has(template.id) ? 0.9 : 1,
                    transition: 'border 0.2s, opacity 0.2s',
                  }}
                  cover={
                    <button
                      type="button"
                      className="gaf-reset-button gaf-position-relative"
                      style={{ height: 160, overflow: 'hidden' }}
                      onClick={() => handlePreview(template)}
                      aria-label={t('resources.aria_preview_template', { name: template.name })}
                    >
                      <Checkbox
                        checked={selectedIds.has(template.id)}
                        onChange={(e) => {
                          e.stopPropagation();
                          toggleSelect(template.id);
                        }}
                        className="gaf-position-absolute"
                        style={{ top: 8, left: 8, zIndex: 1 }}
                      />
                      <Image
                        src={template.thumbnail_url}
                        alt={template.name}
                        preview={false}
                        className="gaf-w-full gaf-h-full"
                        style={{ objectFit: 'cover' }}
                        fallback="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjE2MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjZGRkIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGRvbWluYW50LWJhc2VsaW5lPSJtaWRkbGUiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGZpbGw9IiNhYWEiIGZvbnQtc2l6ZT0iMTQiPk5vIEltYWdlPC90ZXh0Pjwvc3ZnPg=="
                      />
                    </button>
                  }
                  actions={[
                    <Switch
                      key="valid"
                      size="small"
                      checked={template.is_active}
                      onChange={() => checkReferences(template.id, template.name)}
                    />,
                  ]}
                >
                  <Card.Meta
                    title={
                      <Text ellipsis style={{ maxWidth: '100%' }}>
                        {template.name}
                      </Text>
                    }
                    description={
                      <div>
                        {template.tag_ids && template.tag_ids.length > 0 && (
                          <div className="gaf-mb-xs">
                            {template.tag_ids.map((tagId) => {
                              const tag = getTagById(tagId);
                              return tag ? (
                                <Tag
                                  key={tagId}
                                  color={tag.color}
                                  style={{ fontSize: 10, lineHeight: '16px', marginRight: 2 }}
                                >
                                  {tag.name}
                                </Tag>
                              ) : null;
                            })}
                          </div>
                        )}
                        <Tag color={getThresholdColor(template.match_threshold ?? 0)}>
                          {t('resources.label_threshold', {
                            value: ((template.match_threshold ?? 0) * 100).toFixed(0),
                          })}
                        </Tag>
                        <br />
                        <Text type="secondary" className="gaf-text-xs">
                          {template.region_info}
                        </Text>
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
        open={!!previewImage}
        title={
          <span>
            {t('resources.title_template_preview')}
            {previewTemplate?.region_info && (
              <Tag color="green" className="gaf-ml-sm">
                {t('resources.tag_roi_visualization')}
              </Tag>
            )}
          </span>
        }
        footer={null}
        onCancel={handleClosePreview}
        width={900}
        centered
      >
        <div className="gaf-position-relative" style={{ display: 'inline-block', maxWidth: '100%' }}>
          <img
            ref={previewImgRef}
            src={previewImage || ''}
            alt={previewTemplate?.name || 'Preview'}
            width={900}
            height={600}
            loading="lazy"
            className="gaf-w-full gaf-display-block"
          />
          <canvas
            ref={roiCanvasRef}
            className="gaf-w-full gaf-h-full gaf-position-absolute"
            style={{ top: 0, left: 0, pointerEvents: 'none' }}
          />
        </div>

        {previewTemplate && (
          <div className="gaf-mt-lg">
            <Row gutter={[16, 8]}>
              <Col span={12}>
                <Text strong>{t('resources.label_template_name')}</Text>
                <Text>{previewTemplate.name}</Text>
              </Col>
              <Col span={12}>
                <Text strong>{t('resources.label_match_threshold')}</Text>
                <Tag color={getThresholdColor(previewTemplate.match_threshold ?? 0)}>
                  {((previewTemplate.match_threshold ?? 0) * 100).toFixed(0)}%
                </Tag>
              </Col>
              <Col span={12}>
                <Text strong>{t('resources.label_status')}</Text>
                <Switch
                  size="small"
                  checked={previewTemplate.is_active}
                  onChange={() => checkReferences(previewTemplate.id, previewTemplate.name)}
                />
              </Col>
              <Col span={12}>
                <Text strong>{t('resources.label_region_info')}</Text>
                <Text code>{previewTemplate.region_info || t('resources.label_not_set')}</Text>
              </Col>
              {previewTemplate.tag_ids && previewTemplate.tag_ids.length > 0 && (
                <Col span={24}>
                  <Text strong>{t('resources.label_tags')}</Text>
                  {previewTemplate.tag_ids.map((tagId) => {
                    const tag = getTagById(tagId);
                    return tag ? (
                      <Tag key={tagId} color={tag.color} className="gaf-ml-xs">
                        {tag.name}
                      </Tag>
                    ) : null;
                  })}
                </Col>
              )}
            </Row>

            {!parseROI(previewTemplate.region_info) && previewTemplate.region_info && (
              <Alert
                title={t('resources.alert_roi_parse_failed')}
                description={t('resources.alert_roi_parse_failed_desc', { info: previewTemplate.region_info })}
                type="warning"
                showIcon
                className="gaf-mt-md"
              />
            )}
          </div>
        )}
      </Modal>

      {/* Batch Import Modal */}
      <Modal
        title={t('resources.title_batch_import')}
        open={batchImportOpen}
        onCancel={closeBatchImport}
        footer={null}
        width={520}
        destroyOnHidden
      >
        {selectedPackId === undefined ? (
          <Empty description={t('resources.empty_select_pack_first')} />
        ) : (
          <div>
            <div className="gaf-mb-lg">
              <Text type="secondary">
                {t('resources.label_target_pack')}
                <Text strong>{packs.find((p) => p.id === selectedPackId)?.name}</Text>
              </Text>
            </div>

            {!batchResult ? (
              <Upload.Dragger
                beforeUpload={handleBatchImport}
                showUploadList={false}
                accept=".zip"
                multiple={false}
                disabled={batchUploading}
              >
                <p className="ant-upload-drag-icon">
                  <InboxOutlined style={{ fontSize: 48, color: antdToken.colorPrimary }} />
                </p>
                <p className="ant-upload-text">{t('resources.upload_drag_text')}</p>
                <p className="ant-upload-hint">{t('resources.upload_drag_hint')}</p>
              </Upload.Dragger>
            ) : null}

            {batchUploading && (
              <div className="gaf-mt-lg">
                <Progress percent={batchProgress} status="active" strokeColor={{ from: '#108ee9', to: '#87d068' }} />
                <Text type="secondary" className="gaf-text-xs">
                  {t('resources.msg_importing')}
                </Text>
              </div>
            )}

            {batchResult && (
              <div className="gaf-mt-lg">
                <Result
                  status="success"
                  title={t('resources.title_import_complete')}
                  subTitle={t('resources.msg_import_complete_desc', {
                    imported: batchResult.imported,
                    skipped: batchResult.skipped,
                  })}
                  extra={[
                    <Button key="done" type="primary" onClick={closeBatchImport}>
                      {t('resources.btn_done')}
                    </Button>,
                  ]}
                />
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* Reference Check Confirmation Modal */}
      <Modal
        title={t('resources.title_ref_check')}
        open={refCheckModal.open}
        onCancel={() => setRefCheckModal({ open: false, templateId: 0, templateName: '', refs: null })}
        width={480}
        footer={[
          <Button
            key="cancel"
            onClick={() => setRefCheckModal({ open: false, templateId: 0, templateName: '', refs: null })}
          >
            {t('resources.btn_cancel')}
          </Button>,
          <Button key="confirm" type="primary" danger onClick={confirmDisableWithRefs}>
            {t('resources.btn_confirm_disable')}
          </Button>,
        ]}
      >
        <Alert
          type="warning"
          showIcon
          title={t('resources.alert_ref_check_title', { name: refCheckModal.templateName })}
          description={t('resources.alert_ref_check_desc')}
          className="gaf-mb-lg"
        />
        {refCheckModal.refs && (
          <div>
            {refCheckModal.refs.annotations > 0 && (
              <div className="gaf-mb-sm">
                <Tag color="orange">{t('resources.tag_annotations')}</Tag>
                <Text type="secondary">
                  {t('resources.msg_annotation_refs', { count: refCheckModal.refs.annotations })}
                </Text>
              </div>
            )}
            {(() => {
              const eff = (refCheckModal.refs as Record<string, number>)?.effectiveness_records;
              return eff > 0 ? (
                <div className="gaf-mb-sm">
                  <Tag color="red">{t('resources.tag_effectiveness')}</Tag>
                  <Text type="secondary">{t('resources.msg_effectiveness_refs', { count: eff })}</Text>
                </div>
              ) : null;
            })()}
          </div>
        )}
        <Text type="secondary" className="gaf-mt-md gaf-text-xs gaf-display-block">
          {t('resources.msg_confirm_disable_hint')}
        </Text>
      </Modal>
    </div>
  );
}

export default TemplateGallery;
