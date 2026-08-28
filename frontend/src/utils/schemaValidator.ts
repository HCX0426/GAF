/**
 * Task 3.5 (P2-5): 前端本地 schema 校验, 用 ajv + PIPELINE_GRAPH_SCHEMA
 * 快速拦截明显错误, 减少后端 round-trip (N192 B5: 校验前置)。
 *
 * 设计原则:
 * - 本地校验仅做 JSON Schema 结构校验 (与 backend/pipeline/schema.py 一致),
 *   不做引用完整性校验 (Pipeline 存在性 / 模板存在性等) — 这类校验仍走后端。
 * - 本地校验失败时直接展示错误, 不调 backend (节省网络请求)。
 * - 本地校验通过时继续调 backend validate-payload (深度校验: 必填字段 /
 *   模板引用 / Pipeline 引用 / 孤立节点 / 入口出口)。
 *
 * 与 backend schema 同步约定:
 * - 修改 backend/pipeline/schema.py 时, 必须同步修改本文件的 TS schema 副本。
 * - 单一权威源仍是 backend/pipeline/schema.py, 本文件是手动同步的 TS 镜像。
 */
import Ajv from 'ajv';
import type { ErrorObject } from 'ajv';
import type { CheckItem } from '@/api/tasks';

/**
 * 所有节点类型枚举 (与 backend/pipeline/schema.py ALL_NODE_TYPES 同步)。
 * 修改时务必同步 backend schema。
 */
const ALL_NODE_TYPES = [
  'click',
  'swipe',
  'key_press',
  'text_input',
  'long_press',
  'direct_hit',
  'template_match',
  'template_match_any',
  'ocr',
  'color_detect',
  'feature_match',
  'wait',
  'branch',
  'loop',
  'random_delay',
  'notify',
  'device_control',
  'monitor',
  'sub_pipeline',
  'goto',
  'swipe_until',
  'login_account',
  'switch_account',
  'switch_resource',
  'captcha_detect',
] as const;

/**
 * Pipeline graph_data 的 JSON Schema (Draft-07), 与 backend/pipeline/schema.py
 * 的 PIPELINE_GRAPH_SCHEMA 保持同步。
 *
 * Task 3.4 (P2-4): retry/fallback 加 properties 校验 (max_retries: integer>=0,
 * base_delay: number>=0, action: string, target_node_id: string)。
 */
const PIPELINE_GRAPH_SCHEMA = {
  $schema: 'http://json-schema.org/draft-07/schema#',
  type: 'object',
  required: ['nodes'],
  properties: {
    nodes: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id'],
        oneOf: [
          // canvas schema (React Flow)
          {
            type: 'object',
            required: ['id', 'type', 'position', 'data'],
            properties: {
              id: { type: 'string' },
              type: { type: 'string', enum: ALL_NODE_TYPES },
              position: {
                type: 'object',
                required: ['x', 'y'],
                properties: {
                  x: { type: 'number' },
                  y: { type: 'number' },
                },
              },
              data: { type: 'object' },
            },
          },
          // nested schema (agent / template.json)
          {
            type: 'object',
            required: ['id', 'node_type', 'config'],
            properties: {
              id: { type: 'string' },
              name: { type: 'string' },
              node_type: { type: 'string', enum: ALL_NODE_TYPES },
              config: { type: 'object' },
              // Task 3.4: retry/fallback 内部字段校验
              retry: {
                type: 'object',
                properties: {
                  max_retries: { type: 'integer', minimum: 0 },
                  base_delay: { type: 'number', minimum: 0 },
                },
                additionalProperties: false,
              },
              fallback: {
                type: 'object',
                properties: {
                  action: { type: 'string' },
                  target_node_id: { type: 'string' },
                },
                additionalProperties: false,
              },
              next_node_id: { type: 'string' },
            },
          },
        ],
      },
    },
    edges: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'source', 'target'],
        properties: {
          id: { type: 'string' },
          source: { type: 'string' },
          target: { type: 'string' },
          sourceHandle: { type: 'string' },
          targetHandle: { type: 'string' },
        },
      },
    },
    viewport: {
      type: 'object',
      properties: {
        x: { type: 'number' },
        y: { type: 'number' },
        zoom: { type: 'number' },
      },
    },
  },
} as const;

// ajv 单例: 模块加载时编译 schema, 后续调用复用编译结果。
// allErrors: true 收集所有错误而非首个, 便于一次展示全部问题。
// strict: false 关闭 ajv 对未知关键字 (如 $schema) 的告警。
const ajv = new Ajv({ allErrors: true, strict: false });
const validateFn = ajv.compile(PIPELINE_GRAPH_SCHEMA);

/**
 * 把 ajv 错误路径 (如 "nodes/0/retry/max_retries") 解析出 node_id。
 * 若无法定位则返回 null (结构级错误)。
 */
function extractNodeIdFromPath(instancePath: string): string | null {
  // instancePath 格式: "/nodes/0/retry/max_retries"
  const match = instancePath.match(/^\/nodes\/(\d+)/);
  if (!match) return null;
  // 这里只能拿到节点 index, 真正的 node_id 在 data 中;
  // 调用方 (validatePipelineGraph) 会用 nodes[index].id 替换。
  return match[1];
}

/**
 * 把 ajv ErrorObject 转换为 CheckItem (与后端 PipelineValidator.CheckItem 结构一致),
 * 便于前端复用 renderCheckItems 渲染逻辑。
 */
function ajvErrorToCheckItem(err: ErrorObject, nodes: unknown[]): CheckItem {
  const idxStr = extractNodeIdFromPath(err.instancePath);
  let nodeId: string | null = null;
  if (idxStr !== null) {
    const idx = Number(idxStr);
    const node = nodes[idx];
    if (node && typeof node === 'object' && 'id' in node) {
      const id = (node as { id?: unknown }).id;
      nodeId = typeof id === 'string' ? id : null;
    }
  }
  // 把 instancePath 转可读路径: "/nodes/0/retry/max_retries" → "nodes[0].retry.max_retries"
  const readablePath = err.instancePath
    .split('/')
    .filter(Boolean)
    .map((seg) => (/^\d+$/.test(seg) ? `[${seg}]` : seg))
    .join('.')
    .replace(/\.\[/g, '[');
  return {
    check: 'schema_structure',
    status: 'fail',
    message: `Schema 校验失败: ${readablePath || '(root)'} ${err.message}`,
    node_id: nodeId,
    suggestion: '请检查节点字段类型与结构是否符合 schema 要求',
  };
}

/**
 * 本地校验 task_definition 是否符合 PIPELINE_GRAPH_SCHEMA。
 *
 * @param taskDefinition 任务定义 (含 nodes / edges / viewport)
 * @returns errors: CheckItem 列表 (空数组表示通过)
 */
export function validatePipelineGraph(taskDefinition: Record<string, unknown>): CheckItem[] {
  const nodes = Array.isArray(taskDefinition.nodes) ? (taskDefinition.nodes as unknown[]) : [];
  const valid = validateFn(taskDefinition);
  if (valid) return [];
  const ajvErrors = validateFn.errors ?? [];
  return ajvErrors.map((err) => ajvErrorToCheckItem(err, nodes));
}
