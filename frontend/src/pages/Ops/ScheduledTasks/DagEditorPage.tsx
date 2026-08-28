/**
 * DAG task chain editor — based on React Flow drag style multi task orchestration UI
 * allow user will multiple Task organization sequential row / and row DAG depends on graph
 *
 * TD-110: nodes can be either Task or Pipeline (node_type discriminator).
 * Tasks render with NodeIndexOutlined (blue), Pipelines with
 * ApartmentOutlined (purple). The add Modal uses Tabs to switch between
 * Task list and Pipeline list.
 *
 * TD-114: drag-and-drop from sidebar to canvas. Sidebar lists Tasks +
 * Pipelines (always visible, no need to open Modal). Canvas accepts
 * onDrop and creates a node at the drop position. Uses @xyflow/react's
 * native HTML5 drag support — no extra library required.
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import {
  Button,
  Input,
  Tooltip,
  App,
  Typography,
  Badge,
  Spin,
  Modal,
  Tag,
  Tabs,
  theme,
  message as antMessage,
  Empty,
} from 'antd';
import {
  SaveOutlined,
  DeleteOutlined,
  PlusOutlined,
  NodeIndexOutlined,
  ApartmentOutlined,
  DragOutlined,
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
  Panel,
} from '@xyflow/react';
import type { Node, Edge, Connection, ReactFlowInstance } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { TaskChain, DagData, DagNode, Task } from '@/types/models';
import * as taskChainApi from '@/api/tasks';
import { fetchTasks } from '@/api/tasks';
import { listPipelines, type PipelineSummary } from '@/api/pipelines';
import { useTranslation } from '@/i18n';

/** C-class business palette: node-type accent colors (TD-330 spec-94).
 *  #722ed1 = pipeline purple (antd has no direct token), #1677ff = antd
 *  colorPrimary default (kept as constant so getNodeVisual works at module
 *  level without useToken). */
const COLOR_PIPELINE = '#722ed1';
const COLOR_TASK = '#1677ff';

/** Resolve which name to show for a DAG node (TD-110: task or pipeline). */
function getNodeDisplayName(data: DagNode['data']): string {
  if (data?.node_type === 'pipeline') {
    return data.pipeline_name || data.label;
  }
  return data?.task_name || data.label;
}

/** Resolve the icon + accent color for a DAG node based on node_type. */
function getNodeVisual(data: DagNode['data']): { icon: React.ReactNode; color: string } {
  if (data?.node_type === 'pipeline') {
    return {
      icon: <ApartmentOutlined className="gaf-text-md" style={{ color: COLOR_PIPELINE }} />,
      color: COLOR_PIPELINE,
    };
  }
  return { icon: <NodeIndexOutlined className="gaf-text-md" style={{ color: COLOR_TASK }} />, color: COLOR_TASK };
}

/** Custom DAG node component — renders Task (blue) or Pipeline (purple). */
function DagTaskNode({ data }: { data: DagNode['data'] }) {
  const { token } = theme.useToken();
  const { icon, color } = getNodeVisual(data);
  const displayName = getNodeDisplayName(data);
  return (
    <div
      className="gaf-py-md gaf-px-lg gaf-radius-lg"
      style={{
        background: token.colorBgContainer,
        border: `2px solid ${color}`,
        minWidth: 180,
        maxWidth: 260,
        boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
      }}
    >
      <div className="gaf-flex-center gaf-gap-sm gaf-mb-xs">
        {icon}
        <Typography.Text strong className="gaf-text-sm">
          {displayName}
        </Typography.Text>
      </div>
      <Typography.Text type="secondary" className="gaf-text-xs">
        {data?.node_type === 'pipeline' ? 'Pipeline' : 'Task'}
      </Typography.Text>
    </div>
  );
}

const nodeTypes = { dagTask: DagTaskNode };

const defaultEdgeOptions = {
  animated: true,
  type: 'smoothstep' as const,
  markerEnd: { type: MarkerType.ArrowClosed },
  style: { strokeWidth: 2 },
};

/** TD-114: drag payload MIME type — @xyflow/react convention. */
const DRAG_MIME = 'application/reactflow';

/** TD-114: sidebar drag payload. */
interface DragPayload {
  kind: 'task' | 'pipeline';
  id: number;
  name: string;
}

/** TD-114: serialize drag payload into the dataTransfer. */
function setDragPayload(e: React.DragEvent, payload: DragPayload) {
  e.dataTransfer.setData(DRAG_MIME, JSON.stringify(payload));
  e.dataTransfer.effectAllowed = 'move';
}

/** TD-114: parse drag payload from the dataTransfer. Returns null if absent/invalid. */
function getDragPayload(e: React.DragEvent): DragPayload | null {
  const raw = e.dataTransfer.getData(DRAG_MIME);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as DragPayload;
    if (parsed.kind !== 'task' && parsed.kind !== 'pipeline') return null;
    if (typeof parsed.id !== 'number' || typeof parsed.name !== 'string') return null;
    return parsed;
  } catch {
    return null;
  }
}

interface DagEditorProps {
  chainId?: number;
  onSave?: (chain: TaskChain) => void;
}

function DagEditorInner({ chainId, onSave }: DagEditorProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const t = useTranslation();
  const { token } = theme.useToken();
  const [chainName, setChainName] = useState(t('scheduledTasks.chain.default_name_editor'));
  const [chainDescription, setChainDescription] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [pipelines, setPipelines] = useState<PipelineSummary[]>([]);
  const [addNodeModalOpen, setAddNodeModalOpen] = useState(false);
  const [addNodeTab, setAddNodeTab] = useState<'task' | 'pipeline'>('task');
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  /** TD-114: sidebar collapsed state — toggle to maximize canvas area. */
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const flowRef = useRef<{ screenToFlowPosition: (p: { x: number; y: number }) => { x: number; y: number } } | null>(
    null,
  );
  const { message } = App.useApp();

  // Load task + pipeline lists for adding to DAG (TD-110: both kinds).
  useEffect(() => {
    fetchTasks({ page: 1, page_size: 200 })
      .then((res) => setTasks(res.results || []))
      .catch(() => antMessage.error(t('scheduledTasks.message.load_tasks_failed')));
    listPipelines({ page: 1, page_size: 200 })
      .then((res) => setPipelines(res.results || []))
      .catch(() => antMessage.error(t('scheduledTasks.message.load_tasks_failed')));
  }, []);

  // Load existing chain data
  useEffect(() => {
    if (!chainId) return;
    setLoading(true);
    taskChainApi
      .fetchTaskChain(chainId)
      .then((chain) => {
        setChainName(chain.name);
        setChainDescription(chain.description || '');
        if (chain.dag_data?.nodes) {
          const flowNodes = chain.dag_data.nodes.map((n) => ({
            ...n,
            type: (n.type as string) || 'dagTask',
          }));
          setNodes(flowNodes);
          setEdges(chain.dag_data.edges || []);
        }
      })
      .catch(() => message.error(t('scheduledTasks.message.load_chain_failed')))
      .finally(() => setLoading(false));
  }, [chainId]);

  const onConnect = useCallback(
    (params: Connection) => {
      setEdges((eds: Edge[]) => addEdge({ ...params, ...defaultEdgeOptions }, eds));
    },
    [setEdges],
  );

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => setSelectedNode(node), []);

  const onPaneClick = useCallback(() => setSelectedNode(null), []);

  /** TD-114: unified node-creation helper shared by Modal click + drag-drop.
   *
   * Both the legacy "click in Modal" path and the new "drag from sidebar"
   * path funnel through here so node id/data shape stays consistent.
   */
  const addNodeAtPosition = useCallback(
    (payload: { kind: 'task' | 'pipeline'; id: number; name: string }, position: { x: number; y: number }) => {
      const isPipeline = payload.kind === 'pipeline';
      const newNode: Node = {
        id: `${payload.kind}_${payload.id}_${Date.now()}`,
        type: 'dagTask',
        position,
        data: isPipeline
          ? {
              label: payload.name,
              node_type: 'pipeline',
              pipeline_id: payload.id,
              pipeline_name: payload.name,
            }
          : {
              label: payload.name,
              node_type: 'task',
              task_id: payload.id,
              task_name: payload.name,
            },
      };
      setNodes((nds: Node[]) => [...nds, newNode]);
    },
    [setNodes],
  );

  /** Add a Task as a new DAG node (legacy Modal-click path, node_type='task'). */
  const handleAddTask = useCallback(
    (taskId: number, taskName: string) => {
      const position = flowRef.current
        ? flowRef.current.screenToFlowPosition({ x: 300 + Math.random() * 200, y: 200 + Math.random() * 200 })
        : { x: 300 + nodes.length * 250, y: 200 };
      addNodeAtPosition({ kind: 'task', id: taskId, name: taskName }, position);
      setAddNodeModalOpen(false);
    },
    [nodes.length, addNodeAtPosition],
  );

  /** Add a Pipeline as a new DAG node (Modal-click path, node_type='pipeline'). */
  const handleAddPipeline = useCallback(
    (pipelineId: number, pipelineName: string) => {
      const position = flowRef.current
        ? flowRef.current.screenToFlowPosition({ x: 300 + Math.random() * 200, y: 200 + Math.random() * 200 })
        : { x: 300 + nodes.length * 250, y: 200 };
      addNodeAtPosition({ kind: 'pipeline', id: pipelineId, name: pipelineName }, position);
      setAddNodeModalOpen(false);
    },
    [nodes.length, addNodeAtPosition],
  );

  /** TD-114: allow drop on canvas — preventDefault is required to enable drop. */
  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  }, []);

  /** TD-114: handle drop — parse payload, resolve flow position, add node. */
  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const payload = getDragPayload(e);
      if (!payload) return;
      if (!flowRef.current) return;
      const position = flowRef.current.screenToFlowPosition({ x: e.clientX, y: e.clientY });
      addNodeAtPosition(payload, position);
    },
    [addNodeAtPosition],
  );

  /** Delete selected node */
  const handleDeleteNode = useCallback(() => {
    if (!selectedNode) return;
    setNodes((nds: Node[]) => nds.filter((n: Node) => n.id !== selectedNode.id));
    setEdges((eds: Edge[]) => eds.filter((e: Edge) => e.source !== selectedNode.id && e.target !== selectedNode.id));
    setSelectedNode(null);
    message.info(t('scheduledTasks.message.node_deleted'));
  }, [selectedNode, setNodes, setEdges, message, t]);

  /** Save chain to backend */
  const handleSave = useCallback(async () => {
    if (!chainName.trim()) {
      message.warning(t('scheduledTasks.message.chain_name_required'));
      return;
    }
    setSaving(true);
    const dagData: DagData = {
      nodes: nodes.map((n) => ({
        id: n.id,
        position: n.position,
        data: n.data as DagNode['data'],
      })),
      edges: edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
      })),
    };

    try {
      let chain: TaskChain;
      if (chainId) {
        chain = await taskChainApi.updateTaskChain(chainId, {
          name: chainName,
          description: chainDescription,
          dag_data: dagData,
        });
      } else {
        chain = await taskChainApi.createTaskChain({
          name: chainName,
          description: chainDescription,
          dag_data: dagData as unknown as Record<string, unknown>,
          is_enabled: true,
        });
      }
      message.success(t('scheduledTasks.message.save_success'));
      onSave?.(chain);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string };
      const detail = axiosErr?.response?.data?.detail || axiosErr?.message || t('scheduledTasks.message.save_failed');
      message.error(detail);
    } finally {
      setSaving(false);
    }
  }, [chainId, chainName, chainDescription, nodes, edges, onSave, message, t]);

  return (
    <div className="gaf-flex-col gaf-h-full">
      {/* Toolbar */}
      <div
        className="gaf-toolbar"
        style={{
          minHeight: 48,
          borderBottom: `1px solid ${token.colorBorderSecondary}`,
          background: token.colorBgContainer,
        }}
      >
        <Input
          size="small"
          className="gaf-w-md"
          value={chainName}
          onChange={(e) => setChainName(e.target.value)}
          placeholder={t('scheduledTasks.chain.name_placeholder')}
          aria-label={t('scheduledTasks.chain.name_placeholder')}
          name="chain_name"
        />
        <Input
          size="small"
          style={{ width: 280 }}
          value={chainDescription}
          onChange={(e) => setChainDescription(e.target.value)}
          placeholder={t('scheduledTasks.chain.description_placeholder')}
          aria-label={t('scheduledTasks.chain.description_placeholder')}
          name="chain_description"
        />
        <Tooltip title={t('scheduledTasks.chain.tooltip.add_task')}>
          <Button
            size="small"
            icon={<PlusOutlined />}
            onClick={() => {
              setAddNodeTab('task');
              setAddNodeModalOpen(true);
            }}
          >
            {t('scheduledTasks.button.add_node')}
          </Button>
        </Tooltip>
        <Tooltip title={t('scheduledTasks.chain.tooltip.toggle_sidebar')}>
          <Button
            size="small"
            icon={<DragOutlined />}
            type={sidebarCollapsed ? 'default' : 'primary'}
            onClick={() => setSidebarCollapsed((v) => !v)}
            aria-label={t('scheduledTasks.chain.tooltip.toggle_sidebar')}
          >
            {t('scheduledTasks.button.toggle_sidebar')}
          </Button>
        </Tooltip>
        {selectedNode && (
          <Tooltip title={t('scheduledTasks.chain.tooltip.delete_node')}>
            <Button size="small" danger icon={<DeleteOutlined />} onClick={handleDeleteNode}>
              {t('scheduledTasks.button.delete_node')}
            </Button>
          </Tooltip>
        )}
        <div className="gaf-toolbar-spacer" />
        <Tooltip title={t('scheduledTasks.chain.tooltip.save')}>
          <Button
            size="small"
            type="primary"
            icon={saving ? <Spin size="small" /> : <SaveOutlined />}
            onClick={handleSave}
            loading={saving}
          >
            {t('scheduledTasks.button.save')}
          </Button>
        </Tooltip>
      </div>

      {/* TD-114: middle area = sidebar (draggable lists) + canvas (drop target) */}
      <div className="gaf-flex gaf-overflow-hidden" style={{ flex: 1 }}>
        {!sidebarCollapsed && (
          <div
            className="gaf-flex-col gaf-overflow-auto gaf-flex-shrink-0"
            style={{
              width: 260,
              borderRight: `1px solid ${token.colorBorderSecondary}`,
              background: token.colorBgLayout,
            }}
            data-testid="dag-sidebar"
          >
            <div className="gaf-p-md" style={{ borderBottom: `1px solid ${token.colorBorderSecondary}` }}>
              <Typography.Text strong className="gaf-text-sm">
                <DragOutlined className="gaf-mr-xs" />
                {t('scheduledTasks.sidebar.title')}
              </Typography.Text>
              <Typography.Paragraph type="secondary" className="gaf-text-xs gaf-mt-xs gaf-mb-0">
                {t('scheduledTasks.sidebar.hint')}
              </Typography.Paragraph>
            </div>
            <div className="gaf-p-md">
              <Typography.Text type="secondary" className="gaf-text-xs gaf-flex-center gaf-gap-xs">
                <NodeIndexOutlined style={{ color: COLOR_TASK }} />
                {t('scheduledTasks.sidebar.section_tasks')}
              </Typography.Text>
              <div className="gaf-flex-col gaf-gap-sm gaf-mt-sm">
                {tasks.length === 0 ? (
                  <Typography.Text type="secondary" className="gaf-text-xs">
                    {t('scheduledTasks.empty.no_tasks')}
                  </Typography.Text>
                ) : (
                  tasks.map((task) => (
                    <div
                      key={task.id}
                      draggable
                      onDragStart={(e) => setDragPayload(e, { kind: 'task', id: Number(task.id), name: task.name })}
                      onClick={() => handleAddTask(Number(task.id), task.name)}
                      className="gaf-flex-between gaf-radius-md gaf-cursor-pointer"
                      style={{
                        padding: '8px 10px',
                        background: token.colorBgContainer,
                        border: `1px solid ${token.colorBorderSecondary}`,
                        userSelect: 'none',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.borderColor = COLOR_TASK)}
                      onMouseLeave={(e) => (e.currentTarget.style.borderColor = token.colorBorderSecondary)}
                      title={t('scheduledTasks.sidebar.drag_hint')}
                    >
                      <Typography.Text className="gaf-text-xs" ellipsis style={{ maxWidth: 180 }}>
                        {task.name}
                      </Typography.Text>
                      <Tag color={task.is_enabled ? 'green' : 'default'} className="gaf-text-xxs">
                        {task.is_enabled ? t('scheduledTasks.tag.enabled') : t('scheduledTasks.tag.disabled')}
                      </Tag>
                    </div>
                  ))
                )}
              </div>
            </div>
            <div className="gaf-p-md gaf-pt-0">
              <Typography.Text type="secondary" className="gaf-text-xs gaf-flex-center gaf-gap-xs">
                <ApartmentOutlined style={{ color: COLOR_PIPELINE }} />
                {t('scheduledTasks.sidebar.section_pipelines')}
              </Typography.Text>
              <div className="gaf-flex-col gaf-gap-sm gaf-mt-sm">
                {pipelines.length === 0 ? (
                  <Typography.Text type="secondary" className="gaf-text-xs">
                    {t('scheduledTasks.empty.no_pipelines')}
                  </Typography.Text>
                ) : (
                  pipelines.map((pipe) => (
                    <div
                      key={pipe.id}
                      draggable
                      onDragStart={(e) => setDragPayload(e, { kind: 'pipeline', id: Number(pipe.id), name: pipe.name })}
                      onClick={() => handleAddPipeline(Number(pipe.id), pipe.name)}
                      className="gaf-flex-between gaf-radius-md gaf-cursor-pointer"
                      style={{
                        padding: '8px 10px',
                        background: token.colorBgContainer,
                        border: `1px solid ${token.colorBorderSecondary}`,
                        userSelect: 'none',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.borderColor = COLOR_PIPELINE)}
                      onMouseLeave={(e) => (e.currentTarget.style.borderColor = token.colorBorderSecondary)}
                      title={t('scheduledTasks.sidebar.drag_hint')}
                    >
                      <Typography.Text className="gaf-text-xs" ellipsis style={{ maxWidth: 180 }}>
                        <ApartmentOutlined style={{ color: COLOR_PIPELINE, marginRight: 4 }} />
                        {pipe.name}
                      </Typography.Text>
                      <Tag color="purple" className="gaf-text-xxs">
                        v{pipe.version}
                      </Tag>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}

        {/* React Flow canvas — TD-114 drop target */}
        <div className="gaf-flex-1 gaf-overflow-hidden" onDrop={onDrop} onDragOver={onDragOver}>
          {loading ? (
            <div className="gaf-flex-center gaf-justify-center gaf-h-full">
              <Spin description={t('scheduledTasks.status.loading')} />
            </div>
          ) : (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeClick={onNodeClick}
              onPaneClick={onPaneClick}
              onInit={(instance: ReactFlowInstance) => {
                flowRef.current = instance;
              }}
              nodeTypes={nodeTypes}
              defaultEdgeOptions={defaultEdgeOptions}
              snapToGrid
              snapGrid={[20, 20]}
              fitView
              deleteKeyCode="Delete"
              nodesDraggable
              nodesConnectable
              elementsSelectable
              connectionMode={ConnectionMode.Loose}
            >
              <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
              <Controls position="bottom-left" />
              <MiniMap position="bottom-right" style={{ width: 150, height: 100 }} />
              {nodes.length === 0 && (
                <Panel position="center">
                  <Empty
                    description={
                      <span>
                        {t('scheduledTasks.empty.no_nodes_prefix')}
                        <Button
                          type="link"
                          size="small"
                          onClick={() => {
                            setAddNodeTab('task');
                            setAddNodeModalOpen(true);
                          }}
                          className="gaf-p-0"
                        >
                          {t('scheduledTasks.button.add_node')}
                        </Button>
                        {t('scheduledTasks.empty.no_nodes_suffix')}
                      </span>
                    }
                  />
                </Panel>
              )}
            </ReactFlow>
          )}
        </div>
      </div>

      {/* Status bar */}
      <div
        className="gaf-toolbar-group"
        style={{ height: 28, borderTop: `1px solid ${token.colorBorderSecondary}`, background: token.colorBgLayout }}
      >
        <Badge status="success" />
        <Typography.Text className="gaf-text-xxs" style={{ color: token.colorTextTertiary }}>
          {t('scheduledTasks.status.nodes', { count: nodes.length })}
        </Typography.Text>
        <Typography.Text className="gaf-text-xxs" style={{ color: token.colorTextTertiary }}>
          {t('scheduledTasks.status.edges', { count: edges.length })}
        </Typography.Text>
        {selectedNode && (
          <Typography.Text className="gaf-text-xxs" style={{ color: token.colorTextTertiary }}>
            {t('scheduledTasks.status.selected', { name: getNodeDisplayName(selectedNode.data as DagNode['data']) })}
          </Typography.Text>
        )}
      </div>

      {/* Add Node Modal — Tabs: Task | Pipeline (TD-110) */}
      <Modal
        title={t('scheduledTasks.modal.add_node_title')}
        open={addNodeModalOpen}
        onCancel={() => setAddNodeModalOpen(false)}
        footer={null}
        width={600}
      >
        <Tabs
          activeKey={addNodeTab}
          onChange={(key) => setAddNodeTab(key as 'task' | 'pipeline')}
          items={[
            {
              key: 'task',
              label: t('scheduledTasks.modal.add_node_tab_task'),
              children: (
                <div className="gaf-overflow-auto" style={{ maxHeight: 400 }}>
                  {tasks.length === 0 ? (
                    <Empty description={t('scheduledTasks.empty.no_tasks')} />
                  ) : (
                    <div className="gaf-flex-col gaf-gap-sm">
                      {tasks.map((task) => (
                        <div
                          key={task.id}
                          className="gaf-flex-between gaf-radius-md gaf-cursor-pointer"
                          style={{
                            padding: '10px 12px',
                            border: `1px solid ${token.colorBorderSecondary}`,
                          }}
                          onMouseEnter={(e) => (e.currentTarget.style.borderColor = COLOR_TASK)}
                          onMouseLeave={(e) => (e.currentTarget.style.borderColor = token.colorBorderSecondary)}
                          onClick={() => handleAddTask(Number(task.id), task.name)}
                        >
                          <div>
                            <Typography.Text strong>{task.name}</Typography.Text>
                            {task.description && (
                              <Typography.Text type="secondary" className="gaf-text-xs gaf-display-block">
                                {task.description}
                              </Typography.Text>
                            )}
                          </div>
                          <Tag color={task.is_enabled ? 'green' : 'default'}>
                            {task.is_enabled ? t('scheduledTasks.tag.enabled') : t('scheduledTasks.tag.disabled')}
                          </Tag>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ),
            },
            {
              key: 'pipeline',
              label: t('scheduledTasks.modal.add_node_tab_pipeline'),
              children: (
                <div className="gaf-overflow-auto" style={{ maxHeight: 400 }}>
                  {pipelines.length === 0 ? (
                    <Empty description={t('scheduledTasks.empty.no_pipelines')} />
                  ) : (
                    <div className="gaf-flex-col gaf-gap-sm">
                      {pipelines.map((pipe) => (
                        <div
                          key={pipe.id}
                          className="gaf-flex-between gaf-radius-md gaf-cursor-pointer"
                          style={{
                            padding: '10px 12px',
                            border: `1px solid ${token.colorBorderSecondary}`,
                          }}
                          onMouseEnter={(e) => (e.currentTarget.style.borderColor = COLOR_PIPELINE)}
                          onMouseLeave={(e) => (e.currentTarget.style.borderColor = token.colorBorderSecondary)}
                          onClick={() => handleAddPipeline(Number(pipe.id), pipe.name)}
                        >
                          <div>
                            <Typography.Text strong>
                              <ApartmentOutlined style={{ color: COLOR_PIPELINE, marginRight: 6 }} />
                              {pipe.name}
                            </Typography.Text>
                            {pipe.description && (
                              <Typography.Text type="secondary" className="gaf-text-xs gaf-display-block">
                                {pipe.description}
                              </Typography.Text>
                            )}
                          </div>
                          <Tag color={pipe.is_template ? 'purple' : 'default'}>v{pipe.version}</Tag>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ),
            },
          ]}
        />
      </Modal>
    </div>
  );
}

/** DAG Editor Page wrapper with ReactFlowProvider */
export function DagEditorPage({ chainId, onSave }: DagEditorProps) {
  return (
    <ReactFlowProvider>
      <DagEditorInner chainId={chainId} onSave={onSave} />
    </ReactFlowProvider>
  );
}

export default DagEditorPage;
