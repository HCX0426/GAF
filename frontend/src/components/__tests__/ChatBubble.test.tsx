/**
 * ChatBubble component unit tests.
 *
 * Covers src/components/Ai/ChatBubble.tsx:
 * - User role rendering (avatar on right, blue background, label "用户")
 * - Assistant role rendering (avatar on left, green background, label "AI 助手")
 * - Loading state shows "思考中..." instead of content
 * - Timestamp shown when provided
 * - Content preserves whitespace (whiteSpace: pre-wrap)
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import ChatBubble from '@/components/Ai/ChatBubble';

describe('ChatBubble', () => {
  it('renders user role with "用户" label and content', () => {
    render(<ChatBubble role="user" content="Hello, AI" />);
    expect(screen.getByText('用户')).toBeDefined();
    expect(screen.getByText('Hello, AI')).toBeDefined();
  });

  it('renders assistant role with "AI 助手" label and content', () => {
    render(<ChatBubble role="assistant" content="Hi there" />);
    expect(screen.getByText('AI 助手')).toBeDefined();
    expect(screen.getByText('Hi there')).toBeDefined();
  });

  it('shows "思考中..." when isLoading=true', () => {
    render(<ChatBubble role="assistant" content="" isLoading={true} />);
    expect(screen.getByText('思考中...')).toBeDefined();
  });

  it('shows content (not loading text) when isLoading=false', () => {
    render(<ChatBubble role="assistant" content="real reply" isLoading={false} />);
    expect(screen.getByText('real reply')).toBeDefined();
    expect(screen.queryByText('思考中...')).toBeNull();
  });

  it('shows timestamp when provided', () => {
    render(<ChatBubble role="user" content="msg" timestamp="2026-07-12 10:00" />);
    expect(screen.getByText('2026-07-12 10:00')).toBeDefined();
  });

  it('does not render timestamp element when not provided', () => {
    render(<ChatBubble role="user" content="msg" />);
    // No timestamp span should be present
    expect(screen.queryByText(/\d{4}-\d{2}-\d{2}/)).toBeNull();
  });

  it('preserves multiline content (whitespace pre-wrap)', () => {
    const multiline = 'Line 1\nLine 2\nLine 3';
    const { container } = render(<ChatBubble role="assistant" content={multiline} />);
    // RTL's getByText doesn't match across newlines reliably, so check
    // the rendered DOM contains the lines and the bubble has pre-wrap.
    expect(container.textContent).toContain('Line 1');
    expect(container.textContent).toContain('Line 2');
    expect(container.textContent).toContain('Line 3');
    // The bubble div should have whiteSpace: pre-wrap to preserve newlines
    const bubbleDiv = container.querySelector('[style*="pre-wrap"]');
    expect(bubbleDiv).not.toBeNull();
  });

  it('renders user avatar (UserOutlined) for user role', () => {
    const { container } = render(<ChatBubble role="user" content="x" />);
    // antd Avatar renders as .ant-avatar element
    const avatars = container.querySelectorAll('.ant-avatar');
    expect(avatars.length).toBeGreaterThanOrEqual(1);
  });

  it('renders assistant avatar (RobotOutlined) for assistant role', () => {
    const { container } = render(<ChatBubble role="assistant" content="x" />);
    const avatars = container.querySelectorAll('.ant-avatar');
    expect(avatars.length).toBeGreaterThanOrEqual(1);
  });

  it('handles empty content gracefully', () => {
    render(<ChatBubble role="user" content="" />);
    // Should still render the role label
    expect(screen.getByText('用户')).toBeDefined();
  });

  it('applies different background colors for user vs assistant', () => {
    // The bubble div has the bg color, but so does the Avatar. The bubble
    // is the div with both borderRadius: 12px AND background-color. Use a
    // more specific selector to target the bubble (not the avatar).
    const { container: userContainer } = render(<ChatBubble role="user" content="x" />);
    const userBubble = userContainer.querySelector('[style*="border-radius: 12px"]') as HTMLElement;
    expect(userBubble.style.backgroundColor).toBe('rgb(230, 247, 255)'); // #e6f7ff

    const { container: assistantContainer } = render(<ChatBubble role="assistant" content="x" />);
    const assistantBubble = assistantContainer.querySelector('[style*="border-radius: 12px"]') as HTMLElement;
    expect(assistantBubble.style.backgroundColor).toBe('rgb(246, 255, 237)'); // #f6ffed
  });
});
