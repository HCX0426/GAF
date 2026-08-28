import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useWebSocket, useWebSocketSend } from '@/hooks/useWebSocket';

// Pattern A: mock the wsClient singleton. vi.hoisted runs before imports so
// the same mock instance is available inside vi.mock factory and in tests.
const mockWsClient = vi.hoisted(() => {
  const handlers = new Map<string, Set<(d: Record<string, unknown>) => void>>();
  return {
    connect: vi.fn(),
    disconnect: vi.fn(),
    send: vi.fn(),
    onMessage: vi.fn((t: string, h: (d: Record<string, unknown>) => void) => {
      if (!handlers.has(t)) handlers.set(t, new Set());
      handlers.get(t)!.add(h);
    }),
    offMessage: vi.fn((t: string, h: (d: Record<string, unknown>) => void) => {
      handlers.get(t)?.delete(h);
    }),
    onOpen: vi.fn(),
    offOpen: vi.fn(),
    onClose: vi.fn(),
    offClose: vi.fn(),
    emitMessage(t: string, d: Record<string, unknown>) {
      handlers.get(t)?.forEach((h) => h(d));
      handlers.get('*')?.forEach((h) => h(d));
    },
    hasHandler(t: string) {
      return (handlers.get(t)?.size ?? 0) > 0;
    },
  };
});

vi.mock('@/websocket/client', () => ({ wsClient: mockWsClient }));

describe('useWebSocket', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('registers a message handler on mount and unregisters on unmount', () => {
    const handler = vi.fn();
    const { unmount } = renderHook(() => useWebSocket('task_update', handler));

    expect(mockWsClient.onMessage).toHaveBeenCalledTimes(1);
    expect(mockWsClient.onMessage).toHaveBeenCalledWith('task_update', expect.any(Function));
    expect(mockWsClient.hasHandler('task_update')).toBe(true);

    unmount();

    expect(mockWsClient.offMessage).toHaveBeenCalledTimes(1);
    expect(mockWsClient.offMessage).toHaveBeenCalledWith('task_update', expect.any(Function));
    expect(mockWsClient.hasHandler('task_update')).toBe(false);
  });

  it('forwards received messages to the handler callback', () => {
    const handler = vi.fn();
    renderHook(() => useWebSocket('task_update', handler));

    const payload = { id: 1, status: 'running' };
    mockWsClient.emitMessage('task_update', payload);

    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith(payload);
  });

  it('does not re-subscribe when only the handler changes (stable ref pattern)', () => {
    const handler = vi.fn();
    const { rerender } = renderHook(() => useWebSocket('task_update', handler));

    expect(mockWsClient.onMessage).toHaveBeenCalledTimes(1);

    rerender();

    // onMessage should NOT be called again — only type changes re-subscribe
    expect(mockWsClient.onMessage).toHaveBeenCalledTimes(1);
    expect(mockWsClient.offMessage).not.toHaveBeenCalled();
  });

  it('re-subscribes when the message type changes', () => {
    const handler = vi.fn();
    const { rerender } = renderHook(({ type }) => useWebSocket(type, handler), {
      initialProps: { type: 'task_update' },
    });

    expect(mockWsClient.onMessage).toHaveBeenCalledWith('task_update', expect.any(Function));

    rerender({ type: 'device.status' });

    expect(mockWsClient.offMessage).toHaveBeenCalledWith('task_update', expect.any(Function));
    expect(mockWsClient.onMessage).toHaveBeenCalledWith('device.status', expect.any(Function));
  });

  it('wildcard type "*" receives all messages', () => {
    const handler = vi.fn();
    renderHook(() => useWebSocket('*', handler));

    mockWsClient.emitMessage('anything', { foo: 1 });
    mockWsClient.emitMessage('other', { bar: 2 });

    expect(handler).toHaveBeenCalledTimes(2);
  });
});

describe('useWebSocketSend', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns a function that calls wsClient.send', () => {
    const { result } = renderHook(() => useWebSocketSend());
    result.current('ping', { ts: 123 });

    expect(mockWsClient.send).toHaveBeenCalledTimes(1);
    expect(mockWsClient.send).toHaveBeenCalledWith('ping', { ts: 123 });
  });
});
