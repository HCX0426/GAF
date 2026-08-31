/**
 * TrajectoryTimeline component unit tests.
 *
 * Covers src/components/Ai/TrajectoryTimeline.tsx:
 * - Shows "no data" placeholder when trajectory is empty
 * - Renders each node type (router / tools / responder) label
 * - Shows the step number tag for each step
 * - Shows tool names on a tools node
 * - Shows tool-call names + tokens on a router node
 * - Shows tokens on a responder node
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { TrajectoryStep } from '@/api/ai';

const t = (key: string, params?: Record<string, string | number | undefined>) => {
  if (key === 'ailab.trajectory_tokens') return `${params?.tokens} tokens`;
  if (key === 'ailab.trajectory_step') return `Step ${params?.step}`;
  const map: Record<string, string> = {
    'ailab.trajectory_title': 'Agent Trajectory',
    'ailab.trajectory_route': 'Tool Routing',
    'ailab.trajectory_tools': 'Tool Calls',
    'ailab.trajectory_respond': 'Generate Response',
    'ailab.trajectory_no_data': 'No trajectory data',
  };
  return map[key] ?? key;
};

vi.mock('@/i18n', () => ({
  useTranslation: () => t,
}));

// Import after the i18n mock so the component picks up the mocked hook.
import { TrajectoryTimeline } from '@/components/Ai/TrajectoryTimeline';

describe('TrajectoryTimeline', () => {
  it('shows placeholder when trajectory is empty', () => {
    render(<TrajectoryTimeline trajectory={[]} />);
    expect(screen.getByText('No trajectory data')).toBeDefined();
  });

  it('renders a router step with tool-call name and tokens', () => {
    const steps: TrajectoryStep[] = [
      {
        step: 1,
        type: 'router',
        tool_calls: [{ name: 'get_execution_detail', args: { execution_id: 42 } }],
        tokens: { prompt_tokens: 20, completion_tokens: 5, total_tokens: 25 },
      },
      { step: 2, type: 'tools', count: 1, names: ['get_execution_detail'] },
      {
        step: 3,
        type: 'responder',
        tokens: { prompt_tokens: 60, completion_tokens: 40, total_tokens: 100 },
      },
    ];
    const { container } = render(<TrajectoryTimeline trajectory={steps} />);

    expect(screen.getByText('Tool Routing')).toBeDefined();
    expect(screen.getByText('Tool Calls')).toBeDefined();
    expect(screen.getByText('Generate Response')).toBeDefined();
    expect(screen.getByText('Step 1')).toBeDefined();
    expect(screen.getByText('Step 2')).toBeDefined();
    expect(screen.getByText('Step 3')).toBeDefined();
    // router tool-call name
    expect(screen.getAllByText('get_execution_detail').length).toBeGreaterThanOrEqual(1);
    // router tokens
    expect(screen.getByText('25 tokens')).toBeDefined();
    // responder tokens
    expect(screen.getByText('100 tokens')).toBeDefined();
    // node test ids present
    expect(container.querySelector('[data-testid="trajectory-step-router"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="trajectory-step-tools"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="trajectory-step-responder"]')).not.toBeNull();
  });

  it('does not render a token tag on a router node with no token usage', () => {
    const steps: TrajectoryStep[] = [{ step: 1, type: 'router', tool_calls: [{ name: 'get_execution_detail' }] }];
    const { container } = render(<TrajectoryTimeline trajectory={steps} />);
    expect(screen.getByText('Tool Routing')).toBeDefined();
    expect(container.textContent).not.toContain('tokens');
  });
});
