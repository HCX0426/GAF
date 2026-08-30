import { useState, useCallback, useRef, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  Button,
  Input,
  Select,
  Tooltip,
  Segmented,
  App,
  Typography,
  Badge,
  Spin,
  Modal,
  Tag,
  Dropdown,
  theme as antTheme,
} from 'antd';
import type { GlobalToken } from 'antd/es/theme/interface';
import {
  SaveOutlined,
  UndoOutlined,
  RedoOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  LoadingOutlined,
  ExclamationCircleOutlined,
  SyncOutlined,
  DownloadOutlined,
  UploadOutlined,
  SafetyCertificateOutlined,
  AppstoreAddOutlined,
  CopyOutlined,
  StopOutlined,
  PlayCircleOutlined,
  EyeOutlined,
  LineChartOutlined,
  CodeOutlined,
} from '@ant-design/icons';
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  MarkerType,
  ReactFlowProvider,
  ConnectionMode,
} from '@xyflow/react';
import type { Node, Edge, Connection, NodeChange, ReactFlowInstance } from '@xyflow/react';
import { Group, Panel, Separator } from 'react-resizable-panels';
import '@xyflow/react/dist/style.css';
import NodeTypeLibrary from '@/components/Pipeline/NodeTypeLibrary';
import GafPipelineNode from '@/components/Pipeline/GafPipelineNode';
import NodePropertyPanel from '@/components/Pipeline/NodePropertyPanel';
import PreviewPanel from '@/components/Pipeline/PreviewPanel';
import TemplatePicker from '@/components/Pipeline/TemplatePicker';
import RecordingPanel from '@/components/Pipeline/RecordingPanel';
import GafCodeEditor from '@/components/Editor/GafCodeEditor';
import type { PipelineTemplate } from '@/components/Pipeline/TemplatePicker';
import {
  NODE_TYPE_LIBRARY,
  DEFAULT_NODE_CONFIGS,
  NODE_TYPE_CATEGORY,
  CATEGORY_COLORS,
  type PipelineNodeType,
  type GafNodeData,
} from '@/types/models';
import { flowToPipeline, pipelineToFlow, type PipelineJSON } from '@/utils/pipelineConverter';
import { useUndoRedo } from '@/hooks/useUndoRedo';
import { usePipelineSave } from '@/hooks/usePipelineSave';
import { usePipelineKeyboard } from '@/hooks/usePipelineKeyboard';
import { useUnsavedChangesWarning } from '@/hooks/useUnsavedChangesWarning';
import * as pipelineApi from '@/api/pipelines';
import { fetchDevices } from '@/api/devices';
// Task 4.41 (P1-24, 2026-07-28): PipelineEditorPage 接入本地 ajv schema 校验
// (Task 3.5 漏改 — schemaValidator 只在 Editor.tsx 启用, PipelineEditorPage 直接调后端)
import { validatePipelineGraph } from '@/utils/schemaValidator';
// Task 4.46 (P2-24, 2026-07-28): catch 块加 error 参数, 用 resolveErrorMessage 展示具体原因
import { resolveErrorMessage } from '@/utils/errorHandler';
import { useTranslation, getLocale } from '@/i18n';

const nodeTypes = { gafPipeline: GafPipelineNode };

const defaultEdgeOptions = {
  animated: true,
  type: 'smoothstep' as const,
  markerEnd: { type: MarkerType.ArrowClosed },
};

function getSaveStatusIcon(token: GlobalToken): Record<string, React.ReactNode> {
  return {
    saved: (
      <span aria-hidden="true">
        <CheckCircleOutlined style={{ color: token.colorSuccess }} />
      </span>
    ),
    saving: (
      <span aria-hidden="true">
        <LoadingOutlined style={{ color: token.colorPrimary }} />
      </span>
    ),
    unsaved: (
      <span aria-hidden="true">
        <SyncOutlined style={{ color: token.colorWarning }} />
      </span>
    ),
    error: (
      <span aria-hidden="true">
        <ExclamationCircleOutlined style={{ color: token.colorError }} />
      </span>
    ),
  };
}

// F010 fix: map lookups replace nested ternary for validate result rendering
function getValidateResultStyle(token: GlobalToken) {
  return {
    fail: { bg: token.colorErrorBg, border: token.colorErrorBorder },
    warn: { bg: token.colorWarningBg, border: token.colorWarningBorder },
    pass: { bg: token.colorSuccessBg, border: token.colorSuccessBorder },
  };
}
const VALIDATE_RESULT_TAG_COLOR: Record<string, string> = {
  fail: 'error',
  warn: 'warning',
  pass: 'success',
};
const VALIDATE_RESULT_TAG_LABEL: Record<string, string> = {
  fail: 'pipelineEditor.tag_error',
  warn: 'pipelineEditor.tag_warning',
  pass: 'pipelineEditor.tag_pass',
};

interface PipelineEditorPageProps {
  pipelineId?: string;
  readonly?: boolean;
}

function PipelineEditorInner({ pipelineId, readonly }: { pipelineId?: string; readonly?: boolean }) {
  const t = useTranslation();
  const [nodes, setNodes, onNodesChangeBase] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChangeBase] = useEdgesState<Edge>([]);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [pipelineName, setPipelineName] = useState(() => t('pipelineEditor.default_name'));
  const [connectionMode, setConnectionMode] = useState(false);
  const flowInstanceRef = useRef<{
    screenToFlowPosition: (p: { x: number; y: number }) => { x: number; y: number };
  } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const isRestoringRef = useRef(false);
  const [loading, setLoading] = useState(false);
  const { message } = App.useApp();
  const { token } = antTheme.useToken();
  const VALIDATE_RESULT_STYLE = getValidateResultStyle(token);
  const saveStatusIcon = getSaveStatusIcon(token);
  const [showPreview, setShowPreview] = useState(false);

  /** Right-click context menu state */
  interface ContextMenuState {
    x: number;
    y: number;
    type: 'node' | 'edge' | null;
    targetId: string | null;
  }
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);

  /** Pipeline execution state */
  const [executing, setExecuting] = useState(false);
  const [canExecute, setCanExecute] = useState(false);
  const [executeResult, setExecuteResult] = useState<string | null>(null);
  // F6 fix (2026-08-28): 设备下拉改用真实设备 API (此前硬编码 device_a/device_b 占位符)
  const [deviceOptions, setDeviceOptions] = useState<{ label: string; value: string }[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<string | undefined>();

  // F6: 加载设备列表填充下拉 (Worker 在线设备)
  useEffect(() => {
    fetchDevices({ page_size: 50 })
      .then((res) => {
        const items = Array.isArray(res) ? res : res.results || [];
        setDeviceOptions(
          items.map((d) => ({
            label: `${d.name}${d.status === 'online' ? ' (在线)' : ' (离线)'}`,
            value: String(d.id),
          })),
        );
      })
      .catch(() => {
        // 设备接口失败时保持空下拉 (不阻塞编辑器)
      });
  }, []);

  // Check if there's a pipeline that can be executed
  useEffect(() => {
    if (pipelineId) {
      setCanExecute(true);
      return;
    }
    // Check if a pipeline with current name exists
    const controller = new AbortController();
    pipelineApi
      .listPipelines({ signal: controller.signal })
      .then((list) => {
        if (!controller.signal.aborted) {
          const match = list.results.find((p) => p.name === pipelineName);
          setCanExecute(!!match);
        }
      })
      .catch((err) => {
        if ((err as Error)?.name === 'AbortError') return;
        // spec35 #12: fall back to canExecute=false (safe default) but log the
        // failure so backend pipeline-list drift is debuggable.
        setCanExecute(false);
        console.warn('[PipelineEditorPage] pipelineApi.listPipelines failed:', err);
      });
    return () => {
      controller.abort();
    };
  }, [pipelineId, pipelineName]);

  const handleRunPipeline = useCallback(async () => {
    // First try route pipelineId, then check if we have a saved pipeline
    let runId = pipelineId;
    if (!runId) {
      // Try to find a pipeline with the same name
      try {
        const list = await pipelineApi.listPipelines();
        const match = list.results.find((p) => p.name === pipelineName);
        if (match) {
          runId = String(match.id);
        }
      } catch {
        // ignore
      }
    }
    if (!runId) {
      message.warning(t('pipelineEditor.msg_save_first'));
      return;
    }
    const numId = Number(runId);
    if (isNaN(numId)) return;

    setExecuting(true);
    setExecuteResult(null);
    try {
      // F6 fix (2026-08-28): 将所选设备传给执行端点 (此前完全忽略设备选择)
      const res = await pipelineApi.executePipeline(numId, selectedDevice);
      setExecuteResult(t('pipelineEditor.execute_sent', { message: res.message }));
      message.success(res.message);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { error?: string } }; message?: string };
      const detail = axiosErr?.response?.data?.error || axiosErr?.message || t('pipelineEditor.execute_default_failed');
      setExecuteResult(t('pipelineEditor.execute_failed', { detail }));
      message.error(detail);
    } finally {
      setExecuting(false);
    }
  }, [pipelineId, pipelineName, selectedDevice, message, t]);

  const { undo, redo, canUndo, canRedo, pushState, clear } = useUndoRedo(50);
  const { saveStatus, save, markDirty, lastSavedAt } = usePipelineSave();

  // F019: warn before unloading the page when there are unsaved changes.
  useUnsavedChangesWarning(saveStatus === 'unsaved');

  /** Close context menu on pane click or Escape */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setContextMenu(null);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  /** Handle node right-click — show context menu */
  const onNodeContextMenu = useCallback((event: React.MouseEvent, node: Node) => {
    event.preventDefault();
    setContextMenu({
      x: event.clientX,
      y: event.clientY,
      type: 'node',
      targetId: node.id,
    });
  }, []);

  /** Handle edge right-click — show context menu */
  const onEdgeContextMenu = useCallback((event: React.MouseEvent, edge: Edge) => {
    event.preventDefault();
    setContextMenu({
      x: event.clientX,
      y: event.clientY,
      type: 'edge',
      targetId: edge.id,
    });
  }, []);

  /** Copy a node with offset position */
  const handleCopyNode = useCallback(() => {
    if (!contextMenu || contextMenu.type !== 'node' || !contextMenu.targetId) return;
    const sourceNode = nodes.find((n) => n.id === contextMenu.targetId);
    if (!sourceNode) return;
    const newNode: Node = {
      ...sourceNode,
      id: `node_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
      position: {
        x: sourceNode.position.x + 40,
        y: sourceNode.position.y + 40,
      },
      data: { ...sourceNode.data },
      selected: false,
    };
    setNodes((nds: Node[]) => {
      const updated = [...nds, newNode];
      pushState(updated, edges);
      return updated;
    });
    markDirty();
    setContextMenu(null);
  }, [contextMenu, nodes, edges, setNodes, pushState, markDirty, message, t]);

  /** Delete a single node and its connected edges */
  const handleDeleteNode = useCallback(() => {
    if (!contextMenu || contextMenu.type !== 'node' || !contextMenu.targetId) return;
    setNodes((nds: Node[]) => {
      const updated = nds.filter((n: Node) => n.id !== contextMenu.targetId);
      pushState(updated, edges);
      return updated;
    });
    setEdges((eds: Edge[]) => {
      const remaining = eds.filter((e: Edge) => e.source !== contextMenu.targetId && e.target !== contextMenu.targetId);
      pushState(
        nodes.filter((n: Node) => n.id !== contextMenu.targetId),
        remaining,
      );
      return remaining;
    });
    if (selectedNode?.id === contextMenu.targetId) setSelectedNode(null);
    markDirty();
    setContextMenu(null);
    message.info(t('pipelineEditor.msg_node_deleted'));
  }, [contextMenu, nodes, edges, selectedNode, setNodes, setEdges, pushState, markDirty, message, t]);

  /** Toggle node disabled state (visual dim + prevent interaction) */
  const handleToggleDisable = useCallback(() => {
    if (!contextMenu || contextMenu.type !== 'node' || !contextMenu.targetId) return;
    setNodes((nds: Node[]) => {
      const updated = nds.map((n: Node) =>
        n.id === contextMenu.targetId
          ? { ...n, style: { ...n.style, opacity: n.style?.opacity === 0.4 ? 1 : 0.4 } }
          : n,
      );
      pushState(updated, edges);
      return updated;
    });
    markDirty();
    setContextMenu(null);
    const target = nodes.find((n: Node) => n.id === contextMenu.targetId);
    message.info(
      target?.style?.opacity === 0.4 ? t('pipelineEditor.msg_node_enabled') : t('pipelineEditor.msg_node_disabled'),
    );
  }, [contextMenu, nodes, edges, setNodes, pushState, markDirty, message, t]);

  /** Delete a single edge */
  const handleDeleteEdge = useCallback(() => {
    if (!contextMenu || contextMenu.type !== 'edge' || !contextMenu.targetId) return;
    setEdges((eds: Edge[]) => {
      const updated = eds.filter((e: Edge) => e.id !== contextMenu.targetId);
      pushState(nodes, updated);
      return updated;
    });
    markDirty();
    setContextMenu(null);
    message.info(t('pipelineEditor.msg_edge_deleted'));
  }, [contextMenu, nodes, edges, setEdges, pushState, markDirty, message, t]);

  /** Cycle edge style: default → dashed → animated → default */
  const handleChangeEdgeStyle = useCallback(() => {
    if (!contextMenu || contextMenu.type !== 'edge' || !contextMenu.targetId) return;
    setEdges((eds: Edge[]) => {
      const updated = eds.map((e: Edge) => {
        if (e.id !== contextMenu.targetId) return e;
        const currentStyle = e.style || {};
        const isDashed = currentStyle.strokeDasharray != null && currentStyle.strokeDasharray !== '';
        const isAnimated = e.animated === true;
        let newEdge: Edge = { ...e };
        if (isAnimated) {
          newEdge = { ...newEdge, animated: false, style: undefined };
        } else if (isDashed) {
          newEdge = { ...newEdge, animated: true, style: { strokeDasharray: undefined } };
        } else {
          newEdge = { ...newEdge, animated: false, style: { strokeDasharray: '5 5' } };
        }
        return newEdge;
      });
      pushState(nodes, updated);
      return updated;
    });
    markDirty();
    setContextMenu(null);
    message.success(t('pipelineEditor.msg_edge_style_changed'));
  }, [contextMenu, nodes, edges, setEdges, pushState, markDirty, message, t]);

  /** Build menu items for node context menu */
  const getNodeMenuItems = (): import('antd').MenuProps['items'] => {
    if (!contextMenu || contextMenu.type !== 'node') return [];
    const targetNode = nodes.find((n) => n.id === contextMenu.targetId);
    const isDisabled = targetNode?.style?.opacity === 0.4;
    return [
      {
        key: 'copy',
        label: t('pipelineEditor.menu_copy_node'),
        icon: <CopyOutlined />,
        onClick: handleCopyNode,
      },
      { type: 'divider' as const },
      {
        key: 'delete',
        label: t('pipelineEditor.menu_delete_node'),
        icon: <DeleteOutlined />,
        danger: true,
        onClick: handleDeleteNode,
      },
      { type: 'divider' as const },
      {
        key: 'toggle-disable',
        label: isDisabled ? t('pipelineEditor.menu_enable_node') : t('pipelineEditor.menu_disable_node'),
        icon: isDisabled ? <PlayCircleOutlined /> : <StopOutlined />,
        onClick: handleToggleDisable,
      },
    ];
  };

  /** Build menu items for edge context menu */
  const getEdgeMenuItems = (): import('antd').MenuProps['items'] => {
    if (!contextMenu || contextMenu.type !== 'edge') return [];
    return [
      {
        key: 'change-style',
        label: t('pipelineEditor.menu_change_edge_style'),
        icon: <LineChartOutlined />,
        onClick: handleChangeEdgeStyle,
      },
      { type: 'divider' as const },
      {
        key: 'delete-edge',
        label: t('pipelineEditor.menu_delete_edge'),
        icon: <DeleteOutlined />,
        danger: true,
        onClick: handleDeleteEdge,
      },
    ];
  };

  useEffect(() => {
    if (!pipelineId) return;
    const id = Number(pipelineId);
    if (isNaN(id)) return;
    const controller = new AbortController();
    setLoading(true);
    pipelineApi
      .getPipeline(id, { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return;
        if (data.graph_data) {
          const { nodes: loadedNodes, edges: loadedEdges } = pipelineToFlow(data.graph_data as unknown as PipelineJSON);
          setNodes(loadedNodes);
          setEdges(loadedEdges);
          clear();
          pushState(loadedNodes, loadedEdges);
        }
        if (data.name) setPipelineName(data.name);
      })
      .catch((err: unknown) => {
        if ((err as Error)?.name === 'AbortError') return;
        message.error(t('pipelineEditor.msg_load_failed'));
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });
    return () => {
      controller.abort();
    };
  }, [pipelineId]);

  const onConnect = useCallback(
    (params: Connection) => {
      setEdges((eds: Edge[]) => addEdge(params, eds));
      markDirty();
    },
    [setEdges, markDirty],
  );

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      const nodeTypeStr = event.dataTransfer.getData('application/reactflow') as PipelineNodeType;
      if (!nodeTypeStr || !flowInstanceRef.current) return;
      const def = NODE_TYPE_LIBRARY.find((n) => n.type === nodeTypeStr);
      const position = flowInstanceRef.current.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });
      const newNode: Node = {
        id: `node_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
        type: 'gafPipeline',
        position,
        data: {
          label: def?.label || nodeTypeStr,
          nodeType: nodeTypeStr,
          description: def?.description || '',
          status: 'pending' as const,
          config: { ...DEFAULT_NODE_CONFIGS[nodeTypeStr] },
        } satisfies GafNodeData,
      };
      setNodes((nds: Node[]) => {
        const updated = [...nds, newNode];
        pushState(updated, edges);
        return updated;
      });
      markDirty();
    },
    [setNodes, edges, pushState, markDirty],
  );

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => setSelectedNode(node), []);

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
    setContextMenu(null);
  }, []);

  const handlePropertyChange = useCallback(
    (config: Record<string, unknown>) => {
      if (!selectedNode) return;
      setNodes((nds: Node[]) => {
        const updated = nds.map((n: Node) => (n.id === selectedNode.id ? { ...n, data: { ...n.data, config } } : n));
        pushState(updated, edges);
        return updated;
      });
      markDirty();
    },
    [selectedNode, setNodes, edges, pushState, markDirty],
  );

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      onNodesChangeBase(changes);
      const hasStructuralChange = changes.some(
        (c) => c.type === 'remove' || (c.type === 'position' && c.dragging === false),
      );
      if (hasStructuralChange && !isRestoringRef.current) {
        setTimeout(() => {
          setNodes((currentNodes: Node[]) => {
            pushState(currentNodes, edges);
            return currentNodes;
          });
          markDirty();
        }, 0);
      }
    },
    [onNodesChangeBase, edges, pushState, markDirty],
  );

  const onEdgesChange = useCallback(
    (changes: import('@xyflow/react').EdgeChange[]) => {
      onEdgesChangeBase(changes);
      const hasRemoval = changes.some((c) => c.type === 'remove');
      if (hasRemoval && !isRestoringRef.current) {
        setTimeout(() => {
          setEdges((currentEdges: Edge[]) => {
            pushState(nodes, currentEdges);
            return currentEdges;
          });
          markDirty();
        }, 0);
      }
    },
    [onEdgesChangeBase, nodes, pushState, markDirty],
  );

  const minimapNodeColor = useCallback((node: Node, token: GlobalToken) => {
    const data = node.data as unknown as GafNodeData | undefined;
    const nType = data?.nodeType;
    if (!nType) return token.colorBorder;
    const cat = NODE_TYPE_CATEGORY[nType];
    return CATEGORY_COLORS[cat] || token.colorBorder;
  }, []);

  const handleSave = useCallback(async () => {
    const savedId = await save(pipelineName, nodes, edges, pipelineId);
    // canExecute 依赖 [pipelineId, pipelineName]，新建保存成功后这两者都不变
    // （pipelineId 来自路由、pipelineName 未改名），effect 不会重跑 →
    // canExecute 会残留 false，导致保存成功仍无法执行。保存成功即代表
    // 后端已存在该 pipeline，直接置为可执行。
    if (savedId !== undefined) {
      setCanExecute(true);
    }
  }, [save, pipelineName, nodes, edges, pipelineId]);

  const handleRecordingComplete = useCallback(
    (pipeline: Record<string, unknown>) => {
      const pipelineData = pipeline.graph_data as Record<string, unknown> | undefined;
      if (pipelineData && Array.isArray(pipelineData.nodes)) {
        const { nodes: newNodes, edges: newEdges } = pipelineToFlow(pipelineData as unknown as PipelineJSON);
        setNodes(newNodes);
        setEdges(newEdges);
        clear();
        pushState(newNodes, newEdges);
        if (pipeline.name) setPipelineName(String(pipeline.name));
        message.success(t('pipelineEditor.msg_recording_converted'));
      } else {
        message.error(t('pipelineEditor.msg_recording_convert_failed'));
      }
    },
    [clear, pushState, setEdges, setNodes, message, t],
  );

  const handleExport = useCallback(() => {
    const json = flowToPipeline(pipelineName, nodes, edges);
    const blob = new Blob([JSON.stringify(json, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${pipelineName || 'pipeline'}.gafpipeline`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    message.success(t('pipelineEditor.msg_export_success'));
  }, [pipelineName, nodes, edges]);

  const [validating, setValidating] = useState(false);
  const [validateModalOpen, setValidateModalOpen] = useState(false);
  const [validateResults, setValidateResults] = useState<pipelineApi.ValidateResult[]>([]);

  const handleValidate = useCallback(async () => {
    setValidating(true);
    try {
      const json = flowToPipeline(pipelineName, nodes, edges);

      // Task 4.41 (P1-24, 2026-07-28): 本地 ajv schema 校验 — 快速拦截结构错误。
      // 失败时直接展示错误, 不调 backend (节省网络请求 + 减少等待)。
      // 与 Editor.tsx:377-388 对齐。
      const localErrors = validatePipelineGraph(json as unknown as Record<string, unknown>);
      if (localErrors.length > 0) {
        setValidateResults(localErrors as unknown as pipelineApi.ValidateResult[]);
        setValidateModalOpen(true);
        message.error(t('pipelineEditor.msg_validate_failed_count', { count: localErrors.length }));
        return;
      }

      // Task 4.38 (P0-10, 2026-07-28): validate API 契约对齐
      // 之前前端期望 `{ valid, errors }` 但后端返回 `{ results: CheckItem[] }`,
      // res.valid 永远 undefined → 始终显示"0 个错误"。现在直接消费 results。
      const res = await pipelineApi.validatePipeline(json as unknown as Record<string, unknown>);
      const results = res.results || [];
      const failCount = results.filter((r) => r.status === 'fail').length;
      const warnCount = results.filter((r) => r.status === 'warn').length;

      if (failCount === 0 && warnCount === 0) {
        setValidateResults([]);
        setValidateModalOpen(true);
        message.success(t('pipelineEditor.msg_validate_passed'));
      } else if (failCount === 0 && warnCount > 0) {
        // 只有 warn, 不阻塞保存但展示警告
        setValidateResults(results);
        setValidateModalOpen(true);
        message.warning(t('pipelineEditor.msg_validate_failed_count', { count: warnCount }));
      } else {
        setValidateResults(results);
        setValidateModalOpen(true);
        message.error(t('pipelineEditor.msg_validate_failed_count', { count: failCount }));
      }
    } catch (error) {
      // Task 4.46 (P2-24): 加 error 参数, 用 resolveErrorMessage 展示具体失败原因
      // (网络错误 / 500 / 超时等), 而非 generic msg_validate_failed
      message.error(resolveErrorMessage(error));
    } finally {
      setValidating(false);
    }
  }, [nodes, edges, pipelineName, t]);

  const [templateModalOpen, setTemplateModalOpen] = useState(false);

  const [jsonSourceModalOpen, setJsonSourceModalOpen] = useState(false);
  const [jsonSourceText, setJsonSourceText] = useState('');

  const handleTemplateSelect = useCallback(
    (template: PipelineTemplate) => {
      if (!template.pipelineData) {
        message.warning(t('pipelineEditor.msg_template_no_data'));
        return;
      }
      setPipelineName(template.name);
      const { nodes: newNodes, edges: newEdges } = pipelineToFlow(template.pipelineData);
      setNodes(newNodes);
      setEdges(newEdges);
      clear();
      pushState(newNodes, newEdges);
      message.success(t('pipelineEditor.msg_template_loaded', { name: template.name }));
    },
    [setNodes, setEdges, clear, pushState, t],
  );

  const handleImport = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleOpenJsonSource = useCallback(() => {
    const json = flowToPipeline(pipelineName, nodes, edges);
    setJsonSourceText(JSON.stringify(json, null, 2));
    setJsonSourceModalOpen(true);
  }, [pipelineName, nodes, edges]);

  const handleApplyJsonSource = useCallback(() => {
    try {
      const parsed = JSON.parse(jsonSourceText);
      const isPipelineFormat = parsed.nodes && Array.isArray(parsed.nodes) && parsed.nodes[0]?.type;
      if (isPipelineFormat) {
        const { nodes: newNodes, edges: newEdges } = pipelineToFlow(parsed);
        setNodes(newNodes);
        setEdges(newEdges);
        clear();
        pushState(newNodes, newEdges);
      } else if (parsed.nodes) {
        setNodes(parsed.nodes);
        if (parsed.edges) setEdges(parsed.edges);
        clear();
        pushState(parsed.nodes, parsed.edges || []);
      }
      if (parsed.name) setPipelineName(parsed.name);
      markDirty();
      setJsonSourceModalOpen(false);
      message.success(t('pipelineEditor.msg_source_applied'));
    } catch {
      message.error(t('pipelineEditor.msg_json_invalid'));
    }
  }, [jsonSourceText, setNodes, setEdges, clear, pushState, markDirty, message, t]);

  const handleFileChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        try {
          const json = JSON.parse(ev.target?.result as string);
          const isPipelineFormat = json.nodes && Array.isArray(json.nodes) && json.nodes[0]?.type;
          if (isPipelineFormat) {
            const { nodes: newNodes, edges: newEdges } = pipelineToFlow(json);
            setNodes(newNodes);
            setEdges(newEdges);
            clear();
            pushState(newNodes, newEdges);
          } else if (json.nodes) {
            setNodes(json.nodes);
            if (json.edges) setEdges(json.edges);
            clear();
            pushState(json.nodes, json.edges || []);
          }
          if (json.name) setPipelineName(json.name);
          message.success(t('pipelineEditor.msg_import_success'));
        } catch {
          message.error(t('pipelineEditor.msg_import_failed'));
        }
      };
      reader.readAsText(file);
      event.target.value = '';
    },
    [setNodes, setEdges, clear, pushState, t],
  );

  const handleUndo = useCallback(() => {
    const entry = undo();
    if (entry) {
      isRestoringRef.current = true;
      setNodes(entry.nodes);
      setEdges(entry.edges);
      requestAnimationFrame(() => {
        isRestoringRef.current = false;
      });
    }
  }, [undo, setNodes, setEdges]);

  const handleRedo = useCallback(() => {
    const entry = redo();
    if (entry) {
      isRestoringRef.current = true;
      setNodes(entry.nodes);
      setEdges(entry.edges);
      requestAnimationFrame(() => {
        isRestoringRef.current = false;
      });
    }
  }, [redo, setNodes, setEdges]);

  const handleDelete = useCallback(() => {
    setNodes((nds: Node[]) => {
      const updated = nds.filter((n: Node) => !n.selected);
      pushState(updated, edges);
      return updated;
    });
    setEdges((eds: Edge[]) => {
      const remaining = eds.filter((e: Edge) => !e.selected);
      return remaining;
    });
    setSelectedNode(null);
    markDirty();
  }, [setNodes, setEdges, edges, pushState, markDirty]);

  usePipelineKeyboard({
    nodes,
    edges,
    setNodes: (newNodes) => {
      setNodes(newNodes);
      pushState(newNodes, edges);
    },
    setEdges: (newEdges) => {
      setEdges(newEdges);
      pushState(nodes, newEdges);
    },
    onSave: handleSave,
    onUndo: handleUndo,
    onRedo: handleRedo,
    onDelete: handleDelete,
    canUndo,
    canRedo,
  });

  const selectedNodeData = selectedNode?.data as GafNodeData | undefined;

  const saveStatusText: Record<string, string> = {
    saved: t('pipelineEditor.status_saved'),
    saving: t('pipelineEditor.status_saving'),
    unsaved: t('pipelineEditor.status_unsaved'),
    error: t('pipelineEditor.status_error'),
  };

  // F010 fix: map lookup replaces 4-level nested ternary for Antd Badge status
  const saveBadgeStatus: Record<string, 'success' | 'processing' | 'error' | 'warning'> = {
    saved: 'success',
    saving: 'processing',
    error: 'error',
    unsaved: 'warning',
  };

  return (
    <div className="gaf-flex-col gaf-position-relative" style={{ height: '100vh', background: token.colorBgBase }}>
      <RecordingPanel onRecordingComplete={handleRecordingComplete} />
      <div
        className="gaf-toolbar gaf-flex-shrink-0"
        style={{
          minHeight: 48,
          borderBottom: `1px solid ${token.colorBorder}`,
        }}
      >
        <Input
          size="small"
          className="gaf-w-200 gaf-flex-shrink-0"
          value={pipelineName}
          onChange={(e) => {
            setPipelineName(e.target.value);
            markDirty();
          }}
          disabled={readonly}
          placeholder={t('pipelineEditor.placeholder_pipeline_name')}
          aria-label={t('pipelineEditor.placeholder_pipeline_name')}
          name="pipeline_name"
          autoComplete="off"
        />
        <div className="gaf-toolbar-divider" />
        <div className="gaf-toolbar-group">
          <Tooltip title={t('pipelineEditor.tooltip_save')}>
            <Button
              size="small"
              icon={saveStatusIcon[saveStatus] || <SaveOutlined />}
              onClick={handleSave}
              disabled={readonly || saveStatus === 'saving'}
            >
              {t('pipelineEditor.btn_save')}
            </Button>
          </Tooltip>
        </div>
        <div className="gaf-toolbar-divider" />
        <div className="gaf-toolbar-group">
          <Tooltip title={t('pipelineEditor.tooltip_undo')}>
            <Button size="small" icon={<UndoOutlined />} onClick={handleUndo} disabled={readonly || !canUndo}>
              {t('pipelineEditor.btn_undo')}
            </Button>
          </Tooltip>
          <Tooltip title={t('pipelineEditor.tooltip_redo')}>
            <Button size="small" icon={<RedoOutlined />} onClick={handleRedo} disabled={readonly || !canRedo}>
              {t('pipelineEditor.btn_redo')}
            </Button>
          </Tooltip>
          <Tooltip title={t('pipelineEditor.tooltip_delete')}>
            <Button
              size="small"
              danger
              icon={<DeleteOutlined />}
              aria-label={t('pipelineEditor.tooltip_delete')}
              onClick={handleDelete}
              disabled={readonly}
            />
          </Tooltip>
        </div>
        <div className="gaf-toolbar-divider" />
        <div className="gaf-toolbar-group">
          <Tooltip title={t('pipelineEditor.tooltip_import')}>
            <Button size="small" icon={<UploadOutlined />} onClick={handleImport}>
              {t('pipelineEditor.btn_import')}
            </Button>
          </Tooltip>
          <Tooltip title={t('pipelineEditor.tooltip_export')}>
            <Button size="small" icon={<DownloadOutlined />} onClick={handleExport}>
              {t('pipelineEditor.btn_export')}
            </Button>
          </Tooltip>
          <Tooltip title={t('pipelineEditor.tooltip_source')}>
            <Button size="small" icon={<CodeOutlined />} onClick={handleOpenJsonSource} disabled={readonly}>
              {t('pipelineEditor.btn_source')}
            </Button>
          </Tooltip>
        </div>
        <div className="gaf-toolbar-divider" />
        <div className="gaf-toolbar-group">
          <Tooltip title={t('pipelineEditor.tooltip_validate')}>
            <Button
              size="small"
              icon={validating ? <LoadingOutlined /> : <SafetyCertificateOutlined />}
              onClick={handleValidate}
              loading={validating}
            >
              {t('pipelineEditor.btn_validate')}
            </Button>
          </Tooltip>
          <Tooltip title={t('pipelineEditor.tooltip_template')}>
            <Button size="small" icon={<AppstoreAddOutlined />} onClick={() => setTemplateModalOpen(true)}>
              {t('pipelineEditor.btn_template')}
            </Button>
          </Tooltip>
          <Tooltip title={t('pipelineEditor.tooltip_preview')}>
            <Button
              size="small"
              type={showPreview ? 'primary' : 'default'}
              icon={<EyeOutlined />}
              onClick={() => setShowPreview(!showPreview)}
            >
              {t('pipelineEditor.btn_preview')}
            </Button>
          </Tooltip>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".json,.gafpipeline"
          className="gaf-hidden"
          onChange={handleFileChange}
        />
        <div className="gaf-toolbar-spacer" />
        <div className="gaf-toolbar-group">
          <span className="gaf-text-xs" style={{ color: token.colorTextTertiary, whiteSpace: 'nowrap' }}>
            {t('pipelineEditor.lbl_device')}
          </span>
          <Select
            size="small"
            style={{ width: 180 }}
            placeholder={t('pipelineEditor.placeholder_select_device')}
            options={deviceOptions}
            value={selectedDevice}
            onChange={setSelectedDevice}
            allowClear
          />
          <Tooltip
            title={canExecute ? t('pipelineEditor.tooltip_execute') : t('pipelineEditor.tooltip_execute_disabled')}
          >
            <Button
              size="small"
              type="primary"
              icon={executing ? <LoadingOutlined spin /> : <PlayCircleOutlined />}
              onClick={handleRunPipeline}
              disabled={executing || !canExecute || readonly}
              loading={executing}
            >
              {t('pipelineEditor.btn_execute')}
            </Button>
          </Tooltip>
        </div>
        <div className="gaf-toolbar-divider" />
        <Segmented
          size="small"
          value={connectionMode ? 'connect' : 'select'}
          onChange={(val) => setConnectionMode(val === 'connect')}
          options={[
            { label: t('pipelineEditor.segmented_select'), value: 'select' },
            { label: t('pipelineEditor.segmented_connect'), value: 'connect' },
          ]}
        />
      </div>

      <div className="gaf-flex-1 gaf-overflow-hidden">
        <Group orientation="horizontal">
          <Panel defaultSize="20%" minSize="18%" maxSize="30%">
            <div className="gaf-overflow-auto gaf-h-full" style={{ borderRight: `1px solid ${token.colorBorder}` }}>
              <NodeTypeLibrary readonly={readonly} />
            </div>
          </Panel>
          <Separator style={{ width: 4, background: token.colorBorder, cursor: 'col-resize' }} />
          <Panel defaultSize="60%" minSize="30%">
            <div className="gaf-w-full gaf-h-full gaf-position-relative">
              {loading && (
                <div
                  className="gaf-flex-center gaf-justify-center gaf-position-absolute"
                  style={{ inset: 0, zIndex: 10, background: 'rgba(255,255,255,0.7)' }}
                >
                  <Spin description={t('pipelineEditor.loading')} />
                </div>
              )}
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={readonly ? undefined : onNodesChange}
                onEdgesChange={readonly ? undefined : onEdgesChange}
                onConnect={readonly ? undefined : onConnect}
                onDragOver={onDragOver}
                onDrop={readonly ? undefined : onDrop}
                onNodeClick={onNodeClick}
                onPaneClick={onPaneClick}
                onNodeContextMenu={readonly ? undefined : onNodeContextMenu}
                onEdgeContextMenu={readonly ? undefined : onEdgeContextMenu}
                onInit={(instance: ReactFlowInstance) => {
                  flowInstanceRef.current = instance;
                }}
                nodeTypes={nodeTypes}
                defaultEdgeOptions={defaultEdgeOptions}
                snapToGrid
                snapGrid={[20, 20]}
                fitView
                deleteKeyCode={null}
                nodesDraggable={!readonly}
                nodesConnectable={!readonly && connectionMode}
                elementsSelectable={!readonly}
                connectionMode={ConnectionMode.Loose}
              >
                <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
                <Controls position="bottom-left" />
                <MiniMap
                  position="bottom-right"
                  nodeColor={(node) => minimapNodeColor(node, token)}
                  style={{ width: 150, height: 100 }}
                />
              </ReactFlow>
            </div>
          </Panel>
          <Separator style={{ width: 4, background: token.colorBorder, cursor: 'col-resize' }} />
          <Panel defaultSize={showPreview ? '15%' : '20%'} minSize="15%" maxSize="35%">
            <div className="gaf-overflow-auto gaf-h-full" style={{ borderLeft: `1px solid ${token.colorBorder}` }}>
              {!showPreview && (
                <NodePropertyPanel
                  nodeId={selectedNode?.id}
                  nodeType={selectedNodeData?.nodeType ?? null}
                  config={selectedNodeData?.config}
                  onChange={readonly ? undefined : handlePropertyChange}
                  onRequestScreenshot={() => message.info(t('pipelineEditor.msg_select_device_first'))}
                />
              )}
              {showPreview && <PreviewPanel />}
            </div>
          </Panel>
        </Group>
      </div>

      <div
        className="gaf-flex-center gaf-gap-md gaf-px-lg gaf-overflow-hidden gaf-flex-shrink-0"
        style={{ height: 28, borderTop: `1px solid ${token.colorBorder}`, background: token.colorBgLayout }}
      >
        <Badge status={saveBadgeStatus[saveStatus] || 'warning'} />
        <Typography.Text className="gaf-text-xxs" style={{ color: token.colorTextTertiary }}>
          {saveStatusText[saveStatus]}
          {lastSavedAt && saveStatus === 'saved' && ` (${lastSavedAt.toLocaleTimeString(getLocale())})`}
        </Typography.Text>
        <Typography.Text className="gaf-text-xxs" style={{ color: token.colorTextTertiary }}>
          {t('pipelineEditor.lbl_nodes', { count: nodes.length })}
        </Typography.Text>
        <Typography.Text className="gaf-text-xxs" style={{ color: token.colorTextTertiary }}>
          {t('pipelineEditor.lbl_edges', { count: edges.length })}
        </Typography.Text>
        {selectedNodeData && (
          <Typography.Text className="gaf-text-xxs" style={{ color: token.colorTextTertiary }}>
            {t('pipelineEditor.lbl_selected', { label: selectedNodeData.label, type: selectedNodeData.nodeType })}
          </Typography.Text>
        )}
        {executeResult && (
          <Typography.Text className="gaf-text-xxs gaf-ml-lg" style={{ color: token.colorTextTertiary }}>
            {executeResult}
          </Typography.Text>
        )}
      </div>

      <TemplatePicker
        open={templateModalOpen}
        onClose={() => setTemplateModalOpen(false)}
        onSelect={handleTemplateSelect}
      />

      {/* JSON Source Editor Modal (P-003 D3) */}
      <Modal
        title={t('pipelineEditor.modal_json_title')}
        open={jsonSourceModalOpen}
        onCancel={() => setJsonSourceModalOpen(false)}
        footer={null}
        width="80%"
        style={{ top: 20 }}
        styles={{ body: { height: '75vh', padding: 0 } }}
      >
        <div className="gaf-flex-col gaf-h-full">
          <div
            className="gaf-flex gaf-gap-sm gaf-py-sm gaf-px-lg"
            style={{ borderBottom: `1px solid ${token.colorBorder}`, justifyContent: 'flex-end' }}
          >
            <Button size="small" onClick={() => setJsonSourceModalOpen(false)}>
              {t('pipelineEditor.modal_json_close')}
            </Button>
            <Button size="small" type="primary" icon={<CodeOutlined />} onClick={handleApplyJsonSource}>
              {t('pipelineEditor.modal_json_apply')}
            </Button>
          </div>
          <div className="gaf-flex-1">
            <GafCodeEditor
              value={jsonSourceText}
              onChange={(val) => setJsonSourceText(val || '')}
              language="json"
              height="100%"
              options={{
                minimap: { enabled: true, scale: 0.5 },
                wordWrap: 'on',
                formatOnPaste: true,
                formatOnType: true,
              }}
            />
          </div>
        </div>
      </Modal>

      <Modal
        title={t('pipelineEditor.modal_validate_title')}
        open={validateModalOpen}
        onCancel={() => setValidateModalOpen(false)}
        footer={null}
        width={640}
      >
        {validateResults.length === 0 ? (
          <div className="gaf-p-xl gaf-text-center" style={{ color: token.colorSuccess }}>
            <span aria-hidden="true">
              <CheckCircleOutlined className="gaf-mb-sm" style={{ fontSize: 48 }} />
            </span>
            <div>{t('pipelineEditor.modal_validate_passed')}</div>
          </div>
        ) : (
          <div className="gaf-overflow-auto" style={{ maxHeight: 400 }}>
            {validateResults.map((r, i) => {
              // F010 fix: map lookup replaces nested ternary for validate result colors/tags
              const validateStyle = VALIDATE_RESULT_STYLE[r.status] || VALIDATE_RESULT_STYLE.pass;
              const validateTagColor = VALIDATE_RESULT_TAG_COLOR[r.status] || 'success';
              const validateTagLabel = t(VALIDATE_RESULT_TAG_LABEL[r.status] || 'pipelineEditor.tag_pass');
              return (
                <div
                  key={`res-${i}-${r.status}`}
                  className="gaf-py-sm gaf-px-md gaf-mb-sm gaf-radius-md"
                  style={{ background: validateStyle.bg, border: `1px solid ${validateStyle.border}` }}
                >
                  <div className="gaf-flex-center gaf-gap-sm gaf-mb-xs">
                    <Tag color={validateTagColor}>{validateTagLabel}</Tag>
                    <Typography.Text strong>{r.check}</Typography.Text>
                  </div>
                  <Typography.Text className="gaf-text-xs" style={{ color: token.colorTextSecondary }}>
                    {r.message}
                  </Typography.Text>
                  {r.node_id && <Tag className="gaf-ml-sm">{r.node_id}</Tag>}
                  {r.suggestion && (
                    <div className="gaf-mt-xs gaf-text-xs" style={{ color: token.colorPrimary }}>
                      {r.suggestion}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Modal>

      {/* Right-click Context Menu */}
      {contextMenu && (
        <Dropdown
          menu={{
            items: contextMenu.type === 'node' ? getNodeMenuItems() : getEdgeMenuItems(),
          }}
          trigger={['contextMenu']}
          open={!!contextMenu}
          onOpenChange={(open) => {
            if (!open) setContextMenu(null);
          }}
        >
          <div
            style={{
              position: 'fixed',
              left: contextMenu.x,
              top: contextMenu.y,
              width: 1,
              height: 1,
              pointerEvents: 'none',
              zIndex: 9999,
            }}
          />
        </Dropdown>
      )}
    </div>
  );
}

export function PipelineEditorPage({ readonly }: PipelineEditorPageProps) {
  const { id } = useParams<{ id: string }>();
  return (
    <ReactFlowProvider>
      <PipelineEditorInner pipelineId={id} readonly={readonly} />
    </ReactFlowProvider>
  );
}
