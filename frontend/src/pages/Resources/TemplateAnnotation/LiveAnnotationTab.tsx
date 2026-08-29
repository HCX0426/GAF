import React, { useState, useCallback, useRef, useEffect } from 'react';
import {
  Button,
  Input,
  Select,
  Tooltip,
  Modal,
  Form,
  App,
  Tag,
  Typography,
  Card,
  Descriptions,
  Empty,
  Dropdown,
  Checkbox,
  Switch,
  Tabs,
  theme as antTheme,
} from 'antd';
import {
  UndoOutlined,
  RedoOutlined,
  SaveOutlined,
  DeleteOutlined,
  AimOutlined,
  SearchOutlined,
  EyeOutlined,
  EnvironmentOutlined,
  MinusCircleOutlined,
  LineOutlined,
  DownloadOutlined,
} from '@ant-design/icons';
import GafCanvasOverlay from '@/components/Canvas/GafCanvasOverlay';
import type { Annotation as CanvasAnnotation } from '@/components/Canvas/GafCanvasOverlay';
import { useCanvasAnnotation } from '@/hooks/useCanvasAnnotation';
import { useScreenshotStream } from '@/hooks/useScreenshotStream';
import { useTranslation } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';
import { useDeviceStore } from '@/stores/useDeviceStore';
import DeviceOperationPanel from '@/components/Device/DeviceOperationPanel';
import { matchTemplatePreview } from '@/api/resources';

/** Supported drawing tools */
type DrawingTool = 'rect' | 'polygon' | 'ellipse' | 'select' | 'point' | 'line';

/** Canvas interaction mode — 'draw' = annotation drawing, 'pick-*' = coordinate picking (R37-P3 C3) */
type CanvasMode = 'draw' | 'pick-click' | 'pick-swipe-start' | 'pick-swipe-end';

/** Saved template metadata */
interface SavedTemplate {
  id: string;
  annotationId: string;
  name: string;
  category: string;
  description: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Single entry in the undo/redo history */
interface HistoryEntry {
  type: 'add' | 'remove';
  annotation: CanvasAnnotation;
}

/** COCO JSON export structure */
interface CocoExport {
  images: Array<{ id: number; file_name: string; width: number; height: number }>;
  annotations: Array<{
    id: number;
    image_id: number;
    category_id: number;
    segmentation?: number[][][];
    bbox: number[];
    area: number;
    iscrowd: number;
  }>;
  categories: Array<{ id: number; name: string; supercategory: string }>;
}

const CANVAS_WIDTH = 800;
const CANVAS_HEIGHT = 600;
const MAX_HISTORY = 50;

/** Tool colors mapped by drawing type */
const TOOL_COLORS: Record<string, string> = {
  rect: '#52c41a',
  ellipse: '#13c2c2',
  polygon: '#722ed1',
  point: '#eb2f96',
  line: '#fa8c16',
};

/** Available fields for COCO export selection */
type ExportField = 'annotation_id' | 'image_id' | 'category_id' | 'segmentation' | 'bbox' | 'area' | 'confidence';

export function LiveAnnotationTab() {
  const t = useTranslation();
  const { message } = App.useApp();
  const { token } = antTheme.useToken();
  const { currentFrame, isStreaming, startStream, stopStream } = useScreenshotStream();
  const { annotations, addAnnotation, removeAnnotation, selectAnnotation, selectedAnnotation } = useCanvasAnnotation();

  // Device selection — drives screenshot stream startup (R37-P3 C1)
  const [selectedDeviceId, setSelectedDeviceId] = useState<number | undefined>();
  const devices = useDeviceStore((s) => s.devices);
  const fetchDevices = useDeviceStore((s) => s.fetchDevices);
  const selectedDevice = devices.find((d) => d.id === selectedDeviceId);
  const agentId = selectedDevice?.agent_info?.agent_id;

  // Ensure device list is loaded when this tab mounts (R37-P3 C5 fix).
  // Without this, navigating directly to /template-annotation shows an empty device dropdown
  // because no other page has populated the store yet.
  useEffect(() => {
    if (devices.length === 0) {
      void fetchDevices();
    }
  }, [devices.length, fetchDevices]);

  // Coordinate picking bridge between Canvas and DeviceOperationPanel (R37-P3 C2/C3)
  const [coordinatePickTarget, setCoordinatePickTarget] = useState<'click' | 'swipeStart' | 'swipeEnd' | null>(null);
  const [prefilledCoordinate, setPrefilledCoordinate] = useState<{ x: number; y: number } | null>(null);

  // Canvas mode state machine: 'draw' = normal annotation drawing, 'pick-*' = coordinate picking (R37-P3 C3)
  // Coordinate picking takes priority over drawing tools — see handleCanvasClick.
  const [canvasMode, setCanvasMode] = useState<CanvasMode>('draw');

  // Sync coordinatePickTarget (set by DeviceOperationPanel) → canvasMode (read by Canvas)
  useEffect(() => {
    if (coordinatePickTarget === 'click') setCanvasMode('pick-click');
    else if (coordinatePickTarget === 'swipeStart') setCanvasMode('pick-swipe-start');
    else if (coordinatePickTarget === 'swipeEnd') setCanvasMode('pick-swipe-end');
    else setCanvasMode('draw');
  }, [coordinatePickTarget]);

  const [activeTool, setActiveTool] = useState<DrawingTool>('rect');
  const [templates, setTemplates] = useState<SavedTemplate[]>([]);
  const [isDrawing, setIsDrawing] = useState(false);
  const [drawStart, setDrawStart] = useState({ x: 0, y: 0 });
  const [drawRect, setDrawRect] = useState<{ x: number; y: number; w: number; h: number } | null>(null);

  /** polygon drawing state — accumulated vertices */
  const [polygonPoints, setPolygonPoints] = useState<{ x: number; y: number }[]>([]);
  /** line drawing state — start point */
  const [lineStart, setLineStart] = useState<{ x: number; y: number } | null>(null);

  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [pendingAnnotation, setPendingAnnotation] = useState<CanvasAnnotation | null>(null);
  const [templateForm] = Form.useForm();
  const [saveLoading, setSaveLoading] = useState(false);
  const [matchPreview, setMatchPreview] = useState<
    Array<{ x: number; y: number; w: number; h: number; confidence: number }>
  >([]);
  const containerRef = useRef<HTMLDivElement>(null);

  /** Undo/Redo history stacks */
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);

  /** COCO export modal state — tracks modal visibility */
  const [cocoExportModalOpen, setCocoExportModalOpen] = useState(false);
  /** COCO export — selected annotation IDs for batch export */
  const [selectedAnnotationIds, setSelectedAnnotationIds] = useState<Set<string>>(new Set());
  /** COCO export — field selection flags */
  const [exportFields, setExportFields] = useState<Record<ExportField, boolean>>({
    annotation_id: true,
    image_id: true,
    category_id: true,
    segmentation: true,
    bbox: true,
    area: true,
    confidence: false,
  });

  // Start screenshot stream when a device is selected; stop on unmount or device change.
  // The hook's internal cleanup (H16 fix) guards against sending stop on a closed WS.
  useEffect(() => {
    if (!agentId) return; // no device selected yet — nothing to stream
    startStream(agentId);
    return () => stopStream();
  }, [agentId, startStream, stopStream]);

  /** Build display annotations list with selection highlight and drawing preview */
  const displayAnnotations: CanvasAnnotation[] = annotations.map((a) => ({
    ...a,
    color: a.id === selectedAnnotation?.id ? token.colorPrimary : a.color,
  }));

  /** Append rect/ellipse drawing preview */
  if (drawRect && (activeTool === 'rect' || activeTool === 'ellipse')) {
    displayAnnotations.push({
      id: '__drawing__',
      type: activeTool === 'ellipse' ? 'circle' : 'rect',
      x: drawRect.x,
      y: drawRect.y,
      width: drawRect.w,
      height: drawRect.h,
      color: TOOL_COLORS[activeTool],
    });
  }

  /** Append polygon drawing preview (closed shape or open path) */
  if (polygonPoints.length > 0 && activeTool === 'polygon') {
    const xs = polygonPoints.map((p) => p.x);
    const ys = polygonPoints.map((p) => p.y);
    const minX = Math.min(...xs),
      maxX = Math.max(...xs);
    const minY = Math.min(...ys),
      maxY = Math.max(...ys);
    if (polygonPoints.length >= 3) {
      displayAnnotations.push({
        id: '__drawing_polygon__',
        type: 'rect',
        x: minX,
        y: minY,
        width: maxX - minX,
        height: maxY - minY,
        color: TOOL_COLORS.polygon,
      });
    }
  }

  /** Append line drawing preview */
  if (lineStart && activeTool === 'line') {
    displayAnnotations.push({
      id: '__drawing_line__',
      type: 'rect',
      x: Math.min(lineStart.x, lineStart.y === -999 ? lineStart.x : lineStart.x),
      y: Math.min(lineStart.y, lineStart.y === -999 ? lineStart.y : lineStart.y),
      width: Math.abs(lineStart.x - (lineStart.y === -999 ? lineStart.x : lineStart.x)) || 4,
      height: Math.abs(lineStart.y - (lineStart.y === -999 ? lineStart.y : lineStart.y)) || 4,
      color: TOOL_COLORS.line,
    });
  }

  // ─── Coordinate helpers ──────────────────────────────

  const getCanvasCoords = useCallback((e: React.MouseEvent): { x: number; y: number } => {
    const container = containerRef.current;
    if (!container) return { x: 0, y: 0 };
    const rect = container.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }, []);

  // ─── Undo / Redo ──────────────────────────────────────

  /** Push an action onto the history stack (trims future redo branch) */
  const pushHistory = useCallback(
    (entry: HistoryEntry) => {
      setHistory((prev) => {
        const trimmed = prev.slice(0, historyIndex + 1);
        const next = [...trimmed, entry].slice(-MAX_HISTORY);
        return next;
      });
      setHistoryIndex((i) => Math.min(i + 1, MAX_HISTORY - 1));
    },
    [historyIndex],
  );

  const handleUndo = useCallback(() => {
    if (historyIndex < 0) return;
    const entry = history[historyIndex];
    if (entry.type === 'add') {
      removeAnnotation(entry.annotation.id);
    } else {
      addAnnotation(entry.annotation);
    }
    setHistoryIndex((i) => i - 1);
  }, [history, historyIndex, removeAnnotation, addAnnotation]);

  const handleRedo = useCallback(() => {
    if (historyIndex >= history.length - 1) return;
    const nextIdx = historyIndex + 1;
    const entry = history[nextIdx];
    if (entry.type === 'add') {
      addAnnotation(entry.annotation);
    } else {
      removeAnnotation(entry.annotation.id);
    }
    setHistoryIndex(nextIdx);
  }, [history, historyIndex, addAnnotation, removeAnnotation]);

  // ─── Rect / Ellipse drawing (drag) ───────────────────

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (activeTool !== 'rect' && activeTool !== 'ellipse') return;
      const coords = getCanvasCoords(e);
      setDrawStart(coords);
      setIsDrawing(true);
      setDrawRect({ x: coords.x, y: coords.y, w: 0, h: 0 });
    },
    [activeTool, getCanvasCoords],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!isDrawing || !drawRect) return;
      const coords = getCanvasCoords(e);
      const x = Math.min(drawStart.x, coords.x);
      const y = Math.min(drawStart.y, coords.y);
      const w = Math.abs(coords.x - drawStart.x);
      const h = Math.abs(coords.y - drawStart.y);
      setDrawRect({ x, y, w, h });
    },
    [isDrawing, drawStart, getCanvasCoords],
  );

  const handleMouseUp = useCallback(() => {
    if (!isDrawing || !drawRect) return;
    setIsDrawing(false);
    if (drawRect.w < 5 || drawRect.h < 5) {
      setDrawRect(null);
      return;
    }

    const newAnn: CanvasAnnotation = {
      id: `ann_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      type: activeTool === 'ellipse' ? 'circle' : 'rect',
      x: drawRect.x,
      y: drawRect.y,
      width: drawRect.w,
      height: drawRect.h,
      color: TOOL_COLORS[activeTool],
    };
    addAnnotation(newAnn);
    pushHistory({ type: 'add', annotation: newAnn });
    setPendingAnnotation(newAnn);
    setSaveModalOpen(true);
    templateForm.resetFields();
    setDrawRect(null);
  }, [isDrawing, drawRect, activeTool, addAnnotation, templateForm, pushHistory]);

  // ─── Polygon drawing (click vertices) ─────────────────

  const handlePolygonClick = useCallback(
    (x: number, y: number) => {
      if (activeTool !== 'polygon') return;
      const newPoints = [...polygonPoints, { x, y }];
      setPolygonPoints(newPoints);
    },
    [activeTool, polygonPoints],
  );

  const handlePolygonDblClick = useCallback(() => {
    if (activeTool !== 'polygon' || polygonPoints.length < 3) return;

    const xs = polygonPoints.map((p) => p.x);
    const ys = polygonPoints.map((p) => p.y);
    const minX = Math.min(...xs),
      maxX = Math.max(...xs);
    const minY = Math.min(...ys),
      maxY = Math.max(...ys);

    const newAnn: CanvasAnnotation = {
      id: `ann_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      type: 'rect',
      x: minX,
      y: minY,
      width: maxX - minX,
      height: maxY - minY,
      color: TOOL_COLORS.polygon,
      label: t('templateAnnotation.label_polygon', { count: polygonPoints.length }),
    };
    addAnnotation(newAnn);
    pushHistory({ type: 'add', annotation: newAnn });
    setPendingAnnotation(newAnn);
    setSaveModalOpen(true);
    templateForm.resetFields();
    setPolygonPoints([]);
  }, [activeTool, polygonPoints, addAnnotation, templateForm, pushHistory, t]);

  // ─── Point drawing (single click) ──────────────────────

  const handlePointClick = useCallback(
    (x: number, y: number) => {
      if (activeTool !== 'point') return;
      const newAnn: CanvasAnnotation = {
        id: `ann_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        type: 'rect',
        x: x - 4,
        y: y - 4,
        width: 8,
        height: 8,
        color: TOOL_COLORS.point,
        label: t('templateAnnotation.label_point', { x: Math.round(x), y: Math.round(y) }),
      };
      addAnnotation(newAnn);
      pushHistory({ type: 'add', annotation: newAnn });
    },
    [activeTool, addAnnotation, pushHistory, t],
  );

  // ─── Line drawing (click start → click end) ─────────────

  const handleLineClick = useCallback(
    (x: number, y: number) => {
      if (activeTool !== 'line') return;
      if (!lineStart) {
        setLineStart({ x, y });
      } else {
        const newAnn: CanvasAnnotation = {
          id: `ann_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
          type: 'rect',
          x: Math.min(lineStart.x, x),
          y: Math.min(lineStart.y, y),
          width: Math.abs(x - lineStart.x) || 4,
          height: Math.abs(y - lineStart.y) || 4,
          color: TOOL_COLORS.line,
          label: t('templateAnnotation.label_line'),
        };
        addAnnotation(newAnn);
        pushHistory({ type: 'add', annotation: newAnn });
        setLineStart(null);
      }
    },
    [activeTool, lineStart, addAnnotation, pushHistory, t],
  );

  // ─── Select / Delete / Keyboard ────────────────────────

  const handleCanvasClick = useCallback(
    (x: number, y: number) => {
      // Coordinate picking takes priority over drawing tools (R37-P3 C3)
      if (canvasMode === 'pick-click' || canvasMode === 'pick-swipe-start' || canvasMode === 'pick-swipe-end') {
        const rounded = { x: Math.round(x), y: Math.round(y) };
        setPrefilledCoordinate(rounded);
        setCoordinatePickTarget(null); // reset → canvasMode reverts to 'draw' via useEffect
        setCanvasMode('draw');
        message.success(t('templateAnnotation.coord_picked', { x: rounded.x, y: rounded.y }));
        return;
      }

      if (activeTool === 'polygon') {
        handlePolygonClick(x, y);
        return;
      }
      if (activeTool === 'point') {
        handlePointClick(x, y);
        return;
      }
      if (activeTool === 'line') {
        handleLineClick(x, y);
        return;
      }
      if (activeTool !== 'select') return;

      const clicked = annotations.find(
        (ann) => x >= ann.x && x <= ann.x + ann.width && y >= ann.y && y <= ann.y + ann.height,
      );
      if (clicked) {
        selectAnnotation(clicked.id);
      } else {
        selectAnnotation(null);
      }
    },
    [
      canvasMode,
      activeTool,
      annotations,
      selectAnnotation,
      handlePolygonClick,
      handlePointClick,
      handleLineClick,
      message,
      t,
    ],
  );

  /** Unified canvas mouse event handler that dispatches to the correct sub-handler */
  const handleCanvasMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (e.detail === 2) return; /* ignore double-click here, handled by dblClick */
      // Coordinate pick mode suppresses drag-drawing (R37-P3 C3)
      if (canvasMode !== 'draw') return;
      handleMouseDown(e);
    },
    [handleMouseDown, canvasMode],
  );

  const handleCanvasDblClick = useCallback(() => {
    handlePolygonDblClick();
  }, [handlePolygonDblClick]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        handleUndo();
        return;
      }
      if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
        e.preventDefault();
        handleRedo();
        return;
      }
      if (e.key === 'Delete' && selectedAnnotation) {
        const ann = annotations.find((a) => a.id === selectedAnnotation.id);
        removeAnnotation(selectedAnnotation.id);
        if (ann) pushHistory({ type: 'remove', annotation: ann });
        setTemplates((prev) => prev.filter((t2) => t2.annotationId !== selectedAnnotation.id));
        selectAnnotation(null);
      }
      if (e.key === 'Escape') {
        setPolygonPoints([]);
        setLineStart(null);
        setIsDrawing(false);
        setDrawRect(null);
      }
    },
    [
      selectedAnnotation,
      removeAnnotation,
      selectAnnotation,
      setTemplates,
      annotations,
      handleUndo,
      handleRedo,
      pushHistory,
    ],
  );

  // ─── Template save ──────────────────────────────────────

  const handleSaveTemplate = useCallback(async () => {
    try {
      const values = await templateForm.validateFields();
      if (!pendingAnnotation) return;
      setSaveLoading(true);
      const newTemplate: SavedTemplate = {
        id: `tmpl_${Date.now()}`,
        annotationId: pendingAnnotation.id,
        name: values.name,
        category: values.category,
        description: values.description || '',
        x: pendingAnnotation.x,
        y: pendingAnnotation.y,
        width: pendingAnnotation.width,
        height: pendingAnnotation.height,
      };
      setTemplates((prev) => [...prev, newTemplate]);
      setSaveModalOpen(false);
      setPendingAnnotation(null);
      message.success(t('templateAnnotation.msg_template_saved'));
    } catch {
      // form validation failed
    } finally {
      setSaveLoading(false);
    }
  }, [templateForm, pendingAnnotation, t]);

  const handleSaveAll = useCallback(() => {
    if (annotations.length === 0) {
      message.warning(t('templateAnnotation.msg_no_annotations'));
      return;
    }
    message.success(t('templateAnnotation.msg_saved_count', { count: annotations.length }));
  }, [annotations, t]);

  // ─── COCO JSON Export ────────────────────────────────────

  const handleExportCoco = useCallback(() => {
    if (annotations.length === 0) {
      message.warning(t('templateAnnotation.msg_no_export_data'));
      return;
    }

    const categoriesMap = new Map<string, number>();
    let catId = 1;
    annotations.forEach((a) => {
      const catName = a.label?.split('(')[0]?.trim() || a.type;
      if (!categoriesMap.has(catName)) categoriesMap.set(catName, catId++);
    });

    const coco: CocoExport = {
      images: [{ id: 1, file_name: 'screenshot.png', width: CANVAS_WIDTH, height: CANVAS_HEIGHT }],
      annotations: annotations.map((a, i) => ({
        id: i + 1,
        image_id: 1,
        category_id: categoriesMap.get(a.label?.split('(')[0]?.trim() || a.type) || 1,
        segmentation:
          a.type === 'rect'
            ? [
                [
                  [a.x, a.y],
                  [a.x + a.width, a.y],
                  [a.x + a.width, a.y + a.height],
                  [a.x, a.y + a.height],
                ],
              ]
            : undefined,
        bbox: [a.x, a.y, a.width, a.height],
        area: a.width * a.height,
        iscrowd: 0,
      })),
      categories: Array.from(categoriesMap.entries()).map(([name, id]) => ({ id, name, supercategory: 'annotation' })),
    };

    const blob = new Blob([JSON.stringify(coco, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `annotations_${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    message.success(t('templateAnnotation.msg_exported', { count: annotations.length }));
  }, [annotations, t]);

  // ─── Enhanced COCO Export with field selection ─────────────────────

  /** Export selected annotations with user-chosen fields */
  const handleExportCocoWithFields = useCallback(() => {
    const selectedIds = Array.from(selectedAnnotationIds);
    if (selectedIds.length === 0) {
      message.warning(t('templateAnnotation.msg_select_export'));
      return;
    }

    // Filter annotations by selected IDs
    const filteredAnnotations = annotations.filter((a) => selectedIds.includes(a.id));

    // Build category mapping
    const categoriesMap = new Map<string, number>();
    let catId = 1;
    filteredAnnotations.forEach((a) => {
      const catName = a.label?.split('(')[0]?.trim() || a.type;
      if (!categoriesMap.has(catName)) categoriesMap.set(catName, catId++);
    });

    // Build annotation objects with selected fields only
    const cocoAnnotations = filteredAnnotations.map((a, i) => {
      const ann: Record<string, unknown> = {};
      if (exportFields.annotation_id) ann.id = i + 1;
      if (exportFields.image_id) ann.image_id = 1;
      if (exportFields.category_id) {
        ann.category_id = categoriesMap.get(a.label?.split('(')[0]?.trim() || a.type) || 1;
      }
      if (exportFields.segmentation && a.type === 'rect') {
        ann.segmentation = [
          [
            [a.x, a.y],
            [a.x + a.width, a.y],
            [a.x + a.width, a.y + a.height],
            [a.x, a.y + a.height],
          ],
        ];
      }
      if (exportFields.bbox) ann.bbox = [a.x, a.y, a.width, a.height];
      if (exportFields.area) ann.area = a.width * a.height;
      // confidence field is not available in current annotations
      ann.iscrowd = 0; // required COCO field
      return ann;
    });

    const coco: Record<string, unknown> = {
      images: [{ id: 1, file_name: 'screenshot.png', width: CANVAS_WIDTH, height: CANVAS_HEIGHT }],
      annotations: cocoAnnotations,
      categories: Array.from(categoriesMap.entries()).map(([name, id]) => ({ id, name, supercategory: 'annotation' })),
    };

    const blob = new Blob([JSON.stringify(coco, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `annotations_${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    message.success(t('templateAnnotation.msg_exported_filtered', { count: filteredAnnotations.length }));
    setCocoExportModalOpen(false);
  }, [annotations, selectedAnnotationIds, exportFields, t]);

  // ─── Match preview (R37-P2 real: 当前帧 + 选中框裁剪模板 → 后端 cv2 匹配；后端不可用时回退 mock) ───

  const handleTemplateMatchPreview = useCallback(async () => {
    if (!currentFrame?.imageBase64) {
      message.warning(t('templateAnnotation.match_preview_no_frame'));
      return;
    }
    const ann = selectedAnnotation;
    if (!ann || (ann.type !== 'rect' && ann.type !== 'circle') || ann.width <= 0 || ann.height <= 0) {
      message.warning(t('templateAnnotation.match_preview_select_area'));
      return;
    }
    // 裁剪模板：annotation 坐标为图片自然像素（GafCanvasOverlay backing store = 原图尺寸）
    const cutX = Math.floor(ann.x);
    const cutY = Math.floor(ann.y);
    const cutW = Math.max(1, Math.floor(ann.width));
    const cutH = Math.max(1, Math.floor(ann.height));
    let templateBase64 = '';
    try {
      const img = await new Promise<HTMLImageElement>((resolve, reject) => {
        const image = new Image();
        image.onload = () => resolve(image);
        image.onerror = () => reject(new Error('image load failed'));
        image.src = currentFrame.imageBase64.startsWith('data:')
          ? currentFrame.imageBase64
          : `data:image/png;base64,${currentFrame.imageBase64}`;
      });
      const canvas = document.createElement('canvas');
      canvas.width = cutW;
      canvas.height = cutH;
      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error('no 2d context');
      ctx.drawImage(img, cutX, cutY, cutW, cutH, 0, 0, cutW, cutH);
      templateBase64 = canvas.toDataURL('image/png');
    } catch {
      message.warning(t('templateAnnotation.match_preview_crop_failed'));
      return;
    }
    try {
      const data = await matchTemplatePreview(currentFrame.imageBase64, templateBase64, 0.8);
      if (data.error) {
        message.warning(data.error);
        return;
      }
      setMatchPreview(data.matches ?? []);
      message.success(
        t('templateAnnotation.msg_match_preview_result', { count: (data.matches ?? []).length }),
      );
    } catch {
      // 后端不可用（离线/未启动）时回退原 mock，避免功能完全不可用
      setMatchPreview([
        { x: 100, y: 150, w: 80, h: 40, confidence: 0.95 },
        { x: 350, y: 200, w: 80, h: 40, confidence: 0.87 },
      ]);
      message.info(t('templateAnnotation.msg_match_preview'));
    }
  }, [currentFrame, selectedAnnotation, message, t]);

  const matchAnnotations: CanvasAnnotation[] = matchPreview.map((m, i) => ({
    id: `match_${i}`,
    type: 'rect' as const,
    x: m.x,
    y: m.y,
    width: m.w,
    height: m.h,
    color: token.colorWarning,
    label: `${(m.confidence * 100).toFixed(0)}%`,
  }));

  const finalAnnotations = [...displayAnnotations, ...matchAnnotations];

  // ─── Cancel ongoing drawing operations ─────────────────

  const cancelDrawing = useCallback(() => {
    setPolygonPoints([]);
    setLineStart(null);
    setIsDrawing(false);
    setDrawRect(null);
  }, []);

  // ─── Render ───────────────────────────────────────────

  return (
    <PageWrapper>
      <div className="gaf-flex-col gaf-gap-md gaf-p-lg gaf-h-full">
        {/* Toolbar */}
        <Card size="small" className="gaf-flex-shrink-0">
          <div className="gaf-toolbar">
            <span className="gaf-font-medium gaf-text-sm">{t('templateAnnotation.toolbar_label')}</span>

            {/* Device selector — drives screenshot stream (R37-P3 C1) */}
            <Select<number>
              value={selectedDeviceId}
              onChange={(v) => setSelectedDeviceId(v)}
              options={devices.map((d) => ({
                value: d.id,
                label: d.name || `Device #${d.id}`,
              }))}
              placeholder={t('templateAnnotation.device_select')}
              style={{ minWidth: 180 }}
              allowClear
              showSearch
              optionFilterProp="label"
            />
            {isStreaming && <Tag color="processing">{t('templateAnnotation.stream_active')}</Tag>}

            <div className="gaf-toolbar-divider" style={{ background: token.colorBorder }} />

            {/* Shape tools */}
            <Tooltip title={t('templateAnnotation.tool_rect_tip')}>
              <Button
                type={activeTool === 'rect' ? 'primary' : 'default'}
                size="small"
                icon={<AimOutlined />}
                onClick={() => setActiveTool('rect')}
              >
                {t('templateAnnotation.tool_rect')}
              </Button>
            </Tooltip>
            <Tooltip title={t('templateAnnotation.tool_ellipse_tip')}>
              <Button
                type={activeTool === 'ellipse' ? 'primary' : 'default'}
                size="small"
                icon={<AimOutlined />}
                onClick={() => setActiveTool('ellipse')}
              >
                {t('templateAnnotation.tool_ellipse')}
              </Button>
            </Tooltip>
            <Tooltip title={t('templateAnnotation.tool_polygon_tip')}>
              <Button
                type={activeTool === 'polygon' ? 'primary' : 'default'}
                size="small"
                icon={<EnvironmentOutlined />}
                onClick={() => {
                  setActiveTool('polygon');
                  cancelDrawing();
                }}
              >
                {t('templateAnnotation.tool_polygon')}
              </Button>
            </Tooltip>
            <Tooltip title={t('templateAnnotation.tool_line_tip')}>
              <Button
                type={activeTool === 'line' ? 'primary' : 'default'}
                size="small"
                icon={<LineOutlined />}
                onClick={() => {
                  setActiveTool('line');
                  cancelDrawing();
                }}
              >
                {t('templateAnnotation.tool_line')}
              </Button>
            </Tooltip>
            <Tooltip title={t('templateAnnotation.tool_point_tip')}>
              <Button
                type={activeTool === 'point' ? 'primary' : 'default'}
                size="small"
                icon={<MinusCircleOutlined />}
                onClick={() => {
                  setActiveTool('point');
                  cancelDrawing();
                }}
              >
                {t('templateAnnotation.tool_point')}
              </Button>
            </Tooltip>

            <div className="gaf-toolbar-divider" style={{ background: token.colorBorder }} />

            {/* Edit tools */}
            <Tooltip title={t('templateAnnotation.tool_select_tip')}>
              <Button
                type={activeTool === 'select' ? 'primary' : 'default'}
                size="small"
                icon={<SearchOutlined />}
                onClick={() => {
                  setActiveTool('select');
                  cancelDrawing();
                }}
              >
                {t('templateAnnotation.tool_select')}
              </Button>
            </Tooltip>
            <Tooltip title={t('templateAnnotation.tool_delete_tip')}>
              <Button
                size="small"
                icon={<DeleteOutlined />}
                aria-label={t('templateAnnotation.tool_delete_tip')}
                disabled={!selectedAnnotation}
                onClick={() => {
                  if (selectedAnnotation) {
                    const ann = annotations.find((a) => a.id === selectedAnnotation.id);
                    removeAnnotation(selectedAnnotation.id);
                    if (ann) pushHistory({ type: 'remove', annotation: ann });
                    setTemplates((prev) => prev.filter((t2) => t2.annotationId !== selectedAnnotation.id));
                    selectAnnotation(null);
                  }
                }}
              />
            </Tooltip>
            <Tooltip
              title={t('templateAnnotation.tool_undo_tip', {
                state: historyIndex >= 0 ? `[${historyIndex + 1}/${history.length}]` : '',
              })}
            >
              <Button
                size="small"
                icon={<UndoOutlined />}
                aria-label={t('templateAnnotation.tool_undo_tip', {
                  state: historyIndex >= 0 ? `[${historyIndex + 1}/${history.length}]` : '',
                })}
                disabled={historyIndex < 0}
                onClick={handleUndo}
              />
            </Tooltip>
            <Tooltip
              title={t('templateAnnotation.tool_redo_tip', {
                state:
                  historyIndex < history.length - 1 ? `[${history.length - 1 - historyIndex}/${history.length}]` : '',
              })}
            >
              <Button
                size="small"
                icon={<RedoOutlined />}
                aria-label={t('templateAnnotation.tool_redo_tip', {
                  state:
                    historyIndex < history.length - 1 ? `[${history.length - 1 - historyIndex}/${history.length}]` : '',
                })}
                disabled={historyIndex >= history.length - 1}
                onClick={handleRedo}
              />
            </Tooltip>

            <div className="gaf-toolbar-divider" style={{ background: token.colorBorder }} />

            {/* Action tools */}
            <Tooltip title={t('templateAnnotation.btn_cancel_tip')}>
              <Button
                size="small"
                danger
                onClick={cancelDrawing}
                disabled={!isDrawing && polygonPoints.length === 0 && !lineStart}
              >
                {t('templateAnnotation.btn_cancel')}
              </Button>
            </Tooltip>
            <Button size="small" type="primary" icon={<SaveOutlined />} onClick={handleSaveAll}>
              {t('templateAnnotation.btn_save_all')}
            </Button>
            <div className="gaf-toolbar-group">
              <Dropdown
                menu={{
                  items: [
                    {
                      key: 'coco',
                      label: t('templateAnnotation.export_coco_json'),
                      icon: <DownloadOutlined />,
                      onClick: handleExportCoco,
                    },
                  ],
                }}
              >
                <Button size="small" icon={<DownloadOutlined />}>
                  {t('templateAnnotation.btn_export')}
                </Button>
              </Dropdown>
              <Button
                size="small"
                icon={<DownloadOutlined />}
                onClick={() => {
                  setCocoExportModalOpen(true);
                  // Initialize selection with all annotations
                  setSelectedAnnotationIds(new Set(annotations.map((a) => a.id)));
                }}
              >
                {t('templateAnnotation.btn_export_coco')}
              </Button>
            </div>
          </div>
        </Card>

        {/* Canvas area */}
        <div className="gaf-flex gaf-gap-md gaf-flex-1" style={{ minHeight: 0 }}>
          <div
            ref={containerRef}
            className="gaf-flex-1 gaf-overflow-hidden gaf-position-relative gaf-radius-lg"
            style={{
              border: `1px solid ${token.colorBorder}`,
              background: token.colorBgLayout,
              cursor: canvasMode !== 'draw' ? 'crosshair' : activeTool === 'select' ? 'default' : 'crosshair',
            }}
            onMouseDown={handleCanvasMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onDoubleClick={handleCanvasDblClick}
            onKeyDown={handleKeyDown}
            tabIndex={0}
          >
            {/* Coordinate pick mode banner (R37-P3 C3) */}
            {canvasMode !== 'draw' && (
              <div
                className="gaf-position-absolute gaf-radius-sm gaf-text-xs"
                style={{
                  top: 8,
                  left: 8,
                  zIndex: 10,
                  background: 'rgba(24,144,255,0.9)',
                  color: '#fff',
                  padding: '4px 12px',
                  pointerEvents: 'none',
                }}
              >
                {t('templateAnnotation.pick_mode_active')}
              </div>
            )}
            {currentFrame ? (
              <GafCanvasOverlay
                width={CANVAS_WIDTH}
                height={CANVAS_HEIGHT}
                annotations={finalAnnotations}
                imageBase64={currentFrame.imageBase64}
                className="gaf-w-full gaf-h-full"
                style={{ border: 'none', borderRadius: 0 }}
                onCanvasClick={handleCanvasClick}
                showCrosshair={canvasMode !== 'draw'}
              />
            ) : (
              <div
                className="gaf-flex-col gaf-gap-sm gaf-justify-center gaf-h-full"
                style={{ alignItems: 'center', color: token.colorTextTertiary }}
              >
                <Typography.Text type="secondary">
                  {isStreaming ? t('templateAnnotation.canvas_waiting') : t('templateAnnotation.canvas_no_device')}
                </Typography.Text>
              </div>
            )}
          </div>

          {/* Right panel: inline Tabs (annotations | device ops) — R37-P3 C2 */}
          <Card
            size="small"
            style={{ width: 400 }}
            className="gaf-overflow-auto gaf-flex-shrink-0"
            styles={{ body: { padding: 0 } }}
          >
            <Tabs
              defaultActiveKey="annotations"
              size="small"
              className="gaf-px-sm"
              items={[
                {
                  key: 'annotations',
                  label: t('templateAnnotation.tab_annotations'),
                  children: (
                    <>
                      <div className="gaf-toolbar-group gaf-py-sm">
                        <Typography.Text type="secondary" className="gaf-text-xxs">
                          {t('templateAnnotation.list_count', { count: annotations.length })}
                        </Typography.Text>
                        <Button size="small" icon={<EyeOutlined />} onClick={handleTemplateMatchPreview}>
                          {t('templateAnnotation.btn_match_preview')}
                        </Button>
                      </div>
                      {annotations.length === 0 ? (
                        <Empty
                          description={t('templateAnnotation.empty_annotations')}
                          image={Empty.PRESENTED_IMAGE_SIMPLE}
                        />
                      ) : (
                        <div>
                          {(annotations || []).map((ann) => {
                            const template = templates.find((t2) => t2.annotationId === ann.id);
                            const isSelected = ann.id === selectedAnnotation?.id;
                            return (
                              <button
                                type="button"
                                key={ann.id}
                                className="gaf-reset-button gaf-py-sm gaf-px-md"
                                style={{ background: isSelected ? token.colorPrimaryBg : undefined }}
                                onClick={() => selectAnnotation(ann.id)}
                                aria-label={t('templateAnnotation.select_annotation', {
                                  name:
                                    template?.name ||
                                    ann.label ||
                                    t('templateAnnotation.annotation_default', { id: ann.id.slice(-4) }),
                                })}
                              >
                                <div className="gaf-flex gaf-py-xs">
                                  <div className="gaf-flex-1">
                                    <div
                                      className="gaf-flex-center gaf-gap-xs gaf-font-medium"
                                      style={{ marginBottom: 2 }}
                                    >
                                      <Tag color={ann.color || 'green'} style={{ fontSize: 10 }}>
                                        {ann.type}
                                      </Tag>
                                      <Typography.Text
                                        className="gaf-text-13"
                                        style={{ fontWeight: isSelected ? 600 : 400 }}
                                      >
                                        {template?.name ||
                                          ann.label ||
                                          t('templateAnnotation.annotation_default', { id: ann.id.slice(-4) })}
                                      </Typography.Text>
                                    </div>
                                    <div className="gaf-text-xxs" style={{ color: token.colorTextTertiary }}>
                                      <div>{template?.category || t('templateAnnotation.uncategorized')}</div>
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
                          <Descriptions.Item label={t('templateAnnotation.label_type')}>
                            {selectedAnnotation.type}
                          </Descriptions.Item>
                          {selectedAnnotation.label && (
                            <Descriptions.Item label={t('templateAnnotation.label_label')}>
                              {selectedAnnotation.label}
                            </Descriptions.Item>
                          )}
                        </Descriptions>
                      )}

                      {matchPreview.length > 0 && (
                        <div className="gaf-mt-md">
                          <Typography.Text strong className="gaf-text-xs">
                            {t('templateAnnotation.match_results')}
                          </Typography.Text>
                          {matchPreview.map((m, i) => (
                            <Tag key={`match-${i}-${m.x}-${m.y}`} color="gold" className="gaf-mt-xs gaf-text-xxs">
                              {t('templateAnnotation.match_position', {
                                x: m.x,
                                y: m.y,
                                confidence: (m.confidence * 100).toFixed(0),
                              })}
                            </Tag>
                          ))}
                        </div>
                      )}
                    </>
                  ),
                },
                {
                  key: 'deviceOps',
                  label: t('templateAnnotation.tab_device_ops'),
                  children: selectedDevice ? (
                    <DeviceOperationPanel
                      deviceId={selectedDevice.id}
                      deviceName={selectedDevice.name}
                      screenshotWidth={CANVAS_WIDTH}
                      screenshotHeight={CANVAS_HEIGHT}
                      onRequestCoordinatePick={(target) => setCoordinatePickTarget(target)}
                      prefilledCoordinate={prefilledCoordinate}
                    />
                  ) : (
                    <Empty
                      description={t('templateAnnotation.no_device_selected')}
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                    />
                  ),
                },
              ]}
            />
          </Card>
        </div>

        {/* Save template modal */}
        <Modal
          title={t('templateAnnotation.modal_save_title')}
          open={saveModalOpen}
          onOk={handleSaveTemplate}
          onCancel={() => {
            setSaveModalOpen(false);
            setPendingAnnotation(null);
          }}
          confirmLoading={saveLoading}
          okText={t('templateAnnotation.modal_ok')}
          cancelText={t('templateAnnotation.modal_cancel')}
        >
          <Form form={templateForm} layout="vertical">
            <Form.Item
              name="name"
              label={t('templateAnnotation.label_template_name')}
              rules={[{ required: true, message: t('templateAnnotation.validate_template_name') }]}
            >
              <Input placeholder={t('templateAnnotation.placeholder_template_name')} />
            </Form.Item>
            <Form.Item
              name="category"
              label={t('templateAnnotation.label_category')}
              rules={[{ required: true, message: t('templateAnnotation.validate_category') }]}
            >
              <Select
                placeholder={t('templateAnnotation.placeholder_category')}
                options={[
                  { value: '按钮', label: t('templateAnnotation.category_button') },
                  { value: '图标', label: t('templateAnnotation.category_icon') },
                  { value: '文字', label: t('templateAnnotation.category_text') },
                  { value: '弹窗', label: t('templateAnnotation.category_popup') },
                  { value: '页面', label: t('templateAnnotation.category_page') },
                  { value: '其他', label: t('templateAnnotation.category_other') },
                ]}
              />
            </Form.Item>
            <Form.Item name="description" label={t('templateAnnotation.label_description')}>
              <Input.TextArea rows={3} placeholder={t('templateAnnotation.placeholder_description')} />
            </Form.Item>
          </Form>
        </Modal>

        {/* COCO Export Modal with field selection */}
        <Modal
          title={t('templateAnnotation.coco_modal_title')}
          open={cocoExportModalOpen}
          onCancel={() => setCocoExportModalOpen(false)}
          footer={null}
          width={600}
        >
          {/* Annotation selection section */}
          <div className="gaf-mb-lg">
            <Typography.Text strong>{t('templateAnnotation.coco_select_annotations')}</Typography.Text>
            <div className="gaf-mt-sm">
              <div className="gaf-toolbar-group">
                <Button size="small" onClick={() => setSelectedAnnotationIds(new Set(annotations.map((a) => a.id)))}>
                  {t('templateAnnotation.btn_select_all')}
                </Button>
                <Button size="small" onClick={() => setSelectedAnnotationIds(new Set())}>
                  {t('templateAnnotation.btn_clear_selection')}
                </Button>
              </div>
            </div>
            <div
              className="gaf-mt-sm gaf-p-sm gaf-overflow-auto gaf-radius-sm"
              style={{ maxHeight: 200, border: `1px solid ${token.colorBorder}` }}
            >
              {annotations.length === 0 ? (
                <Empty description={t('templateAnnotation.empty_annotations')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                annotations.map((ann) => {
                  const template = templates.find((t2) => t2.annotationId === ann.id);
                  const isSelected = selectedAnnotationIds.has(ann.id);
                  return (
                    <div
                      key={ann.id}
                      className="gaf-flex-center gaf-py-xs gaf-cursor-pointer"
                      onClick={() => {
                        const newSet = new Set(selectedAnnotationIds);
                        if (isSelected) {
                          newSet.delete(ann.id);
                        } else {
                          newSet.add(ann.id);
                        }
                        setSelectedAnnotationIds(newSet);
                      }}
                    >
                      <Checkbox checked={isSelected} className="gaf-mr-sm" />
                      <Tag color={ann.color || 'green'}>{ann.type}</Tag>
                      <span className="gaf-text-13">
                        {template?.name ||
                          ann.label ||
                          t('templateAnnotation.annotation_default', { id: ann.id.slice(-4) })}
                      </span>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Field selection section */}
          <div className="gaf-mb-lg">
            <Typography.Text strong>{t('templateAnnotation.coco_export_fields')}</Typography.Text>
            <div className="gaf-flex gaf-flex-wrap gaf-gap-md gaf-mt-sm">
              {Object.entries(exportFields).map(([field, checked]) => (
                <div key={field} className="gaf-flex-center gaf-gap-xs">
                  <Switch
                    size="small"
                    checked={checked}
                    onChange={(val) => setExportFields((prev) => ({ ...prev, [field]: val }))}
                  />
                  <span className="gaf-text-13">{field}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Export action buttons */}
          <div className="gaf-text-right" style={{ borderTop: `1px solid ${token.colorBorder}`, paddingTop: 12 }}>
            <div className="gaf-toolbar-group">
              <Button onClick={() => setCocoExportModalOpen(false)}>{t('templateAnnotation.modal_cancel')}</Button>
              <Button type="primary" onClick={handleExportCocoWithFields}>
                {t('templateAnnotation.btn_export')}
              </Button>
            </div>
          </div>
        </Modal>
      </div>
    </PageWrapper>
  );
}

export default LiveAnnotationTab;
