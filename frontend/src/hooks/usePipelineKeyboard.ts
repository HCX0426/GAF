import { useEffect, useRef } from 'react';
import type { Node, Edge } from '@xyflow/react';

interface UsePipelineKeyboardOptions {
  nodes: Node[];
  edges: Edge[];
  setNodes: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;
  onSave: () => void;
  onUndo: () => void;
  onRedo: () => void;
  onDelete: () => void;
  canUndo: boolean;
  canRedo: boolean;
}

export function usePipelineKeyboard(opts: UsePipelineKeyboardOptions): void {
  const clipboardRef = useRef<Node[]>([]);
  // Keep latest opts in a ref so the keydown listener registered once can read fresh values
  const optsRef = useRef(opts);
  optsRef.current = opts;

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const isInput = ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName);
      if (isInput) return;

      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        optsRef.current.onSave();
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        if (optsRef.current.canUndo) optsRef.current.onUndo();
      } else if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
        e.preventDefault();
        if (optsRef.current.canRedo) optsRef.current.onRedo();
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        e.preventDefault();
        optsRef.current.onDelete();
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'c') {
        e.preventDefault();
        const selectedNodes = optsRef.current.nodes.filter((n) => n.selected);
        if (selectedNodes.length > 0) {
          clipboardRef.current = JSON.parse(JSON.stringify(selectedNodes));
        }
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'v') {
        e.preventDefault();
        if (clipboardRef.current.length > 0) {
          const offset = 50;
          const newNodes = clipboardRef.current.map((n) => ({
            ...JSON.parse(JSON.stringify(n)),
            id: `${n.type}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
            position: { x: n.position.x + offset, y: n.position.y + offset },
            selected: false,
          }));
          optsRef.current.setNodes([...optsRef.current.nodes.map((n) => ({ ...n, selected: false })), ...newNodes]);
        }
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
        return;
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);
}
