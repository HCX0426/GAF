/**
 * Custom task editor page.
 * Left: step list (drag-sortable). Right: step config form.
 * Supports pipeline mode and state machine mode switching, JSON preview/edit, schema validation.
 *
 * spec-2026-07-27-execution-path-unification: 表单内部用 TaskStepConfigLegacy (flat UI
 * 字段), 保存时通过 stepToPipelineNode() 转成 agent 期望的 PipelineNode schema
 * (nested: node_type/config/retry/fallback/next_node_id). chain schema 已废弃.
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Tabs,
  Form,
  Input,
  InputNumber,
  Select,
  Button,
  Space,
  Card,
  App,
  Modal,
  Empty,
  Tooltip,
  theme as antTheme,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  HolderOutlined,
  CheckCircleOutlined,
  SaveOutlined,
  ArrowLeftOutlined,
} from '@ant-design/icons';
import { createTask, updateTask, validateTask, validatePayload, fetchTask, type CheckItem, type ValidatePayloadResult } from '@/api/tasks';
import { resolveErrorMessage } from '@/utils/errorHandler';
import { validatePipelineGraph } from '@/utils/schemaValidator';
import type { TaskStepConfigLegacy, TaskEditorMode, Task } from '@/types/models';
import { useTranslation } from '@/i18n';
import { useUnsavedChangesWarning } from '@/hooks/useUnsavedChangesWarning';
import PageWrapper from '@/components/Common/PageWrapper';

/** Generate unique ID */
function generateId(): string {
  return `step_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * N191 §10.7 P0-3 (架构层归一化, 2026-07-27): 解析 "WxH" 字符串为 [w, h] 元组。
 * 用于前端 base_resolution 输入框 → task_definition.metadata.original_base_res 转换。
 * 返回 null 表示输入无效或为空 (orchestrator 会跳过 transformer 构建)。
 */
function parseBaseResolution(raw: string): [number, number] | null {
  const trimmed = (raw || '').trim();
  if (!trimmed) return null;
  const match = trimmed.match(/^(\d+)\s*[x×]\s*(\d+)$/i);
  if (!match) return null;
  const w = parseInt(match[1], 10);
  const h = parseInt(match[2], 10);
  if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) return null;
  return [w, h];
}

/** Create default step (i18n-aware name) */
function createDefaultStep(
  index: number,
  t: (key: string, params?: Record<string, string | number>) => string,
): TaskStepConfigLegacy {
  return {
    id: generateId(),
    name: t('tasks.default_step_name', { n: index + 1 }),
    action_type: 'click',
    retry_count: 0,
    retry_interval: 1000,
  };
}

/**
 * spec-2026-07-27-execution-path-unification: 把表单内部的 TaskStepConfigLegacy
 * (flat UI 字段) 转成 agent parser 期望的 PipelineNode schema (nested)。
 *
 * 字段映射:
 *   action_type           → node_type
 *   retry_count + retry_interval → retry: {max_retries, base_delay}
 *   fallback_action       → fallback: {action}
 *   next_step             → next_node_id
 *   template_id/roi/condition → config: {...}
 *
 * 线性 pipeline: 不输出 edges, PipelineParser 会按 nodes 顺序自动链接。
 * 状态机模式: 通过 next_node_id 表达条件跳转目标 (condition 放在 config)。
 */
function stepToPipelineNode(step: TaskStepConfigLegacy): Record<string, unknown> {
  const config: Record<string, unknown> = {};
  if (step.template_id) config.template_id = step.template_id;
  if (step.roi) config.roi = step.roi;
  if (step.condition) config.condition = step.condition;

  const node: Record<string, unknown> = {
    id: step.id,
    name: step.name,
    node_type: step.action_type,
    config,
  };

  if (step.retry_count > 0 || step.retry_interval > 0) {
    node.retry = {
      max_retries: step.retry_count,
      base_delay: step.retry_interval,
    };
  }

  if (step.fallback_action) {
    node.fallback = { action: step.fallback_action };
  }

  if (step.next_step) {
    node.next_node_id = step.next_step;
  }

  return node;
}

/**
 * 反向转换: pipeline node dict → TaskStepConfigLegacy (用于 JSON 导入)。
 * 兼容新旧两种字段名 (action/type/node_type, next_step/next_node_id)。
 */
function pipelineNodeToStep(node: Record<string, unknown>): TaskStepConfigLegacy {
  const config = (node.config as Record<string, unknown>) || {};
  const retry = (node.retry as Record<string, unknown>) || {};
  const fallback = (node.fallback as Record<string, unknown>) || {};
  return {
    id: (node.id as string) || generateId(),
    name: (node.name as string) || '',
    action_type: (node.node_type as string) || (node.action as string) || (node.type as string) || 'click',
    template_id: config.template_id as string | undefined,
    roi: config.roi as string | undefined,
    retry_count: (retry.max_retries as number) || 0,
    retry_interval: (retry.base_delay as number) || 1000,
    fallback_action: fallback.action as string | undefined,
    condition: config.condition as string | undefined,
    next_step: (node.next_node_id as string) || (node.next_step as string) || undefined,
  };
}

/** Task editor page component */
export function TaskEditorPage() {
  const { token } = antTheme.useToken();
  const navigate = useNavigate();
  const { taskId } = useParams<{ taskId: string }>();
  const t = useTranslation();
  const [mode, setMode] = useState<TaskEditorMode>('pipeline');
  const [steps, setSteps] = useState<TaskStepConfigLegacy[]>([createDefaultStep(0, t)]);
  const [activeStepId, setActiveStepId] = useState<string>(steps[0]?.id || '');
  const [taskName, setTaskName] = useState('');
  const [taskDesc, setTaskDesc] = useState('');
  // N191 §10.7 P0-3 (架构层归一化, 2026-07-27): base_resolution 输入框。
  // 用户填写后, 保存到 task_definition.metadata.original_base_res = [w, h],
  // orchestrator 读取后构造 coord_transformer (Windows logical / ADB physical)。
  // 默认空字符串 (legacy 兼容, 不注入 transformer)。
  const [baseResolution, setBaseResolution] = useState('');
  const [saving, setSaving] = useState(false);
  // Task 1.4 (P1-6): validate 按钮独立 loading state, 避免与 save 按钮混淆
  const [validating, setValidating] = useState(false);
  const [jsonModalOpen, setJsonModalOpen] = useState(false);
  const [jsonValue, setJsonValue] = useState('');
  const [isDirty, setIsDirty] = useState(false);
  const firstRenderRef = useRef(true);
  const [form] = Form.useForm();
  const { modal: modalApi, message: msgApi } = App.useApp();

  // F2 fix (2026-08-28): 路由 tasks/:taskId/edit 编辑态 — 加载既有任务并预填表单。
  // 之前完全忽略 taskId, 导致编辑页永远空白 (名称/描述为空 → 校验必失败)。
  useEffect(() => {
    if (!taskId) return;
    const numId = Number(taskId);
    if (!Number.isFinite(numId)) return;
    let cancelled = false;
    fetchTask(numId)
      .then((task) => {
        if (cancelled) return;
        setTaskName(task.name || '');
        setTaskDesc(task.description || '');
        if (task.execution_mode === 'state_machine') {
          setMode('state_machine');
        }
        // 反填步骤: task_definition.nodes (pipeline schema) → TaskStepConfigLegacy
        const def = (task.task_definition as { nodes?: unknown[]; metadata?: { original_base_res?: [number, number] } }) || {};
        const rawNodes = Array.isArray(def.nodes) ? def.nodes : [];
        if (rawNodes.length > 0) {
          const loaded = rawNodes.map((n) => pipelineNodeToStep(n as Record<string, unknown>));
          setSteps(loaded);
          setActiveStepId(loaded[0]?.id || '');
        }
        const rawBaseRes = def.metadata?.original_base_res;
        if (Array.isArray(rawBaseRes) && rawBaseRes.length === 2) {
          setBaseResolution(`${rawBaseRes[0]}x${rawBaseRes[1]}`);
        }
      })
      .catch(() => {
        if (cancelled) return;
        msgApi.error(t('tasks.load_task_failed') || '加载任务失败');
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId]);

  // F019: mark the editor dirty whenever the user edits steps/name/desc/mode.
  // Skip the initial render so loading existing data doesn't flip the flag.
  useEffect(() => {
    if (firstRenderRef.current) {
      firstRenderRef.current = false;
      return;
    }
    setIsDirty(true);
  }, [steps, taskName, taskDesc, mode, baseResolution]);

  useUnsavedChangesWarning(isDirty);

  // Action type options depend on current locale
  const actionTypeOptions = [
    { label: t('tasks.action_click'), value: 'click' },
    { label: t('tasks.action_long_press'), value: 'long_press' },
    { label: t('tasks.action_swipe'), value: 'swipe' },
    { label: t('tasks.action_input_text'), value: 'input_text' },
    { label: t('tasks.action_wait'), value: 'wait' },
    { label: t('tasks.action_ocr'), value: 'ocr' },
    { label: t('tasks.action_template_match'), value: 'template_match' },
    { label: t('tasks.action_condition'), value: 'condition' },
    { label: t('tasks.action_script'), value: 'script' },
  ];

  /** Get active step */
  const activeStep = steps.find((s) => s.id === activeStepId);

  /** Add new step */
  const handleAddStep = () => {
    const newStep = createDefaultStep(steps.length, t);
    setSteps([...steps, newStep]);
    setActiveStepId(newStep.id);
  };

  /** Delete step */
  const handleDeleteStep = (stepId: string) => {
    const newSteps = steps.filter((s) => s.id !== stepId);
    setSteps(newSteps);
    if (activeStepId === stepId) {
      setActiveStepId(newSteps[newSteps.length - 1]?.id || '');
    }
  };

  /** Move step up */
  const handleMoveUp = (index: number) => {
    if (index === 0) return;
    const newSteps = [...steps];
    [newSteps[index - 1], newSteps[index]] = [newSteps[index], newSteps[index - 1]];
    setSteps(newSteps);
  };

  /** Move step down */
  const handleMoveDown = (index: number) => {
    if (index === steps.length - 1) return;
    const newSteps = [...steps];
    [newSteps[index], newSteps[index + 1]] = [newSteps[index + 1], newSteps[index]];
    setSteps(newSteps);
  };

  /** Update step config */
  const handleStepChange = useCallback(
    (field: string, value: unknown) => {
      setSteps(steps.map((s) => (s.id === activeStepId ? { ...s, [field]: value } : s)));
    },
    [steps, activeStepId],
  );

  /** Sync form value changes to step */
  const handleFormChange = (changedValues: Partial<TaskStepConfigLegacy>) => {
    Object.entries(changedValues).forEach(([key, value]) => {
      handleStepChange(key, value);
    });
  };

  /** Open JSON preview */
  const handleOpenJson = () => {
    // N191 §10.7 P0-3: 输出 metadata.original_base_res (若用户填写)。
    // orchestrator 读取此字段构建 coord_transformer (Windows/ADB)。
    const baseRes = parseBaseResolution(baseResolution);
    const data: Record<string, unknown> = {
      name: taskName,
      description: taskDesc,
      mode,
      nodes: steps.map((s) => stepToPipelineNode(s)),
    };
    if (baseRes) {
      data.metadata = { original_base_res: baseRes };
    }
    setJsonValue(JSON.stringify(data, null, 2));
    setJsonModalOpen(true);
  };

  /** Import from JSON */
  const handleImportJson = () => {
    try {
      const data = JSON.parse(jsonValue);
      if (data.name) setTaskName(data.name);
      if (data.description) setTaskDesc(data.description);
      if (data.mode) setMode(data.mode);
      // N191 §10.7 P0-3: 读取 metadata.original_base_res 回填 baseResolution 输入框。
      const meta = data.metadata || {};
      const rawBaseRes = meta.original_base_res;
      if (Array.isArray(rawBaseRes) && rawBaseRes.length === 2) {
        setBaseResolution(`${rawBaseRes[0]}x${rawBaseRes[1]}`);
      } else {
        setBaseResolution('');
      }
      // spec-2026-07-27-execution-path-unification: 同时兼容
      // 新 pipeline schema ({nodes: [...]}) 和旧 chain schema ({steps: [...]}).
      // 旧 steps 直接是 TaskStepConfigLegacy; 新 nodes 需要 pipelineNodeToStep 反向转换.
      const rawNodes = Array.isArray(data.nodes) ? data.nodes : [];
      const rawSteps = Array.isArray(data.steps) ? data.steps : [];
      const imported: TaskStepConfigLegacy[] = [
        ...rawNodes.map((n: Record<string, unknown>) => pipelineNodeToStep(n)),
        ...rawSteps.map((s: TaskStepConfigLegacy) => ({
          ...s,
          id: s.id || generateId(),
        })),
      ];
      if (imported.length > 0) {
        setSteps(imported);
        setActiveStepId(imported[0].id);
      }
      msgApi.success(t('tasks.json_import_success'));
      setJsonModalOpen(false);
    } catch (error) {
      // N192 B1 P0: 用 resolveErrorMessage 展示具体错误, 而非 generic "JSON 格式无效"
      msgApi.error(resolveErrorMessage(error));
    }
  };

  /**
   * Task 1.4 (P1-6): 构建 task_definition (handleValidate + handleSave 共用)。
   * N191 §10.7 P0-3: 若用户填写 base_resolution, 写入 metadata.original_base_res,
   * orchestrator 读取后构造 coord_transformer (Windows logical / ADB physical)。
   */
  const buildTaskDefinition = (baseRes: [number, number] | null): Record<string, unknown> => {
    const nodes = steps.map((s) => stepToPipelineNode(s));
    const taskDefinition: Record<string, unknown> = { nodes };
    if (baseRes) {
      taskDefinition.metadata = { original_base_res: baseRes };
    }
    return taskDefinition;
  };

  /**
   * Task 1.4 (P1-6): 渲染 CheckItem 列表为 React 节点, 供 modal 展示。
   * fail 项用红色, warn 项用橙色, 附带 suggestion (N192 B3/B6 P1)。
   */
  const renderCheckItems = (items: CheckItem[], color: string) => (
    <>
      {items.map((err, i) => (
        <div key={i} className="gaf-mb-sm">
          <div style={{ color }}>
            {err.node_id ? `[${err.node_id}] ` : ''}
            {err.message}
          </div>
          {err.suggestion && <div style={{ color: token.colorTextTertiary, fontSize: 12 }}>{err.suggestion}</div>}
        </div>
      ))}
    </>
  );

  /**
   * Schema validation — Task 1.4 (P1-6): 改为调用后端 validate-payload 端点。
   *
   * 之前是纯前端校验 (taskName + step name + action_type), 与 handleSave 的
   * 后端校验口径不一致 (N192 B5 评估发现)。现在统一走 validate-payload 端点,
   * 复用 PipelineValidator, 与 handleSave 完全一致。
   *
   * Task 3.5 (P2-5): handleValidate 入口先做本地 ajv schema 校验,
   * 本地校验失败时直接展示错误不调 backend (N192 B5 校验前置, 减少网络往返);
   * 本地校验通过时继续调 backend validate-payload (深度校验: 引用完整性等)。
   */
  const handleValidate = async () => {
    // 前端基础校验: task name 必填 (不调用后端就能判断, 减少不必要的网络请求)
    if (!taskName.trim()) {
      modalApi.error({
        title: t('tasks.validation_failed_title'),
        content: t('tasks.validation_task_name_required'),
      });
      return;
    }
    // N191 §10.7 P0-3: 校验 base_resolution 格式 (若用户填写)。
    const baseRes = parseBaseResolution(baseResolution);
    if (baseResolution.trim() && !baseRes) {
      modalApi.error({
        title: t('tasks.validation_failed_title'),
        content: t('tasks.validation_base_resolution_invalid'),
      });
      return;
    }

    setValidating(true);
    try {
      const taskDefinition = buildTaskDefinition(baseRes);

      // Task 3.5 (P2-5): 本地 ajv schema 校验 — 快速拦截结构错误。
      // 失败时直接展示错误, 不调 backend (节省网络请求 + 减少等待)。
      const localErrors = validatePipelineGraph(taskDefinition);
      if (localErrors.length > 0) {
        modalApi.error({
          title: t('tasks.validation_failed_title'),
          content: <div>{renderCheckItems(localErrors, 'token.colorError')}</div>,
        });
        return;
      }

      // Task 1.4 (P1-6): 调用后端 validate-payload 端点, 统一校验口径
      const result = await validatePayload(taskDefinition, mode);

      if (result.valid && result.warnings.length === 0) {
        // 校验通过, 无警告
        modalApi.success({
          title: t('tasks.validation_passed_title'),
          content: t('tasks.validation_passed_content'),
        });
      } else if (result.valid && result.warnings.length > 0) {
        // 校验通过, 但有警告 — 展示警告让用户知晓
        modalApi.warning({
          title: t('tasks.validation_passed_title'),
          content: <div>{renderCheckItems(result.warnings, 'token.colorWarning')}</div>,
        });
      } else {
        // 校验失败 — 展示错误 + 警告
        modalApi.error({
          title: t('tasks.validation_failed_title'),
          content: (
            <div>
              {renderCheckItems(result.errors, 'token.colorError')}
              {renderCheckItems(result.warnings, 'token.colorWarning')}
            </div>
          ),
        });
      }
    } catch (error) {
      // validate-payload 端点报错 (网络/500) — 用 resolveErrorMessage 展示具体错误
      msgApi.error(resolveErrorMessage(error));
    } finally {
      setValidating(false);
    }
  };

  /** Save task — Task 1.4 (P1-6): 先 validate-payload 通过再 createTask, 移除 race condition */
  const handleSave = async () => {
    if (!taskName.trim()) {
      msgApi.warning(t('tasks.validation_task_name_required'));
      return;
    }
    // N191 §10.7 P0-3: 校验 base_resolution 格式 (若用户填写)。
    // 留空 = legacy 模式 (orchestrator 不构建 transformer, 走 raw pixel)。
    const baseRes = parseBaseResolution(baseResolution);
    if (baseResolution.trim() && !baseRes) {
      msgApi.warning(t('tasks.validation_base_resolution_invalid'));
      return;
    }
    setSaving(true);
    try {
      const taskDefinition = buildTaskDefinition(baseRes);
      const nodes = taskDefinition.nodes as Array<Record<string, unknown>>;

      // Task 1.4 (P1-6): 先调用 validate-payload 预校验, 通过后再 createTask。
      // 统一校验口径 (handleValidate + handleSave 都走同一端点), 避免 createTask 后
      // validate 失败再 deleteTask 的 race condition (N192 B5 P1)。
      let payloadResult: ValidatePayloadResult | null = null;
      try {
        payloadResult = await validatePayload(taskDefinition, mode);
      } catch (validateError) {
        // validate-payload 端点本身报错 (非校验失败, 如 500/网络) — 不阻塞保存, 但记录日志
        console.warn('validate-payload endpoint failed:', validateError);
      }
      if (payloadResult && !payloadResult.valid) {
        // 预校验失败: 展示节点级错误, 不创建 task (避免 race condition)
        modalApi.error({
          title: t('tasks.validation_failed_title'),
          content: (
            <div>
              {renderCheckItems(payloadResult.errors, 'token.colorError')}
              {renderCheckItems(payloadResult.warnings, 'token.colorWarning')}
            </div>
          ),
        });
        return; // 不创建 task, 让用户修复后重新保存 (finally 仍会 setSaving(false))
      }

      const created = taskId
        ? await updateTask(Number(taskId), {
            name: taskName,
            description: taskDesc,
            execution_mode: mode,
            task_definition: taskDefinition,
            params_config: { mode, nodes },
          } as Partial<Task>)
        : await createTask({
            name: taskName,
            description: taskDesc,
            execution_mode: mode,
            task_definition: taskDefinition,
            params_config: { mode, nodes },
          } as Parameters<typeof createTask>[0]);

      // N192 B5 P1: 保存后调用后端 validate 端点作为二次校验 (可选, 不阻塞)。
      // Task 1.4 (P1-6): 预校验已通过, 二次校验失败只记录日志, 不删除 task。
      // 因为预校验和 createTask 之间没有状态变更, 二次校验失败是极罕见的边角情况
      // (如数据库序列化导致 schema 微变), 删除 task 会让用户困惑。保留二次校验
      // 仅用于异常监控, 不影响用户流程。
      try {
        await validateTask(created.id);
      } catch (validateError) {
        // validate 端点本身报错 (非校验失败, 如 500/网络) — 不阻塞保存, 但记录日志
        console.warn('post-create validate endpoint failed:', validateError);
      }

      setIsDirty(false);
      msgApi.success(t('tasks.task_saved'));
      navigate('/tasks');
    } catch (error) {
      // N192 B1 P0: 用 resolveErrorMessage 展示后端具体错误, 而非 generic "保存失败"
      msgApi.error(resolveErrorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  /** Sync form when active step changes */
  useEffect(() => {
    if (activeStep) {
      form.setFieldsValue(activeStep);
    }
  }, [activeStepId, form]);

  return (
    <PageWrapper
      title={t('tasks.editor_title')}
      extra={
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/tasks')}>
            {t('tasks.editor_back')}
          </Button>
          <Button icon={<CheckCircleOutlined />} onClick={handleValidate} loading={validating}>
            {t('tasks.editor_validate')}
          </Button>
          <Button onClick={handleOpenJson}>{t('tasks.editor_json_preview')}</Button>
          <Button type="primary" icon={<SaveOutlined />} onClick={handleSave} loading={saving}>
            {t('tasks.editor_save')}
          </Button>
        </Space>
      }
    >
      {/* Task basic info */}
      <Card size="small" className="gaf-mb-lg">
        <Space className="gaf-w-full" orientation="vertical">
          <Input
            placeholder={t('tasks.editor_task_name_placeholder')}
            value={taskName}
            onChange={(e) => setTaskName(e.target.value)}
            maxLength={200}
            showCount
            style={{ maxWidth: 400 }}
            aria-label={t('tasks.editor_task_name_placeholder')}
            name="task_name"
            autoComplete="off"
          />
          <Input.TextArea
            placeholder={t('tasks.editor_task_desc_placeholder')}
            value={taskDesc}
            onChange={(e) => setTaskDesc(e.target.value)}
            rows={2}
            style={{ maxWidth: 600 }}
            aria-label={t('tasks.editor_task_desc_placeholder')}
            name="task_description"
            autoComplete="off"
          />
          <Tabs
            activeKey={mode}
            onChange={(key) => setMode(key as TaskEditorMode)}
            items={[
              { key: 'pipeline', label: t('tasks.editor_mode_pipeline') },
              { key: 'state_machine', label: t('tasks.editor_mode_state_machine') },
            ]}
            size="small"
          />
          {/* N191 §10.7 P0-3 (架构层归一化, 2026-07-27): base_resolution 输入框。
              用户填写 "WxH" (如 "1920x1080") 后, 保存到 task_definition.metadata.original_base_res,
              orchestrator 读取后构造 coord_transformer (Windows: base→logical→physical,
              ADB: base→physical 直接缩放)。留空 = legacy 模式, 走 raw pixel 不转换。 */}
          <Space size="small" style={{ alignItems: 'center' }}>
            <Tooltip title={t('tasks.editor_base_resolution_tooltip')}>
              <span className="gaf-text-13" style={{ color: token.colorTextSecondary }}>
                {t('tasks.editor_base_resolution_label')}
              </span>
            </Tooltip>
            <Input
              placeholder={t('tasks.editor_base_resolution_placeholder')}
              value={baseResolution}
              onChange={(e) => setBaseResolution(e.target.value)}
              maxLength={20}
              style={{ maxWidth: 240 }}
              aria-label={t('tasks.editor_base_resolution_placeholder')}
              name="base_resolution"
              autoComplete="off"
            />
          </Space>
        </Space>
      </Card>

      <div className="gaf-flex gaf-gap-lg">
        {/* Left: step list */}
        <Card
          title={t('tasks.editor_step_list_title')}
          size="small"
          style={{ width: 280 }}
          extra={
            <Button
              size="small"
              icon={
                <span aria-hidden="true">
                  <PlusOutlined />
                </span>
              }
              onClick={handleAddStep}
            >
              {t('tasks.editor_add_step')}
            </Button>
          }
        >
          {steps.length === 0 ? (
            <Empty description={t('tasks.editor_empty_steps')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <div>
              {(steps || []).map((step, index) => (
                <div
                  key={step.id}
                  onClick={() => {
                    setActiveStepId(step.id);
                  }}
                  className="gaf-flex-between gaf-py-sm gaf-px-md gaf-cursor-pointer"
                  style={{
                    borderRadius: 4,
                    background: activeStepId === step.id ? token.colorPrimaryBg : 'transparent',
                    borderBottom: index < steps.length - 1 ? `1px solid ${token.colorBorderSecondary}` : undefined,
                  }}
                >
                  <Space>
                    <HolderOutlined style={{ color: token.colorTextTertiary, cursor: 'grab' }} />
                    <span>{step.name}</span>
                  </Space>
                  <Space size={4}>
                    <Button
                      type="text"
                      size="small"
                      disabled={index === 0}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleMoveUp(index);
                      }}
                    >
                      ↑
                    </Button>
                    <Button
                      type="text"
                      size="small"
                      disabled={index === steps.length - 1}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleMoveDown(index);
                      }}
                    >
                      ↓
                    </Button>
                    <DeleteOutlined
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteStep(step.id);
                      }}
                      className="gaf-p-xs gaf-cursor-pointer"
                      style={{ color: token.colorError }}
                    />
                  </Space>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Right: step config form */}
        <Card
          title={
            activeStep
              ? t('tasks.editor_step_config_with_name', { name: activeStep.name })
              : t('tasks.editor_step_config')
          }
          size="small"
          className="gaf-flex-1"
        >
          <Form
            form={form}
            layout="vertical"
            initialValues={activeStep}
            onValuesChange={handleFormChange}
            style={{ maxWidth: 600, display: activeStep ? 'block' : 'none' }}
          >
            <Form.Item
              name="name"
              label={t('tasks.form_step_name_label')}
              rules={[{ required: true, message: t('tasks.form_step_name_required') }]}
            >
              <Input placeholder={t('tasks.form_step_name_placeholder')} />
            </Form.Item>
            <Form.Item
              name="action_type"
              label={t('tasks.form_action_type_label')}
              rules={[{ required: true, message: t('tasks.form_action_type_required') }]}
            >
              <Select options={actionTypeOptions} placeholder={t('tasks.form_action_type_placeholder')} />
            </Form.Item>
            <Form.Item name="template_id" label={t('tasks.form_template_id_label')}>
              <Input placeholder={t('tasks.form_template_id_placeholder')} />
            </Form.Item>
            <Form.Item name="roi" label={t('tasks.form_roi_label')}>
              <Input placeholder={t('tasks.form_roi_placeholder')} />
            </Form.Item>
            <Space className="gaf-w-full" size="large">
              <Form.Item name="retry_count" label={t('tasks.form_retry_count_label')}>
                <InputNumber min={0} max={10} />
              </Form.Item>
              <Form.Item name="retry_interval" label={t('tasks.form_retry_interval_label')}>
                <InputNumber min={0} step={500} />
              </Form.Item>
            </Space>
            <Form.Item name="fallback_action" label={t('tasks.form_fallback_action_label')}>
              <Input placeholder={t('tasks.form_fallback_action_placeholder')} />
            </Form.Item>
            {mode === 'state_machine' && (
              <>
                <Form.Item name="condition" label={t('tasks.form_condition_label')}>
                  <Input placeholder={t('tasks.form_condition_placeholder')} />
                </Form.Item>
                <Form.Item name="next_step" label={t('tasks.form_next_step_label')}>
                  <Select
                    placeholder={t('tasks.form_next_step_placeholder')}
                    allowClear
                    options={steps.filter((s) => s.id !== activeStepId).map((s) => ({ label: s.name, value: s.id }))}
                  />
                </Form.Item>
              </>
            )}
          </Form>
          {!activeStep && (
            <Empty description={t('tasks.editor_empty_step_hint')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
        </Card>
      </div>

      {/* JSON preview/edit modal */}
      <Modal
        title={t('tasks.json_modal_title')}
        open={jsonModalOpen}
        width={700}
        onCancel={() => setJsonModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setJsonModalOpen(false)}>
            {t('app.cancel')}
          </Button>,
          <Button key="import" type="primary" onClick={handleImportJson}>
            {t('app.import')}
          </Button>,
        ]}
      >
        <Input.TextArea
          value={jsonValue}
          onChange={(e) => setJsonValue(e.target.value)}
          rows={20}
          className="gaf-text-13 gaf-font-mono"
        />
      </Modal>
    </PageWrapper>
  );
}

export default TaskEditorPage;
