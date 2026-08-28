import { create } from 'zustand';
import type { Node, Edge } from '@xyflow/react';

/**
 * history record snapshot
 */
interface HistorySnapshot {
  nodes: Node[];
  edges: Edge[];
}

/**
 * Pipeline editor global status
 */
interface PipelineState {
  pipelineId: string | null;
  pipelineName: string;
  nodes: Node[];
  edges: Edge[];
  selectedNodeId: string | null;
  isDirty: boolean;
  history: {
    past: HistorySnapshot[];
    future: HistorySnapshot[];
  };

  setPipelineId: (id: string | null) => void;
  setPipelineName: (name: string) => void;
  setNodes: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;
  setSelectedNodeId: (id: string | null) => void;
  markDirty: () => void;
  markClean: () => void;

  addNode: (node: Node) => void;
  removeNode: (nodeId: string) => void;
  updateNode: (nodeId: string, data: Partial<Node>) => void;
  addEdge: (edge: Edge) => void;
  removeEdge: (edgeId: string) => void;

  pushHistory: () => void;
  undo: () => void;
  redo: () => void;
  reset: () => void;
}

const MAX_HISTORY = 20;

const initialState = {
  pipelineId: null,
  pipelineName: '未命名 Pipeline',
  nodes: [] as Node[],
  edges: [] as Edge[],
  selectedNodeId: null,
  isDirty: false,
  history: {
    past: [] as HistorySnapshot[],
    future: [] as HistorySnapshot[],
  },
};

function makeSnapshot(nodes: Node[], edges: Edge[]): HistorySnapshot {
  return { nodes: JSON.parse(JSON.stringify(nodes)), edges: JSON.parse(JSON.stringify(edges)) };
}

/**
 * Pipeline visualization editor status management
 * management node / edge CRUD, select in status, dirty mark, undo / redo history
 */
export const usePipelineStore = create<PipelineState>((set, get) => ({
  ...initialState,

  setPipelineId: (pipelineId) => set({ pipelineId }),
  setPipelineName: (pipelineName) => set({ pipelineName }),
  setNodes: (nodes) => set({ nodes, isDirty: true }),
  setEdges: (edges) => set({ edges, isDirty: true }),
  setSelectedNodeId: (selectedNodeId) => set({ selectedNodeId }),
  markDirty: () => set({ isDirty: true }),
  markClean: () => set({ isDirty: false }),

  addNode: (node) => {
    const { nodes, edges } = get();
    const snapshot = makeSnapshot(nodes, edges);
    set({
      nodes: [...nodes, node],
      isDirty: true,
      history: { past: [...get().history.past, snapshot].slice(-MAX_HISTORY), future: [] },
    });
  },

  removeNode: (nodeId) => {
    const { nodes, edges } = get();
    const snapshot = makeSnapshot(nodes, edges);
    set({
      nodes: nodes.filter((n) => n.id !== nodeId),
      edges: edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
      isDirty: true,
      selectedNodeId: get().selectedNodeId === nodeId ? null : get().selectedNodeId,
      history: { past: [...get().history.past, snapshot].slice(-MAX_HISTORY), future: [] },
    });
  },

  updateNode: (nodeId, data) => {
    const { nodes, edges } = get();
    const snapshot = makeSnapshot(nodes, edges);
    set({
      nodes: nodes.map((n) => (n.id === nodeId ? { ...n, ...data } : n)),
      isDirty: true,
      history: { past: [...get().history.past, snapshot].slice(-MAX_HISTORY), future: [] },
    });
  },

  addEdge: (edge) => {
    const { nodes, edges } = get();
    const snapshot = makeSnapshot(nodes, edges);
    set({
      edges: [...edges, edge],
      isDirty: true,
      history: { past: [...get().history.past, snapshot].slice(-MAX_HISTORY), future: [] },
    });
  },

  removeEdge: (edgeId) => {
    const { nodes, edges } = get();
    const snapshot = makeSnapshot(nodes, edges);
    set({
      edges: edges.filter((e) => e.id !== edgeId),
      isDirty: true,
      history: { past: [...get().history.past, snapshot].slice(-MAX_HISTORY), future: [] },
    });
  },

  pushHistory: () => {
    const { nodes, edges, history } = get();
    const snapshot = makeSnapshot(nodes, edges);
    const newPast = [...history.past, snapshot].slice(-MAX_HISTORY);
    set({ history: { past: newPast, future: [] } });
  },

  undo: () => {
    const { nodes, edges, history } = get();
    if (history.past.length === 0) return;
    const previous = history.past[history.past.length - 1];
    const newPast = history.past.slice(0, -1);
    const snapshot = makeSnapshot(nodes, edges);
    set({
      nodes: previous.nodes,
      edges: previous.edges,
      isDirty: true,
      history: {
        past: newPast,
        future: [snapshot, ...history.future].slice(0, MAX_HISTORY),
      },
    });
  },

  redo: () => {
    const { nodes, edges, history } = get();
    if (history.future.length === 0) return;
    const next = history.future[0];
    const newFuture = history.future.slice(1);
    const snapshot = makeSnapshot(nodes, edges);
    set({
      nodes: next.nodes,
      edges: next.edges,
      isDirty: true,
      history: {
        past: [...history.past, snapshot].slice(-MAX_HISTORY),
        future: newFuture,
      },
    });
  },

  reset: () => set(initialState),
}));
