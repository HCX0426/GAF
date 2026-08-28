import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useLogStream, type LogStreamEntry } from '@/hooks/useLogStream';

// Mutable auth state shared with the mocked useAuthStore selector.
const authState = vi.hoisted(() => ({
  isAuthenticated: false,
  accessToken: null as string | null,
}));

vi.mock('@/stores/useAuthStore', () => ({
  useAuthStore: (selector: (s: typeof authState) => unknown) => selector(authState),
}));

// Pattern B: the hook calls `new WebSocket(url, subprotocols)` directly.
const createdInstances: {
  url: string;
  protocols: string | string[];
  readyState: number;
  onopen: ((ev: Event) => void) | null;
  onmessage: ((ev: MessageEvent) => void) | null;
  onclose: ((ev: CloseEvent) => void) | null;
  onerror: ((ev: Event) => void) | null;
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
  authState.isAuthenticated = false;
  authState.accessToken = null;
  vi.useFakeTimers();
  vi.stubGlobal('WebSocket', MockWebSocket);
});

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('useLogStream', () => {
  it('does not connect when not authenticated', () => {
    authState.isAuthenticated = false;
    authState.accessToken = 'token';
    renderHook(() => useLogStream(() => {}));
    expect(createdInstances).toHaveLength(0);
  });

  it('does not connect when no access token', () => {
    authState.isAuthenticated = true;
    authState.accessToken = null;
    renderHook(() => useLogStream(() => {}));
    expect(createdInstances).toHaveLength(0);
  });

  it('connects to /ws/logs/ with JWT subprotocol when authenticated', () => {
    authState.isAuthenticated = true;
    authState.accessToken = 'jwt-abc';
    renderHook(() => useLogStream(() => {}));

    expect(createdInstances).toHaveLength(1);
    expect(createdInstances[0].url).toContain('/ws/logs/');
    expect(createdInstances[0].protocols).toEqual(['access.jwt-abc']);
  });

  it('receives and dispatches log.entry payloads', () => {
    authState.isAuthenticated = true;
    authState.accessToken = 'tkn';
    const onEntry = vi.fn();
    renderHook(() => useLogStream(onEntry));

    const entry: LogStreamEntry = {
      timestamp: '2026-01-01T00:00:00Z',
      level: 'INFO',
      source: 'agent',
      message: 'task started',
    };
    act(() => {
      createdInstances[0].emitMessage({ type: 'log.entry', payload: entry });
    });

    expect(onEntry).toHaveBeenCalledTimes(1);
    expect(onEntry).toHaveBeenCalledWith(entry);
  });

  it('ignores non-log.entry message types', () => {
    authState.isAuthenticated = true;
    authState.accessToken = 'tkn';
    const onEntry = vi.fn();
    renderHook(() => useLogStream(onEntry));

    act(() => {
      createdInstances[0].emitMessage({ type: 'other', payload: { foo: 1 } });
    });

    expect(onEntry).not.toHaveBeenCalled();
  });

  it('ignores log.entry without a payload', () => {
    authState.isAuthenticated = true;
    authState.accessToken = 'tkn';
    const onEntry = vi.fn();
    renderHook(() => useLogStream(onEntry));

    act(() => {
      createdInstances[0].emitMessage({ type: 'log.entry' });
    });

    expect(onEntry).not.toHaveBeenCalled();
  });

  it('ignores malformed JSON without throwing', () => {
    authState.isAuthenticated = true;
    authState.accessToken = 'tkn';
    const onEntry = vi.fn();
    renderHook(() => useLogStream(onEntry));

    expect(() => {
      createdInstances[0].onmessage?.({ data: '{bad json' } as MessageEvent);
    }).not.toThrow();
    expect(onEntry).not.toHaveBeenCalled();
  });

  it('closes the WebSocket on unmount', () => {
    authState.isAuthenticated = true;
    authState.accessToken = 'tkn';
    const { unmount } = renderHook(() => useLogStream(() => {}));

    // Advance timer so readyState becomes OPEN before unmount.
    act(() => {
      vi.advanceTimersByTime(1);
    });

    const ws = createdInstances[0];
    const closeSpy = vi.spyOn(ws, 'close');
    unmount();

    expect(closeSpy).toHaveBeenCalled();
  });

  // TD-080: isConnected is now reactive (useState). Previously it was a ref,
  // so updates never triggered re-renders and result.current.isConnected was
  // effectively always the initial false. The fix uses useState so consumers
  // can render connection status.
  it('isConnected starts false and becomes true after ws.open', () => {
    authState.isAuthenticated = true;
    authState.accessToken = 'tkn';
    const { result } = renderHook(() => useLogStream(() => {}));

    expect(result.current.isConnected).toBe(false);

    // MockWebSocket auto-opens on next timer tick.
    act(() => {
      vi.advanceTimersByTime(1);
    });

    expect(result.current.isConnected).toBe(true);
  });

  it('isConnected becomes false after ws.close', () => {
    authState.isAuthenticated = true;
    authState.accessToken = 'tkn';
    const { result } = renderHook(() => useLogStream(() => {}));

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current.isConnected).toBe(true);

    act(() => {
      createdInstances[0].close();
    });
    expect(result.current.isConnected).toBe(false);
  });
});
