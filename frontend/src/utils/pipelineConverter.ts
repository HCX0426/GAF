import type { Node, Edge } from '@xyflow/react';
import type { PipelineNodeType, GafNodeData } from '@/types/models';

/** Pipeline JSON format */
export interface PipelineJSON {
  name: string;
  description?: string;
  version?: number;
  nodes: PipelineNodeJSON[];
  edges: PipelineEdgeJSON[];
}

export interface PipelineNodeJSON {
  id: string;
  type: PipelineNodeType;
  position: { x: number; y: number };
  data: {
    label: string;
    config: Record<string, unknown>;
  };
}

export interface PipelineEdgeJSON {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
  label?: string;
}

/**
 * React Flow nodes/edges → Pipeline JSON
 */
export function flowToPipeline(
  name: string,
  nodes: Node[],
  edges: Edge[],
  description?: string,
  version?: number,
): PipelineJSON {
  return {
    name,
    description,
    version,
    nodes: nodes.map((n) => ({
      id: n.id,
      type: (n.data as unknown as GafNodeData)?.nodeType || 'click',
      position: { x: n.position.x, y: n.position.y },
      data: {
        label: (n.data as unknown as GafNodeData)?.label || n.id,
        config: (n.data as unknown as GafNodeData)?.config || {},
      },
    })),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle || undefined,
      targetHandle: e.targetHandle || undefined,
      label: typeof e.label === 'string' ? e.label : undefined,
    })),
  };
}

/**
 * Pipeline JSON → React Flow nodes/edges
 */
export function pipelineToFlow(json: PipelineJSON): { nodes: Node[]; edges: Edge[] } {
  return {
    nodes: json.nodes.map((n) => ({
      id: n.id,
      type: 'gafPipeline',
      position: n.position,
      data: {
        label: n.data.label,
        nodeType: n.type,
        description: '',
        status: 'pending',
        config: n.data.config,
      } satisfies GafNodeData,
    })),
    edges: json.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle,
      targetHandle: e.targetHandle,
      label: e.label,
      type: 'smoothstep',
      animated: true,
    })),
  };
}
