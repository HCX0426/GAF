import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useScreenshotStream } from '@/hooks/useScreenshotStream';

// Pattern A: mock the wsClient singleton.
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
    },
    hasHandler(t: string) {
      return (handlers.get(t)?.size ?? 0) > 0;
    },
  };
});

vi.mock('@/websocket/client', () => ({ wsClient: mockWsClient }));

describe('useScreenshotStream', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('registers a screenshot_frame handler on mount', () => {
    renderHook(() => useScreenshotStream());

    expect(mockWsClient.onMessage).toHaveBeenCalledWith('screenshot_frame', expect.any(Function));
    expect(mockWsClient.hasHandler('screenshot_frame')).toBe(true);
  });

  it('unregisters handler and sends stop on unmount', () => {
    const { unmount } = renderHook(() => useScreenshotStream());

    unmount();

    expect(mockWsClient.offMessage).toHaveBeenCalledWith('screenshot_frame', expect.any(Function));
    // H16 fix: cleanup sends stop_screenshot_stream
    expect(mockWsClient.send).toHaveBeenCalledWith('stop_screenshot_stream', {});
  });

  it('startStream sends request_screenshot_stream with agent_id and sets isStreaming', () => {
    const { result } = renderHook(() => useScreenshotStream());

    expect(result.current.isStreaming).toBe(false);

    act(() => {
      result.current.startStream('agent-1');
    });

    expect(mockWsClient.send).toHaveBeenCalledWith('request_screenshot_stream', { agent_id: 'agent-1' });
    expect(result.current.isStreaming).toBe(true);
  });

  it('startStream with deviceIds includes them in the payload', () => {
    const { result } = renderHook(() => useScreenshotStream());

    act(() => {
      result.current.startStream('agent-1', ['dev-a', 'dev-b']);
    });

    expect(mockWsClient.send).toHaveBeenCalledWith('request_screenshot_stream', {
      agent_id: 'agent-1',
      device_ids: ['dev-a', 'dev-b'],
    });
  });

  it('receiving a frame updates currentFrame and frameHistory', () => {
    const { result } = renderHook(() => useScreenshotStream());

    expect(result.current.currentFrame).toBeNull();
    expect(result.current.frameHistory).toHaveLength(0);

    act(() => {
      mockWsClient.emitMessage('screenshot_frame', {
        image_base64: 'aGVsbG8=',
        width: 800,
        height: 600,
        captured_at: '2026-01-01T00:00:00Z',
        device_id: 'dev-1',
      });
    });

    expect(result.current.currentFrame).toEqual({
      imageBase64: 'aGVsbG8=',
      width: 800,
      height: 600,
      timestamp: '2026-01-01T00:00:00Z',
    });
    expect(result.current.frameHistory).toHaveLength(1);
  });

  it('receiving frames from multiple devices updates framesByDevice', () => {
    const { result } = renderHook(() => useScreenshotStream());

    act(() => {
      mockWsClient.emitMessage('screenshot_frame', {
        image_base64: 'img1',
        width: 100,
        height: 100,
        captured_at: 't1',
        device_id: 'dev-a',
      });
    });
    act(() => {
      mockWsClient.emitMessage('screenshot_frame', {
        image_base64: 'img2',
        width: 200,
        height: 200,
        captured_at: 't2',
        device_id: 'dev-b',
      });
    });

    expect(Object.keys(result.current.framesByDevice)).toHaveLength(2);
    expect(result.current.framesByDevice['dev-a'].imageBase64).toBe('img1');
    expect(result.current.framesByDevice['dev-b'].imageBase64).toBe('img2');
  });

  // TD-079: frameHistory caps at 50 entries. Previously `[...prev.slice(-50),
  // frame]` produced 51 entries (50 retained + 1 new); the fix uses
  // `[...prev, frame].slice(-50)` (append then cap to most-recent 50).
  it('frameHistory caps at 50 entries', () => {
    const { result } = renderHook(() => useScreenshotStream());

    act(() => {
      for (let i = 0; i < 55; i++) {
        mockWsClient.emitMessage('screenshot_frame', {
          image_base64: `img${i}`,
          width: 1,
          height: 1,
          captured_at: `t${i}`,
          device_id: 'dev',
        });
      }
    });

    expect(result.current.frameHistory).toHaveLength(50);
    // Last 50 frames retained (indices 5..54)
    expect(result.current.frameHistory[0].imageBase64).toBe('img5');
    expect(result.current.frameHistory[49].imageBase64).toBe('img54');
  });

  it('stopStream sends stop with agent_id and clears isStreaming', () => {
    const { result } = renderHook(() => useScreenshotStream());

    act(() => {
      result.current.startStream('agent-42');
    });
    expect(result.current.isStreaming).toBe(true);

    act(() => {
      result.current.stopStream();
    });

    expect(mockWsClient.send).toHaveBeenCalledWith('stop_screenshot_stream', { agent_id: 'agent-42' });
    expect(result.current.isStreaming).toBe(false);
  });
});
