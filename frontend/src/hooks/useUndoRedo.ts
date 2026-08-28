import { useState, useCallback, useRef } from 'react';
import type { Node, Edge } from '@xyflow/react';

interface HistoryEntry {
  nodes: Node[];
  edges: Edge[];
}

interface UseUndoRedoReturn {
  undo: () => HistoryEntry | null;
  redo: () => HistoryEntry | null;
  canUndo: boolean;
  canRedo: boolean;
  pushState: (nodes: Node[], edges: Edge[]) => void;
  clear: () => void;
}

export function useUndoRedo(maxHistory = 50): UseUndoRedoReturn {
  const [past, setPast] = useState<HistoryEntry[]>([]);
  const [future, setFuture] = useState<HistoryEntry[]>([]);
  const skipRef = useRef(false);

  const undo = useCallback((): HistoryEntry | null => {
    if (past.length === 0) return null;
    const newPast = [...past];
    const entry = newPast.pop()!;
    setPast(newPast);
    setFuture((f) => [entry, ...f]);
    return entry;
  }, [past]);

  const redo = useCallback((): HistoryEntry | null => {
    if (future.length === 0) return null;
    const newFuture = [...future];
    const entry = newFuture.shift()!;
    setFuture(newFuture);
    setPast((p) => [...p, entry]);
    return entry;
  }, [future]);

  const pushState = useCallback(
    (nodes: Node[], edges: Edge[]) => {
      if (skipRef.current) {
        skipRef.current = false;
        return;
      }
      const entry: HistoryEntry = {
        nodes: JSON.parse(JSON.stringify(nodes)),
        edges: JSON.parse(JSON.stringify(edges)),
      };
      setPast((prev) => {
        const newPast = [...prev, entry];
        if (newPast.length > maxHistory) newPast.shift();
        return newPast;
      });
      setFuture([]);
    },
    [maxHistory],
  );

  const clear = useCallback(() => {
    setPast([]);
    setFuture([]);
  }, []);

  return {
    undo,
    redo,
    canUndo: past.length > 0,
    canRedo: future.length > 0,
    pushState,
    clear,
  };
}
