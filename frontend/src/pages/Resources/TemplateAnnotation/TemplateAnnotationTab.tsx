/**
 * R37-P1 C5 — Template Annotation Tab (persistence)
 *
 * Tab 2 of TemplateAnnotationPage. Lets the user pick a ResourcePack +
 * Template, draw rect annotations on the template image, and persist them
 * via /api/v2/resources/annotations/. Annotations are reloaded from the
 * backend whenever the selected Template changes.
 *
 * Scope note: only `rect` annotations are supported in this minimal version.
 * Polygon/line/point tools live in Tab 1 (live annotation). Full device
 * operation (click/input/OCR) integration is deferred to R37-P2 per plan §C5.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  App,
  Button,
  Card,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Tooltip,
  Typography,
  Tag,
  Descriptions,
  theme as antTheme,
} from 'antd';
import { DeleteOutlined, DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import GafCanvasOverlay from '@/components/Canvas/GafCanvasOverlay';
import type { Annotation as CanvasAnnotation } from '@/components/Canvas/GafCanvasOverlay';
import { useCanvasAnnotation } from '@/hooks/useCanvasAnnotation';
import { useTranslation } from '@/i18n';
import {
  fetchResourcePacks,
  fetchTemplateAnnotations,
  createTemplateAnnotation,
  deleteTemplateAnnotation,
  batchDeleteTemplateAnnotations,
  fetchTemplates,
  fetchTemplateImageBlob,
  type Template as TemplateItem,
} from '@/api/resources';
import type { ResourcePack } from '@/types/models';

const CANVAS_WIDTH = 800;
const CANVAS_HEIGHT = 600;

export function TemplateAnnotationTab() {
  const t = useTranslation();
  const { message } = App.useApp();
  const { token } = antTheme.useToken();
  const { annotations, addAnnotation, removeAnnotation, selectAnnotation, selectedAnnotation, clearAnnotations } =
    useCanvasAnnotation();

  const [packs, setPacks] = useState<ResourcePack[]>([]);
  const [selectedPackId, setSelectedPackId] = useState<number | undefined>();
  const [templates, setTemplates] = useState<TemplateItem[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | undefined>();
  const [selectedTemplate, setSelectedTemplate] = useState<TemplateItem | null>(null);
  /** Object URL for the selected template image.
   *  Template files endpoint requires JWT auth, so we fetch the image as a
   *  blob via the authenticated axios client and convert to an object URL
   *  (browser `<img>` cannot send Authorization headers). */
  const [templateImageUrl, setTemplateImageUrl] = useState<string | undefined>();
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [loadingAnnotations, setLoadingAnnotations] = useState(false);
  const [savingAnnotation, setSavingAnnotation] = useState(false);

  /** Drawing state — rect drag only */
  const [drawStart, setDrawStart] = useState<{ x: number; y: number } | null>(null);
  const [drawRect, setDrawRect] = useState<{ x: number; y: number; w: number; h: number } | null>(null);
  const [pendingSave, setPendingSave] = useState<CanvasAnnotation | null>(null);
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [labelForm] = Form.useForm();
  /** Map canvas annotation id → backend TemplateAnnotation id (for delete). */
  const [annotationIdMap, setAnnotationIdMap] = useState<Map<string, number>>(new Map());

  /** Load resource pack list once. */
  useEffect(() => {
    fetchResourcePacks({ page: 1, page_size: 100 })
      .then((res) => {
        setPacks(res.results || []);
        if (res.results && res.results.length > 0) {
          setSelectedPackId(res.results[0].id);
        }
      })
      .catch((err) => {
        // spec35 #12: surfaced by empty state. Log the failure so backend
        // pack-list drift is debuggable.
        console.warn('[TemplateAnnotationTab] fetchResourcePacks failed:', err);
      });
  }, []);

  /** Load templates when pack changes. */
  useEffect(() => {
    if (!selectedPackId) {
      setTemplates([]);
      return;
    }
    setLoadingTemplates(true);
    fetchTemplates({ pack_id: selectedPackId })
      .then((arr) => {
        setTemplates(arr);
        if (arr.length > 0) {
          setSelectedTemplateId(arr[0].id);
        } else {
          setSelectedTemplateId(undefined);
          setSelectedTemplate(null);
        }
      })
      .catch((err) => {
        // spec35 #12: surface fetch failure instead of swallowing silently.
        // Empty-state UI still renders; user gets a toast explaining why.
        message.error(t('templateAnnotation.load_templates_failed'));
        console.warn('[TemplateAnnotationTab] fetchTemplates failed:', err);
        setTemplates([]);
      })
      .finally(() => {
        setLoadingTemplates(false);
      });
  }, [selectedPackId]);

  /** Update selectedTemplate object when templateId changes. */
  useEffect(() => {
    if (!selectedTemplateId) {
      setSelectedTemplate(null);
      return;
    }
    const found = templates.find((tpl) => tpl.id === selectedTemplateId) || null;
    setSelectedTemplate(found);
  }, [selectedTemplateId, templates]);

  /** Fetch template image as authenticated blob → object URL.
   *  The template files endpoint (IsAuthenticated) cannot be hit by a bare
   *  `<img src=...>` because the browser will not attach the JWT. We fetch
   *  via the API module (which injects the Authorization header) and
   *  convert the response blob into an object URL that GafCanvasOverlay can
   *  load. The previous object URL is revoked to avoid leaking blob memory.
   *
   *  Note: `image_url` is stored as an absolute path (`/api/v2/resources/...`)
   *  but the axios client already has `baseURL='/api/v2'`, so the API module
   *  strips the prefix to avoid a doubled `/api/v2/api/v2/...` path. */
  useEffect(() => {
    if (!selectedTemplate?.image_url) {
      setTemplateImageUrl(undefined);
      return;
    }
    let revoked = false;
    let createdUrl: string | null = null;
    fetchTemplateImageBlob(selectedTemplate.image_url)
      .then((blob) => {
        if (revoked) return;
        createdUrl = URL.createObjectURL(blob);
        setTemplateImageUrl(createdUrl);
      })
      .catch(() => {
        if (!revoked) setTemplateImageUrl(undefined);
      });
    return () => {
      revoked = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [selectedTemplate]);

  /** Load persisted annotations when template changes. */
  const loadAnnotations = useCallback(
    async (templateId: number) => {
      setLoadingAnnotations(true);
      try {
        const res = await fetchTemplateAnnotations(templateId, { page: 1, page_size: 200 });
        clearAnnotations();
        const idMap = new Map<string, number>();
        for (const ann of res.results) {
          const points = Array.isArray(ann.points) ? ann.points : [];
          // points format: [x, y, w, h] for rect
          if (points.length >= 4) {
            const canvasAnn: CanvasAnnotation = {
              id: `tmpl_ann_${ann.id}`,
              type: 'rect',
              x: points[0],
              y: points[1],
              width: points[2],
              height: points[3],
              color: token.colorSuccess,
              label: ann.label || undefined,
            };
            addAnnotation(canvasAnn);
            idMap.set(canvasAnn.id, ann.id);
          }
        }
        setAnnotationIdMap(idMap);
      } catch {
        message.error(t('templateAnnotation.msg_load_failed'));
      } finally {
        setLoadingAnnotations(false);
      }
    },
    [addAnnotation, clearAnnotations, message, t],
  );

  useEffect(() => {
    if (selectedTemplateId) {
      loadAnnotations(selectedTemplateId);
    } else {
      clearAnnotations();
      setAnnotationIdMap(new Map());
    }
  }, [selectedTemplateId, loadAnnotations, clearAnnotations]);

  /** Drawing handlers (rect only). */
  const getCanvasCoords = useCallback((e: React.MouseEvent): { x: number; y: number } => {
    const target = e.currentTarget as HTMLDivElement;
    const rect = target.getBoundingClientRect();
    // Scale to canvas coordinates (canvas is rendered at CANVAS_WIDTH x CANVAS_HEIGHT).
    const scaleX = CANVAS_WIDTH / rect.width;
    const scaleY = CANVAS_HEIGHT / rect.height;
    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top) * scaleY,
    };
  }, []);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (!selectedTemplate) return;
      const coords = getCanvasCoords(e);
      setDrawStart(coords);
      setDrawRect({ x: coords.x, y: coords.y, w: 0, h: 0 });
    },
    [selectedTemplate, getCanvasCoords],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!drawStart) return;
      const coords = getCanvasCoords(e);
      const x = Math.min(drawStart.x, coords.x);
      const y = Math.min(drawStart.y, coords.y);
      const w = Math.abs(coords.x - drawStart.x);
      const h = Math.abs(coords.y - drawStart.y);
      setDrawRect({ x, y, w, h });
    },
    [drawStart, getCanvasCoords],
  );

  const handleMouseUp = useCallback(() => {
    if (!drawRect || drawRect.w < 5 || drawRect.h < 5) {
      setDrawStart(null);
      setDrawRect(null);
      return;
    }
    const newAnn: CanvasAnnotation = {
      id: `pending_${Date.now()}`,
      type: 'rect',
      x: drawRect.x,
      y: drawRect.y,
      width: drawRect.w,
      height: drawRect.h,
      color: token.colorSuccess,
    };
    setPendingSave(newAnn);
    setSaveModalOpen(true);
    labelForm.resetFields();
    setDrawStart(null);
    setDrawRect(null);
  }, [drawRect, labelForm]);

  /** Save annotation via API. */
  const handleSaveAnnotation = useCallback(async () => {
    if (!pendingSave || !selectedTemplateId) return;
    try {
      const values = await labelForm.validateFields();
      setSavingAnnotation(true);
      const created = await createTemplateAnnotation({
        template: selectedTemplateId,
        annotation_type: 'rect',
        points: [
          Math.round(pendingSave.x),
          Math.round(pendingSave.y),
          Math.round(pendingSave.width),
          Math.round(pendingSave.height),
        ],
        label: values.label || '',
      });
      const canvasAnn: CanvasAnnotation = {
        ...pendingSave,
        id: `tmpl_ann_${created.id}`,
        label: values.label || undefined,
      };
      addAnnotation(canvasAnn);
      setAnnotationIdMap((prev) => new Map(prev).set(canvasAnn.id, created.id));
      setSaveModalOpen(false);
      setPendingSave(null);
      message.success(t('templateAnnotation.msg_saved'));
    } catch {
      // validation error or API error
    } finally {
      setSavingAnnotation(false);
    }
  }, [pendingSave, selectedTemplateId, labelForm, addAnnotation, message, t]);

  /** Delete annotation via API. */
  const handleDeleteAnnotation = useCallback(
    async (canvasAnnId: string) => {
      const backendId = annotationIdMap.get(canvasAnnId);
      if (!backendId) {
        // Not persisted yet (e.g., still in pendingSave flow) — just remove locally.
        removeAnnotation(canvasAnnId);
        return;
      }
      try {
        await deleteTemplateAnnotation(backendId);
        removeAnnotation(canvasAnnId);
        setAnnotationIdMap((prev) => {
          const next = new Map(prev);
          next.delete(canvasAnnId);
          return next;
        });
        message.success(t('templateAnnotation.msg_deleted'));
      } catch {
        message.error(t('templateAnnotation.msg_delete_failed'));
      }
    },
    [annotationIdMap, removeAnnotation, message, t],
  );

  /** Batch delete all annotations for the current template. */
  const handleBatchDelete = useCallback(async () => {
    if (!selectedTemplateId) return;
    try {
      const res = await batchDeleteTemplateAnnotations(selectedTemplateId);
      clearAnnotations();
      setAnnotationIdMap(new Map());
      message.success(t('templateAnnotation.msg_batch_deleted', { count: res.deleted }));
    } catch {
      message.error(t('templateAnnotation.msg_delete_failed'));
    }
  }, [selectedTemplateId, clearAnnotations, message, t]);

  /** COCO export — current template's annotations only. */
  const handleExportCoco = useCallback(() => {
    if (annotations.length === 0) {
      message.warning(t('templateAnnotation.msg_no_export_data'));
      return;
    }
    const coco = {
      images: [
        {
          id: selectedTemplateId || 1,
          file_name: selectedTemplate?.name || 'template.png',
          width: CANVAS_WIDTH,
          height: CANVAS_HEIGHT,
        },
      ],
      annotations: annotations.map((a, i) => ({
        id: i + 1,
        image_id: selectedTemplateId || 1,
        category_id: 1,
        bbox: [Math.round(a.x), Math.round(a.y), Math.round(a.width), Math.round(a.height)],
        area: Math.round(a.width * a.height),
        iscrowd: 0,
      })),
      categories: [{ id: 1, name: 'template_region', supercategory: 'annotation' }],
    };
    const blob = new Blob([JSON.stringify(coco, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `annotations_template_${selectedTemplateId || 'unknown'}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    message.success(t('templateAnnotation.msg_exported', { count: annotations.length }));
  }, [annotations, selectedTemplateId, selectedTemplate, message, t]);

  /** Display annotations + drawing preview. */
  const displayAnnotations: CanvasAnnotation[] = useMemo(() => {
    const list = annotations.map((a) => ({
      ...a,
      color: a.id === selectedAnnotation?.id ? token.colorPrimary : a.color,
    }));
    if (drawRect) {
      list.push({
        id: '__drawing__',
        type: 'rect',
        x: drawRect.x,
        y: drawRect.y,
        width: drawRect.w,
        height: drawRect.h,
        color: token.colorSuccess,
      });
    }
    return list;
  }, [annotations, selectedAnnotation, drawRect]);

  return (
    <div className="gaf-flex-col gaf-gap-md gaf-p-lg gaf-h-full">
      {/* Toolbar: pack + template selector + actions */}
      <Card size="small" className="gaf-flex-shrink-0">
        <Space wrap>
          <span className="gaf-font-medium gaf-text-sm">{t('templateAnnotation.tab_template')}</span>
          <Select
            style={{ width: 220 }}
            placeholder={t('templateAnnotation.select_pack')}
            value={selectedPackId}
            onChange={setSelectedPackId}
            options={packs.map((p) => ({ value: p.id, label: p.name }))}
            loading={loadingTemplates}
          />
          <Select
            style={{ width: 280 }}
            placeholder={t('templateAnnotation.select_template')}
            value={selectedTemplateId}
            onChange={setSelectedTemplateId}
            options={templates.map((tpl) => ({ value: tpl.id, label: tpl.name }))}
            loading={loadingTemplates}
            disabled={templates.length === 0}
          />
          <Tooltip title={t('templateAnnotation.btn_reload_annotations')}>
            <Button
              size="small"
              icon={<ReloadOutlined />}
              aria-label={t('templateAnnotation.btn_reload_annotations')}
              disabled={!selectedTemplateId}
              loading={loadingAnnotations}
              onClick={() => selectedTemplateId && loadAnnotations(selectedTemplateId)}
            />
          </Tooltip>
          <Tooltip title={t('templateAnnotation.tool_delete_tip')}>
            <Button
              size="small"
              icon={<DeleteOutlined />}
              aria-label={t('templateAnnotation.tool_delete_tip')}
              disabled={!selectedAnnotation}
              onClick={() => selectedAnnotation && handleDeleteAnnotation(selectedAnnotation.id)}
            />
          </Tooltip>
          <Button size="small" danger disabled={annotations.length === 0} onClick={handleBatchDelete}>
            {t('templateAnnotation.btn_batch_delete')}
          </Button>
          <Button
            size="small"
            type="primary"
            icon={<DownloadOutlined />}
            onClick={handleExportCoco}
            disabled={annotations.length === 0}
          >
            {t('templateAnnotation.btn_export')}
          </Button>
        </Space>
      </Card>

      {/* Canvas + side panel */}
      <div className="gaf-flex gaf-gap-md gaf-flex-1" style={{ minHeight: 0 }}>
        <div
          className="gaf-flex-1 gaf-overflow-hidden gaf-position-relative"
          style={{
            border: `1px solid ${token.colorBorder}`,
            borderRadius: 8,
            background: token.colorBgLayout,
            cursor: selectedTemplate ? 'crosshair' : 'not-allowed',
          }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
        >
          {selectedTemplate ? (
            <GafCanvasOverlay
              width={CANVAS_WIDTH}
              height={CANVAS_HEIGHT}
              annotations={displayAnnotations}
              imageUrl={templateImageUrl}
              className="gaf-w-full gaf-h-full"
              style={{ border: 'none', borderRadius: 0 }}
            />
          ) : (
            <div
              className="gaf-flex-col gaf-gap-sm gaf-justify-center gaf-h-full"
              style={{ alignItems: 'center', color: token.colorTextTertiary }}
            >
              <Typography.Text type="secondary">
                {templates.length === 0
                  ? t('templateAnnotation.empty_no_templates')
                  : t('templateAnnotation.empty_select_template')}
              </Typography.Text>
            </div>
          )}
        </div>

        {/* Annotation list panel */}
        <Card
          size="small"
          title={t('templateAnnotation.list_title')}
          className="gaf-overflow-auto gaf-flex-shrink-0"
          style={{ width: 280 }}
          extra={
            <Typography.Text type="secondary" className="gaf-text-xxs">
              {t('templateAnnotation.list_count', { count: annotations.length })}
            </Typography.Text>
          }
        >
          {annotations.length === 0 ? (
            <Empty description={t('templateAnnotation.empty_annotations')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <div>
              {annotations.map((ann) => {
                const isSelected = ann.id === selectedAnnotation?.id;
                return (
                  <button
                    type="button"
                    key={ann.id}
                    className="gaf-reset-button gaf-py-sm gaf-px-md"
                    style={{ background: isSelected ? token.colorPrimaryBg : undefined }}
                    onClick={() => selectAnnotation(ann.id)}
                    aria-label={ann.label || `annotation ${ann.id.slice(-4)}`}
                  >
                    <div className="gaf-flex gaf-py-xs">
                      <div className="gaf-flex-1">
                        <div className="gaf-flex-center gaf-gap-xs gaf-font-medium" style={{ marginBottom: 2 }}>
                          <Tag color={ann.color || 'green'} style={{ fontSize: 10 }}>
                            {ann.type}
                          </Tag>
                          <Typography.Text className="gaf-text-13" style={{ fontWeight: isSelected ? 600 : 400 }}>
                            {ann.label || t('templateAnnotation.annotation_default', { id: ann.id.slice(-4) })}
                          </Typography.Text>
                        </div>
                        <div className="gaf-text-xxs" style={{ color: token.colorTextTertiary }}>
                          <div>
                            {Math.round(ann.width)}×{Math.round(ann.height)}
                          </div>
                        </div>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}

          {selectedAnnotation && (
            <Descriptions size="small" column={1} className="gaf-mt-md" bordered>
              <Descriptions.Item label={t('templateAnnotation.label_position')}>
                ({Math.round(selectedAnnotation.x)}, {Math.round(selectedAnnotation.y)})
              </Descriptions.Item>
              <Descriptions.Item label={t('templateAnnotation.label_size')}>
                {Math.round(selectedAnnotation.width)} × {Math.round(selectedAnnotation.height)}
              </Descriptions.Item>
              {selectedAnnotation.label && (
                <Descriptions.Item label={t('templateAnnotation.label_label')}>
                  {selectedAnnotation.label}
                </Descriptions.Item>
              )}
            </Descriptions>
          )}
        </Card>
      </div>

      {/* Save annotation modal (label input) */}
      <Modal
        title={t('templateAnnotation.modal_save_title')}
        open={saveModalOpen}
        onOk={handleSaveAnnotation}
        onCancel={() => {
          setSaveModalOpen(false);
          setPendingSave(null);
        }}
        confirmLoading={savingAnnotation}
        okText={t('templateAnnotation.modal_ok')}
        cancelText={t('templateAnnotation.modal_cancel')}
      >
        <Form form={labelForm} layout="vertical">
          <Form.Item name="label" label={t('templateAnnotation.label_annotation_label')}>
            <Input placeholder={t('templateAnnotation.placeholder_annotation_label')} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default TemplateAnnotationTab;
