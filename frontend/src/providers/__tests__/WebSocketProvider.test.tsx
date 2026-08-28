import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, act } from '@testing-library/react';
import { createElement } from 'react';
import { WebSocketProvider, useWebSocketContext } from '@/providers/WebSocketProvider';

// Pattern A: mock the wsClient singleton with lifecycle event tracking.
const mockWsClient = vi.hoisted(() => {
  const openCbs = new Set<() => void>();
  const closeCbs = new Set<() => void>();
  const reconnectFailedCbs = new Set<() => void>();
  return {
    connect: vi.fn(),
    disconnect: vi.fn(),
    send: vi.fn(),
    onMessage: vi.fn(),
    offMessage: vi.fn(),
    onOpen: vi.fn((cb: () => void) => openCbs.add(cb)),
    offOpen: vi.fn((cb: () => void) => openCbs.delete(cb)),
    onClose: vi.fn((cb: () => void) => closeCbs.add(cb)),
    offClose: vi.fn((cb: () => void) => closeCbs.delete(cb)),
    onReconnectFailed: vi.fn((cb: () => void) => reconnectFailedCbs.add(cb)),
    offReconnectFailed: vi.fn((cb: () => void) => reconnectFailedCbs.delete(cb)),
    emitOpen() {
      openCbs.forEach((cb) => cb());
    },
    emitClose() {
      closeCbs.forEach((cb) => cb());
    },
    emitReconnectFailed() {
      reconnectFailedCbs.forEach((cb) => cb());
    },
  };
});

// Mock antd App.useApp() so WebSocketProvider can call notification.warning
// without needing a real <AntApp> wrapper in tests. The mock returns a stable
// singleton so tests can assert on the same notification.warning instance.
const mockAppApi = vi.hoisted(() => ({
  notification: {
    warning: vi.fn(),
    destroy: vi.fn(),
    close: vi.fn(),
  },
  message: { warning: vi.fn(), success: vi.fn(), error: vi.fn() },
}));

vi.mock('antd', () => ({
  App: {
    useApp: () => mockAppApi,
  },
}));

// Mutable auth state shared with the mocked useAuthStore selector.
const authState = vi.hoisted(() => ({
  isAuthenticated: false,
  accessToken: null as string | null,
}));

vi.mock('@/websocket/client', () => ({ wsClient: mockWsClient }));
vi.mock('@/stores/useAuthStore', () => ({
  useAuthStore: (selector: (s: typeof authState) => unknown) => selector(authState),
}));

/** Consumer that reads the WebSocket context for assertions. */
function ContextConsumer({ onValue }: { onValue: (v: { send: unknown; isConnected: boolean }) => void }) {
  const value = useWebSocketContext();
  onValue(value);
  return null;
}

describe('WebSocketProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.isAuthenticated = false;
    authState.accessToken = null;
  });

  it('renders children', () => {
    const { getByText } = render(createElement(WebSocketProvider, null, createElement('div', null, 'child-content')));
    expect(getByText('child-content')).toBeDefined();
  });

  it('does not connect when not authenticated', () => {
    render(createElement(WebSocketProvider, null, createElement('div')));
    expect(mockWsClient.connect).not.toHaveBeenCalled();
  });

  it('connects with the access token when authenticated', () => {
    authState.isAuthenticated = true;
    authState.accessToken = 'my-token';

    render(createElement(WebSocketProvider, null, createElement('div')));

    expect(mockWsClient.connect).toHaveBeenCalledTimes(1);
    expect(mockWsClient.connect).toHaveBeenCalledWith('my-token');
    expect(mockWsClient.onOpen).toHaveBeenCalledTimes(1);
    expect(mockWsClient.onClose).toHaveBeenCalledTimes(1);
  });

  it('disconnects on unmount when authenticated', () => {
    authState.isAuthenticated = true;
    authState.accessToken = 'my-token';

    const { unmount } = render(createElement(WebSocketProvider, null, createElement('div')));
    unmount();

    expect(mockWsClient.offOpen).toHaveBeenCalledTimes(1);
    expect(mockWsClient.offClose).toHaveBeenCalledTimes(1);
    expect(mockWsClient.disconnect).toHaveBeenCalledTimes(1);
  });

  it('provides send and isConnected via context', () => {
    authState.isAuthenticated = true;
    authState.accessToken = 'tkn';

    let captured: { send: (t: string, d: Record<string, unknown>) => void; isConnected: boolean } | null = null;
    render(
      createElement(
        WebSocketProvider,
        null,
        createElement(ContextConsumer, {
          onValue: (v) =>
            (captured = v as { send: (t: string, d: Record<string, unknown>) => void; isConnected: boolean }),
        }),
      ),
    );

    expect(captured).not.toBeNull();
    expect(captured!.isConnected).toBe(false);

    // The provided send delegates to wsClient.send
    act(() => {
      captured!.send('ping', { a: 1 });
    });
    expect(mockWsClient.send).toHaveBeenCalledWith('ping', { a: 1 });
  });

  it('isConnected becomes true on open event and false on close event', () => {
    authState.isAuthenticated = true;
    authState.accessToken = 'tkn';

    let captured: { isConnected: boolean } | null = null;
    const { rerender } = render(
      createElement(WebSocketProvider, null, createElement(ContextConsumer, { onValue: (v) => (captured = v) })),
    );

    expect(captured!.isConnected).toBe(false);

    act(() => {
      mockWsClient.emitOpen();
    });
    rerender(
      createElement(WebSocketProvider, null, createElement(ContextConsumer, { onValue: (v) => (captured = v) })),
    );
    expect(captured!.isConnected).toBe(true);

    act(() => {
      mockWsClient.emitClose();
    });
    rerender(
      createElement(WebSocketProvider, null, createElement(ContextConsumer, { onValue: (v) => (captured = v) })),
    );
    expect(captured!.isConnected).toBe(false);
  });

  it('subscribes to reconnect-failed events and surfaces a notification (TD-259 #14)', () => {
    authState.isAuthenticated = true;
    authState.accessToken = 'tkn';

    render(createElement(WebSocketProvider, null, createElement('div')));

    // onReconnectFailed must be registered at mount time.
    expect(mockWsClient.onReconnectFailed).toHaveBeenCalledTimes(1);

    act(() => {
      mockWsClient.emitReconnectFailed();
    });
    expect(mockAppApi.notification.warning).toHaveBeenCalledTimes(1);
    expect(mockAppApi.notification.warning).toHaveBeenCalledWith(
      expect.objectContaining({
        key: 'ws-reconnect-failed',
        duration: 0,
        placement: 'top',
      }),
    );

    // A second emit must NOT stack a duplicate (idempotent via reconnectFailedKeyRef).
    act(() => {
      mockWsClient.emitReconnectFailed();
    });
    expect(mockAppApi.notification.warning).toHaveBeenCalledTimes(1);
  });

  it('useWebSocketContext throws when used outside the provider', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(createElement(ContextConsumer, { onValue: () => {} }))).toThrow(/WebSocketProvider/);
    spy.mockRestore();
  });
});
