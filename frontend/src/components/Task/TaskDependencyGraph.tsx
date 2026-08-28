import { useEffect, useState, useCallback, useRef } from 'react';
import {
  Card,
  Button,
  Space,
  Tag,
  Typography,
  Modal,
  Select,
  message,
  Alert,
  Popconfirm,
  Row,
  Col,
  Badge,
  theme as antTheme,
} from 'antd';
import { PlusOutlined, DeleteOutlined, ReloadOutlined, ApartmentOutlined, WarningOutlined } from '@ant-design/icons';
import { fetchTasks } from '@/api/tasks';
import { fetchTaskChainNodes, createTaskChainNode, deleteTaskChainNode, checkTaskChainCircular } from '@/api/misc';
import { useTranslation } from '@/i18n';

interface TaskNode {
  id: number;
  name: string;
  status?: string;
  is_enabled?: boolean;
}

interface TaskDependency {
  id: number;
  parent: number;
  child: number;
  condition: Record<string, unknown>;
  order: number;
  parent_name?: string;
  child_name?: string;
  parent_status?: string;
  child_status?: string;
}

interface TaskOrchestrationProps {
  taskId?: number;
  visible: boolean;
  onClose: () => void;
}

export function TaskDependencyGraph({ taskId, visible, onClose }: TaskOrchestrationProps) {
  const { token } = antTheme.useToken();
  const t = useTranslation();
  const [tasks, setTasks] = useState<TaskNode[]>([]);
  const [dependencies, setDependencies] = useState<TaskDependency[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedTask, setSelectedTask] = useState<number | null>(null);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [addChildId, setAddChildId] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const loadData = useCallback(async () => {
    if (!taskId) return;
    setLoading(true);
    try {
      const [tasksData, depsData] = await Promise.all([
        fetchTasks({ page_size: 100 }),
        fetchTaskChainNodes<TaskDependency[]>(taskId),
      ]);
      setTasks((tasksData?.results || []) as unknown as TaskNode[]);
      setDependencies(depsData || []);
    } catch {
      message.error(t('taskStudio.dependency_load_failed'));
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  useEffect(() => {
    if (visible && taskId) {
      loadData();
    }
  }, [visible, taskId, loadData]);

  const handleAddDependency = async () => {
    if (!addChildId || !selectedTask) {
      message.warning(t('taskStudio.dependency_select_required'));
      return;
    }
    if (selectedTask === addChildId) {
      message.warning(t('taskStudio.dependency_self_dep_forbidden'));
      return;
    }
    try {
      await createTaskChainNode({
        task_id: taskId || selectedTask,
        parent_id: selectedTask,
        child_id: addChildId,
        condition: {},
        order: dependencies.length,
      });
      message.success(t('taskStudio.dependency_create_success'));
      setAddModalOpen(false);
      setAddChildId(null);
      loadData();
    } catch {
      message.error(t('taskStudio.dependency_create_failed'));
    }
  };

  const handleDeleteDependency = async (depId: number) => {
    try {
      await deleteTaskChainNode(depId);
      message.success(t('taskStudio.dependency_delete_success'));
      loadData();
    } catch {
      message.error(t('taskStudio.dependency_delete_failed'));
    }
  };

  const handleCheckCircular = async () => {
    if (!taskId) return;
    try {
      const data = await checkTaskChainCircular<{ has_cycle?: boolean; cycle_path?: string[] }>(taskId);
      if (data?.has_cycle) {
        message.error(t('taskStudio.dependency_circular_detected', { path: data.cycle_path?.join(' → ') }));
      } else {
        message.success(t('taskStudio.dependency_no_circular'));
      }
    } catch {
      message.error(t('taskStudio.dependency_circular_check_failed'));
    }
  };

  const detectCircularInClient = (): boolean => {
    const adj: Record<number, number[]> = {};
    dependencies.forEach((d) => {
      if (!adj[d.parent]) adj[d.parent] = [];
      adj[d.parent].push(d.child);
    });

    const visited = new Set<number>();
    const recStack = new Set<number>();

    const dfs = (node: number): boolean => {
      visited.add(node);
      recStack.add(node);
      const neighbors = adj[node] || [];
      for (const neighbor of neighbors) {
        if (!visited.has(neighbor)) {
          if (dfs(neighbor)) return true;
        } else if (recStack.has(neighbor)) {
          return true;
        }
      }
      recStack.delete(node);
      return false;
    };

    for (const dep of dependencies) {
      if (!visited.has(dep.parent)) {
        if (dfs(dep.parent)) return true;
      }
    }
    return false;
  };

  const hasCircular = detectCircularInClient();

  const renderGraph = () => {
    if (dependencies.length === 0) {
      return (
        <div style={{ textAlign: 'center', padding: 40, color: token.colorTextTertiary }}>
          <ApartmentOutlined className="gaf-mb-lg" style={{ fontSize: 48 }} />
          <div>暂无任务依赖关系，点击"添加依赖"创建任务编排</div>
        </div>
      );
    }

    const nodeMap = new Map<number, { deps: number[]; children: number[] }>();
    const allIds = new Set<number>();

    dependencies.forEach((d) => {
      allIds.add(d.parent);
      allIds.add(d.child);
      if (!nodeMap.has(d.parent)) {
        nodeMap.set(d.parent, { deps: [], children: [] });
      }
      if (!nodeMap.has(d.child)) {
        nodeMap.set(d.child, { deps: [], children: [] });
      }
      nodeMap.get(d.parent)!.children.push(d.child);
      nodeMap.get(d.child)!.deps.push(d.parent);
    });

    const rootNodes = Array.from(allIds).filter((id) => {
      return !dependencies.some((d) => d.child === id);
    });

    const renderNode = (nodeId: number, level: number): React.ReactNode => {
      const task = tasks.find((t) => t.id === nodeId);
      const name = task?.name || `任务 #${nodeId}`;
      const isSelected = selectedTask === nodeId;
      const info = nodeMap.get(nodeId);

      return (
        <div key={nodeId} className="gaf-mb-sm">
          <div className="gaf-flex-center gaf-gap-sm">
            <div style={{ width: level * 40, flexShrink: 0 }} />
            <Card
              size="small"
              hoverable
              style={{
                cursor: 'pointer',
                borderColor: isSelected ? '#1890ff' : '#d9d9d9',
                borderWidth: isSelected ? 2 : 1,
                minWidth: 180,
              }}
              onClick={() => setSelectedTask(nodeId)}
              styles={{ body: { padding: '8px 12px' } }}
            >
              <Space>
                <Badge status={task?.is_enabled !== false ? 'success' : 'default'} text={null} />
                <Typography.Text strong ellipsis style={{ maxWidth: 140 }}>
                  {name}
                </Typography.Text>
                {info && (
                  <Tag color="processing" style={{ fontSize: 10 }}>
                    {info.children.length} 下游
                  </Tag>
                )}
              </Space>
            </Card>
            {selectedTask === nodeId && (
              <Button
                size="small"
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => {
                  setAddModalOpen(true);
                  setAddChildId(null);
                  setSelectedTask(nodeId);
                }}
              >
                添加依赖
              </Button>
            )}
          </div>
          {info && info.children.length > 0 && (
            <div style={{ borderLeft: '2px solid #1890ff', marginLeft: level * 40 + 90 }}>
              {info.children.map((childId) => (
                <div key={childId}>
                  <div style={{ height: 16, marginLeft: 2 }}>
                    <span className="gaf-ml-sm" style={{ fontSize: 10, color: token.colorTextTertiary }}>
                      └ 依赖 #{depIdOf(childId)}
                    </span>
                    <Popconfirm
                      title="确定删除此依赖关系？"
                      onConfirm={() => {
                        const dep = dependencies.find((d) => d.parent === nodeId && d.child === childId);
                        if (dep) handleDeleteDependency(dep.id);
                      }}
                    >
                      <DeleteOutlined
                        className="gaf-ml-sm"
                        style={{ color: token.colorError, fontSize: 10, cursor: 'pointer' }}
                      />
                    </Popconfirm>
                  </div>
                  {renderNode(childId, level + 1)}
                </div>
              ))}
            </div>
          )}
        </div>
      );
    };

    const depIdOf = (childId: number) => dependencies.find((d) => d.child === childId)?.id || '?';

    return (
      <div ref={containerRef} style={{ overflow: 'auto', maxHeight: 500 }}>
        {rootNodes.map((id) => renderNode(id, 0))}
      </div>
    );
  };

  return (
    <Modal
      title={
        <Space>
          <ApartmentOutlined />
          多任务编排
          {hasCircular && <Tag color="error">检测到循环依赖</Tag>}
        </Space>
      }
      open={visible}
      onCancel={onClose}
      width={900}
      footer={
        <Space>
          <Button onClick={handleCheckCircular} icon={<WarningOutlined />}>
            检测循环依赖
          </Button>
          <Button icon={<ReloadOutlined />} onClick={loadData}>
            刷新
          </Button>
          <Button onClick={onClose}>关闭</Button>
        </Space>
      }
      destroyOnHidden
    >
      {hasCircular && (
        <Alert
          type="error"
          title="检测到循环依赖！请移除形成循环的依赖关系，否则任务调度可能异常。"
          showIcon
          className="gaf-mb-lg"
        />
      )}

      <Row gutter={[16, 16]} className="gaf-mb-lg">
        <Col span={24}>
          <Space>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setAddModalOpen(true);
                setAddChildId(null);
              }}
            >
              添加依赖
            </Button>
            <Select
              placeholder="选择父任务…"
              value={selectedTask}
              onChange={setSelectedTask}
              allowClear
              className="gaf-w-200"
              options={tasks.map((t) => ({
                value: t.id,
                label: `${t.is_enabled !== false ? '● ' : '○ '}${t.name}`,
              }))}
            />
          </Space>
        </Col>
      </Row>

      <Card size="small" title="依赖关系图">
        {loading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <ReloadOutlined spin className="gaf-text-2xl" />
          </div>
        ) : (
          renderGraph()
        )}
      </Card>

      <Modal
        title="添加任务依赖"
        open={addModalOpen}
        onCancel={() => {
          setAddModalOpen(false);
          setAddChildId(null);
        }}
        onOk={handleAddDependency}
        okText="创建依赖"
        cancelText="取消"
      >
        <div className="gaf-mb-lg">
          <Typography.Text strong>父任务（前置）</Typography.Text>
          <Select
            value={selectedTask}
            onChange={setSelectedTask}
            className="gaf-w-full gaf-mt-sm"
            placeholder="选择前置任务"
            options={tasks
              .filter((t) => t.id !== addChildId)
              .map((t) => ({
                value: t.id,
                label: t.name,
              }))}
          />
        </div>
        <div>
          <Typography.Text strong>子任务（后续）</Typography.Text>
          <Select
            value={addChildId}
            onChange={setAddChildId}
            className="gaf-w-full gaf-mt-sm"
            placeholder="选择后续任务"
            options={tasks
              .filter((t) => t.id !== selectedTask)
              .map((t) => ({
                value: t.id,
                label: t.name,
              }))}
          />
        </div>
        <Alert type="info" title="父任务完成后，子任务才会开始执行" className="gaf-mt-lg gaf-text-xs" />
      </Modal>
    </Modal>
  );
}

export default TaskDependencyGraph;
