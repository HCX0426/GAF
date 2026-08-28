import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useNotificationWebSocket } from '@/hooks/useNotificationWebSocket';

// Mutable auth state shared with the mocked useAuthStore selector.
const authState = vi.hoisted(() => ({
  accessToken: null as string | null,
}));

vi.mock('@/stores/useAuthStore', () => ({
  useAuthStore: (selector: (s: typeof authState) => unknown) => selector(authState),
}));

// Pattern B: the hook calls `new WebSocket(url, subprotocols)` directly.
// We stub the global WebSocket with a controllable mock and track instances.
const createdInstances: {
  url: string;
  protocols: string | string[];
  readyState: number;
  onopen: ((ev: Event) => void) | null;
  onmessage: ((ev: MessageEvent) => void) | null;
  onclose: ((ev: CloseEvent) => void) | null;
  onerror: ((ev: Event) => void) | null;
  send: (data: string) => void;
  close: () => void;
  emitMessage: (data: unknown) => void;
}[] = [];

class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  url: string;
  protocols: string | string[];
  readyState = 0;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;

  constructor(url: string, protocols?: string | string[]) {
    this.url = url;
    this.protocols = protocols ?? [];
    createdInstances.push(this);
    // Defer onopen so the hook can assign handlers after construction.
    setTimeout(() => {
      if (this.readyState === 0) {
        this.readyState = 1;
        this.onopen?.(new Event('open'));
      }
    }, 0);
  }
  send() {}
  close() {
    if (this.readyState === 3) return;
    this.readyState = 3;
    this.onclose?.(new CloseEvent('close'));
  }
  emitMessage(data: unknown) {
    this.onmessage?.({
      data: typeof data === 'string' ? data : JSON.stringify(data),
    } as MessageEvent);
  }
}

beforeEach(() => {
  createdInstances.length = 0;
  authState.accessToken = null;
  vi.useFakeTimers();
  vi.stubGlobal('WebSocket', MockWebSocket);
});

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('useNotificationWebSocket', () => {
  it('does not connect when disabled', () => {
    authState.accessToken = 'token';
    renderHook(() => useNotificationWebSocket(false, () => {}));
    expect(createdInstances).toHaveLength(0);
  });

  it('does not connect when no access token', () => {
    authState.accessToken = null;
    renderHook(() => useNotificationWebSocket(true, () => {}));
    expect(createdInstances).toHaveLength(0);
  });

  it('connects to /ws/notifications/ with JWT subprotocol when enabled', () => {
    authState.accessToken = 'my-jwt';
    renderHook(() => useNotificationWebSocket(true, () => {}));

    expect(createdInstances).toHaveLength(1);
    expect(createdInstances[0].url).toContain('/ws/notifications/');
    expect(createdInstances[0].protocols).toEqual(['access.my-jwt']);
  });

  it('receives and parses notification messages', () => {
    authState.accessToken = 'tkn';
    const onNotification = vi.fn();
    renderHook(() => useNotificationWebSocket(true, onNotification));

    const payload = { level: 'info', title: 'Hello', message: 'World' };
    act(() => {
      createdInstances[0].emitMessage({ type: 'notification', payload });
    });

    expect(onNotification).toHaveBeenCalledTimes(1);
    expect(onNotification).toHaveBeenCalledWith(payload);
  });

  it('ignores non-notification message types', () => {
    authState.accessToken = 'tkn';
    const onNotification = vi.fn();
    renderHook(() => useNotificationWebSocket(true, onNotification));

    act(() => {
      createdInstances[0].emitMessage({ type: 'other', payload: { foo: 1 } });
    });

    expect(onNotification).not.toHaveBeenCalled();
  });

  it('ignores legacy "data" field after spec-29a #31 cleanup', () => {
    // spec-29a #31: legacy `data` fallback removed. Messages without a
    // `payload` field now dispatch an empty object instead of falling back
    // to `data`. This test documents the new behavior to prevent regression.
    authState.accessToken = 'tkn';
    const onNotification = vi.fn();
    renderHook(() => useNotificationWebSocket(true, onNotification));

    act(() => {
      createdInstances[0].emitMessage({ type: 'notification', data: { title: 'legacy' } });
    });

    expect(onNotification).toHaveBeenCalledWith({});
  });

  it('ignores malformed JSON messages without throwing', () => {
    authState.accessToken = 'tkn';
    const onNotification = vi.fn();
    renderHook(() => useNotificationWebSocket(true, onNotification));

    expect(() => {
      createdInstances[0].onmessage?.({ data: 'not-json' } as MessageEvent);
    }).not.toThrow();
    expect(onNotification).not.toHaveBeenCalled();
  });

  it('closes the WebSocket on unmount', () => {
    authState.accessToken = 'tkn';
    const { unmount } = renderHook(() => useNotificationWebSocket(true, () => {}));

    // Advance timer so readyState becomes OPEN (direct close path).
    act(() => {
      vi.advanceTimersByTime(1);
    });

    const ws = createdInstances[0];
    const closeSpy = vi.spyOn(ws, 'close');
    unmount();

    expect(closeSpy).toHaveBeenCalled();
  });
});
