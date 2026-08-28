/**
 * TD-336 #4: usePipelineStore 测试 — 覆盖节点/边 CRUD + 撤销/重做 + dirty 标记
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { usePipelineStore } from '@/stores/usePipelineStore';
import type { Node, Edge } from '@xyflow/react';

const makeNode = (id: string): Node => ({ id, type: 'default', position: { x: 0, y: 0 }, data: { label: id } });
const makeEdge = (id: string, source: string, target: string): Edge => ({ id, source, target });

beforeEach(() => {
  usePipelineStore.getState().reset();
});

describe('usePipelineStore', () => {
  describe('初始状态', () => {
    it('nodes/edges 应为空数组', () => {
      const s = usePipelineStore.getState();
      expect(s.nodes).toEqual([]);
      expect(s.edges).toEqual([]);
    });

    it('isDirty 应为 false', () => {
      expect(usePipelineStore.getState().isDirty).toBe(false);
    });

    it('pipelineName 应为默认值', () => {
      expect(usePipelineStore.getState().pipelineName).toBe('未命名 Pipeline');
    });

    it('history.past/future 应为空', () => {
      const s = usePipelineStore.getState();
      expect(s.history.past).toEqual([]);
      expect(s.history.future).toEqual([]);
    });
  });

  describe('节点 CRUD', () => {
    it('addNode 应追加节点并标记 dirty', () => {
      const { addNode } = usePipelineStore.getState();
      addNode(makeNode('n1'));
      const s = usePipelineStore.getState();
      expect(s.nodes).toHaveLength(1);
      expect(s.isDirty).toBe(true);
    });

    it('removeNode 应移除节点 + 关联边并清除选中', () => {
      const { addNode, addEdge, removeNode } = usePipelineStore.getState();
      addNode(makeNode('n1'));
      addNode(makeNode('n2'));
      addEdge(makeEdge('e1', 'n1', 'n2'));
      usePipelineStore.setState({ selectedNodeId: 'n1' });

      removeNode('n1');

      const s = usePipelineStore.getState();
      expect(s.nodes).toHaveLength(1);
      expect(s.nodes[0].id).toBe('n2');
      expect(s.edges).toHaveLength(0); // 关联边被移除
      expect(s.selectedNodeId).toBeNull(); // 选中被清除
    });

    it('updateNode 应合并节点 data', () => {
      const { addNode, updateNode } = usePipelineStore.getState();
      addNode(makeNode('n1'));
      updateNode('n1', { data: { label: 'updated' } });

      const s = usePipelineStore.getState();
      expect(s.nodes[0].data.label).toBe('updated');
    });
  });

  describe('边 CRUD', () => {
    it('addEdge 应追加边并标记 dirty', () => {
      const { addNode, addEdge } = usePipelineStore.getState();
      addNode(makeNode('n1'));
      addNode(makeNode('n2'));
      addEdge(makeEdge('e1', 'n1', 'n2'));

      const s = usePipelineStore.getState();
      expect(s.edges).toHaveLength(1);
      expect(s.isDirty).toBe(true);
    });

    it('removeEdge 应移除指定边', () => {
      const { addNode, addEdge, removeEdge } = usePipelineStore.getState();
      addNode(makeNode('n1'));
      addNode(makeNode('n2'));
      addEdge(makeEdge('e1', 'n1', 'n2'));
      addEdge(makeEdge('e2', 'n1', 'n2'));

      removeEdge('e1');

      expect(usePipelineStore.getState().edges).toHaveLength(1);
      expect(usePipelineStore.getState().edges[0].id).toBe('e2');
    });
  });

  describe('撤销/重做', () => {
    it('undo 空历史时应无操作', () => {
      const { undo } = usePipelineStore.getState();
      undo();
      expect(usePipelineStore.getState().nodes).toEqual([]);
    });

    it('addNode 后 undo 应恢复空状态并记入 future', () => {
      const { addNode, undo } = usePipelineStore.getState();
      addNode(makeNode('n1'));
      expect(usePipelineStore.getState().nodes).toHaveLength(1);

      undo();

      const s = usePipelineStore.getState();
      expect(s.nodes).toHaveLength(0);
      expect(s.history.future).toHaveLength(1);
    });

    it('undo 后 redo 应恢复操作', () => {
      const { addNode, undo, redo } = usePipelineStore.getState();
      addNode(makeNode('n1'));
      undo();
      expect(usePipelineStore.getState().nodes).toHaveLength(0);

      redo();

      const s = usePipelineStore.getState();
      expect(s.nodes).toHaveLength(1);
      expect(s.history.future).toHaveLength(0);
    });

    it('redo 空未来时应无操作', () => {
      const { redo } = usePipelineStore.getState();
      redo();
      expect(usePipelineStore.getState().nodes).toEqual([]);
    });

    it('新操作应清空 future 历史', () => {
      const { addNode, undo, addEdge } = usePipelineStore.getState();
      addNode(makeNode('n1'));
      addNode(makeNode('n2'));
      undo();
      expect(usePipelineStore.getState().history.future).toHaveLength(1);

      addEdge(makeEdge('e1', 'n1', 'n1'));
      expect(usePipelineStore.getState().history.future).toHaveLength(0);
    });
  });

  describe('dirty 标记', () => {
    it('markDirty 应设置 isDirty=true', () => {
      usePipelineStore.getState().markDirty();
      expect(usePipelineStore.getState().isDirty).toBe(true);
    });

    it('markClean 应设置 isDirty=false', () => {
      usePipelineStore.getState().markDirty();
      usePipelineStore.getState().markClean();
      expect(usePipelineStore.getState().isDirty).toBe(false);
    });
  });

  describe('reset', () => {
    it('应恢复全部初始状态', () => {
      const { addNode, setPipelineName, reset } = usePipelineStore.getState();
      addNode(makeNode('n1'));
      setPipelineName('custom');
      usePipelineStore.setState({ isDirty: true });

      reset();

      const s = usePipelineStore.getState();
      expect(s.nodes).toEqual([]);
      expect(s.pipelineName).toBe('未命名 Pipeline');
      expect(s.isDirty).toBe(false);
    });
  });
});
