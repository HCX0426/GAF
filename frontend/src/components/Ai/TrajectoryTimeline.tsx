/**
 * Agent trajectory timeline (Phase 2 observability layer).
 *
 * Renders the LangGraph execution trail produced by the hand-written
 * StateGraph (backend gaf_ai.agent.langgraph_graph). Each step is a node in
 * the vertical timeline with a node-type-specific icon/color:
 *   - router     : the LLM decides which tools to call (tool_calls + tokens)
 *   - tools      : the resolved tools that actually ran (names)
 *   - responder  : the LLM composes the final answer (tokens)
 */
import type { ReactNode } from 'react';
import { Tag, Timeline, Typography } from 'antd';
import { ApartmentOutlined, ToolOutlined, CheckCircleOutlined } from '@ant-design/icons';
import type { TrajectoryStep } from '@/api/ai';
import { useTranslation } from '@/i18n';

/** Per-node-type presentation config. */
const NODE_META: Record<TrajectoryStep['type'], { color: string; icon: ReactNode; labelKey: string }> = {
  router: { color: 'blue', icon: <ApartmentOutlined />, labelKey: 'ailab.trajectory_route' },
  tools: { color: 'orange', icon: <ToolOutlined />, labelKey: 'ailab.trajectory_tools' },
  responder: { color: 'green', icon: <CheckCircleOutlined />, labelKey: 'ailab.trajectory_respond' },
};

interface TrajectoryTimelineProps {
  trajectory: TrajectoryStep[];
}

/** Vertical timeline of LangGraph nodes with tool + token detail. */
export function TrajectoryTimeline({ trajectory }: TrajectoryTimelineProps) {
  const t = useTranslation();

  if (!trajectory.length) {
    return <Typography.Text type="secondary">{t('ailab.trajectory_no_data')}</Typography.Text>;
  }

  return (
    <Timeline
      items={trajectory.map((step) => {
        const meta = NODE_META[step.type] ?? NODE_META.router;
        const total = step.tokens?.total_tokens ?? 0;
        return {
          color: meta.color,
          icon: meta.icon,
          content: (
            <div key={`traj-${step.step}`} data-testid={`trajectory-step-${step.type}`}>
              <div className="gaf-mb-xs">
                <Tag color={meta.color}>{t(meta.labelKey)}</Tag>
                <Tag>{t('ailab.trajectory_step', { step: step.step })}</Tag>
                {step.type === 'responder' && total > 0 && (
                  <Tag color="cyan">{t('ailab.trajectory_tokens', { tokens: total })}</Tag>
                )}
              </div>
              {step.type === 'tools' && step.names && step.names.length > 0 && (
                <div className="gaf-mb-xs">
                  {step.names.map((name, idx) => (
                    <Tag key={`${name}-${idx}`} color="geekblue">
                      {name}
                    </Tag>
                  ))}
                </div>
              )}
              {step.type === 'router' &&
                step.tool_calls &&
                step.tool_calls.map((tc, idx) => (
                  <div key={`tc-${idx}`} className="gaf-mb-xs">
                    <Tag color="purple">{tc.name}</Tag>
                    {total > 0 && (
                      <Typography.Text type="secondary" className="gaf-text-xs">
                        {t('ailab.trajectory_tokens', { tokens: total })}
                      </Typography.Text>
                    )}
                  </div>
                ))}
            </div>
          ),
        };
      })}
    />
  );
}

export default TrajectoryTimeline;
