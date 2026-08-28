import { Handle, Position, type NodeProps } from '@xyflow/react';
import { NODE_TYPE_CATEGORY, CATEGORY_COLORS, type GafNodeData } from '@/types/models';

const STATUS_COLORS: Record<string, string> = {
  pending: '#d9d9d9',
  running: '#1890ff',
  success: '#52c41a',
  failed: '#ff4d4f',
  skipped: '#fa8c16',
};

export function GafPipelineNode({ data, selected }: NodeProps) {
  const nodeData = data as unknown as GafNodeData;
  const category = NODE_TYPE_CATEGORY[nodeData.nodeType] || '逻辑控制';
  const categoryColor = CATEGORY_COLORS[category];
  const statusColor = nodeData.status ? STATUS_COLORS[nodeData.status] : undefined;
  const isBranch = nodeData.nodeType === 'branch';

  return (
    <div
      style={{
        minWidth: 150,
        maxWidth: 220,
        borderRadius: 6,
        border: `${selected ? 2 : 1}px solid ${selected ? '#1890ff' : '#d9d9d9'}`,
        boxShadow: selected
          ? '0 0 0 2px rgba(24,144,255,0.2), 0 2px 8px rgba(0,0,0,0.12)'
          : '0 1px 4px rgba(0,0,0,0.08)',
        background: '#fff',
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      <div className="gaf-w-full" style={{ height: 4, background: categoryColor }} />

      {nodeData.status && (
        <div
          style={{
            position: 'absolute',
            top: 6,
            right: 6,
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: statusColor,
            boxShadow: nodeData.status === 'running' ? `0 0 4px ${statusColor}, 0 0 8px ${statusColor}80` : undefined,
          }}
        />
      )}

      <div style={{ padding: '8px 12px 4px' }}>
        <div className="gaf-font-semibold" style={{ fontSize: 13, color: '#262626', lineHeight: 1.4 }}>
          {nodeData.label}
        </div>
      </div>

      <div style={{ padding: '0 12px 8px' }}>
        <div className="gaf-text-xxs" style={{ color: categoryColor }}>
          {nodeData.nodeType}
        </div>
        {nodeData.description && (
          <div className="gaf-text-xxs" style={{ color: '#8c8c8c', marginTop: 2 }}>
            {nodeData.description}
          </div>
        )}
      </div>

      <Handle
        type="target"
        position={Position.Top}
        style={{ background: categoryColor, width: 8, height: 8, border: '2px solid #fff' }}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        style={{ background: categoryColor, width: 8, height: 8, border: '2px solid #fff' }}
      />

      {isBranch && (
        <>
          <Handle
            type="source"
            position={Position.Left}
            id="false"
            style={{ background: '#ff4d4f', width: 8, height: 8, border: '2px solid #fff' }}
            title="false"
          />
          <Handle
            type="source"
            position={Position.Right}
            id="true"
            style={{ background: '#52c41a', width: 8, height: 8, border: '2px solid #fff' }}
            title="true"
          />
        </>
      )}
    </div>
  );
}

export default GafPipelineNode;
