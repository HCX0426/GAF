import { useState, useCallback, useRef } from 'react';
import * as pipelineApi from '@/api/pipelines';
import { flowToPipeline } from '@/utils/pipelineConverter';
import type { Node, Edge } from '@xyflow/react';

type SaveStatus = 'saved' | 'saving' | 'unsaved' | 'error';

interface UsePipelineSaveReturn {
  saveStatus: SaveStatus;
  save: (name: string, nodes: Node[], edges: Edge[], pipelineId?: string | number) => Promise<number | undefined>;
  markDirty: () => void;
  lastSavedAt: Date | null;
}

export function usePipelineSave(): UsePipelineSaveReturn {
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('saved');
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  // H13 fix: pipelineApi.updatePipeline expects number, and PipelineDetail.id is number.
  // Previously this was string — assigning result.id (number) caused a type mismatch.
  const currentPipelineIdRef = useRef<number | undefined>(undefined);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const save = useCallback(
    async (name: string, nodes: Node[], edges: Edge[], pipelineId?: string | number): Promise<number | undefined> => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      setSaveStatus('saving');
      try {
        const json = flowToPipeline(name, nodes, edges);
        const graphData = {
          nodes: json.nodes,
          edges: json.edges,
        };
        // H13 fix: normalize incoming id (string from URL route or number from ref) to number.
        const incomingId = pipelineId !== undefined ? Number(pipelineId) : undefined;
        const existingId =
          incomingId !== undefined && !Number.isNaN(incomingId) ? incomingId : currentPipelineIdRef.current;
        if (existingId !== undefined) {
          await pipelineApi.updatePipeline(existingId, {
            name: json.name,
            description: json.description,
            graph_data: graphData,
          });
          currentPipelineIdRef.current = existingId;
          setSaveStatus('saved');
          setLastSavedAt(new Date());
          return existingId;
        } else {
          const result = await pipelineApi.createPipeline({
            name: json.name,
            description: json.description,
            graph_data: graphData,
          });
          currentPipelineIdRef.current = result.id;
          setSaveStatus('saved');
          setLastSavedAt(new Date());
          return result.id;
        }
      } catch (err) {
        console.error('Pipeline save failed:', err);
        setSaveStatus('error');
        return undefined;
      }
    },
    [],
  );

  const markDirty = useCallback(() => {
    setSaveStatus((s) => (s === 'saved' || s === 'error' ? 'unsaved' : s));
  }, []);

  return { saveStatus, save, markDirty, lastSavedAt };
}
