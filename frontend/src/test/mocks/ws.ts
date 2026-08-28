/**
 * Shared WebSocket mock factories for tests.
 *
 * Two patterns exist in the codebase:
 *  - Pattern A: hooks import the `wsClient` singleton from `@/websocket/client`.
 *    Use `createMockWsClient()` and `vi.mock('@/websocket/client')`.
 *  - Pattern B: hooks call `new WebSocket(url)` directly.
 *    Use `createMockWebSocket()` with `vi.stubGlobal('WebSocket', ...)`.
 */
import { vi } from 'vitest';

type MessageHandler = (data: Record<string, unknown>) => void;

/** Options for createMockWsClient. */
export interface MockWsClientOptions {
  /** Initial connection state reported to onOpen/onClose subscribers. */
  connected?: boolean;
}

/**
 * Build a mock of the wsClient singleton. Tracks onMessage/onOpen/onClose
 * subscribers so tests can simulate incoming frames and connection lifecycle
 * events via the returned `emitMessage` / `emitOpen` / `emitClose` helpers.
 */
export function createMockWsClient() {
  const messageHandlers = new Map<string, Set<MessageHandler>>();
  const openCallbacks = new Set<() => void>();
  const closeCallbacks = new Set<() => void>();
  const reconnectCallbacks = new Set<() => void>();

  const mock = {
    connect: vi.fn(),
    disconnect: vi.fn(),
    send: vi.fn(),
    subscribe: vi.fn(),
    unsubscribe: vi.fn(),
    onMessage: vi.fn((type: string, handler: MessageHandler) => {
      if (!messageHandlers.has(type)) {
        messageHandlers.set(type, new Set());
      }
      messageHandlers.get(type)!.add(handler);
    }),
    offMessage: vi.fn((type: string, handler: MessageHandler) => {
      messageHandlers.get(type)?.delete(handler);
    }),
    onOpen: vi.fn((cb: () => void) => openCallbacks.add(cb)),
    offOpen: vi.fn((cb: () => void) => openCallbacks.delete(cb)),
    onClose: vi.fn((cb: () => void) => closeCallbacks.add(cb)),
    offClose: vi.fn((cb: () => void) => closeCallbacks.delete(cb)),
    onReconnect: vi.fn((cb: () => void) => reconnectCallbacks.add(cb)),
    offReconnect: vi.fn((cb: () => void) => reconnectCallbacks.delete(cb)),
    getCachedExecutionLogs: vi.fn(() => []),
    clearCachedExecutionLogs: vi.fn(),

    /** Test helper: dispatch a message to all handlers registered for `type`
     *  plus any `*` wildcard handlers. Mirrors WsClient.dispatchMessage. */
    emitMessage(type: string, data: Record<string, unknown>) {
      messageHandlers.get(type)?.forEach((h) => h(data));
      messageHandlers.get('*')?.forEach((h) => h(data));
    },
    /** Test helper: fire onOpen callbacks. */
    emitOpen() {
      openCallbacks.forEach((cb) => cb());
    },
    /** Test helper: fire onClose callbacks. */
    emitClose() {
      closeCallbacks.forEach((cb) => cb());
    },
    /** Test helper: fire onReconnect callbacks. */
    emitReconnect() {
      reconnectCallbacks.forEach((cb) => cb());
    },
    /** Test helper: check whether a handler is currently registered. */
    hasHandler(type: string): boolean {
      return (messageHandlers.get(type)?.size ?? 0) > 0;
    },
  };

  return mock;
}

export type MockWsClient = ReturnType<typeof createMockWsClient>;

/** WebSocket readyState constants (mirrors the spec). */
const CONNECTING = 0;
const OPEN = 1;
const CLOSING = 2;
const CLOSED = 3;

/**
 * A minimal WebSocket class mock for Pattern B hooks that call
 * `new WebSocket(url, subprotocols)` directly. Exposes the same surface the
 * hooks read (readyState, url, onopen/onmessage/onclose/onerror, close, send).
 *
 * Tests drive lifecycle transitions via the returned class's static helpers
 * or by calling the instance methods directly.
 */
export function createMockWebSocket() {
  return class MockWebSocket {
    static CONNECTING = CONNECTING;
    static OPEN = OPEN;
    static CLOSING = CLOSING;
    static CLOSED = CLOSED;

    readonly url: string;
    readonly protocols: string | string[];
    readyState: number = CONNECTING;
    onopen: ((ev: Event) => void) | null = null;
    onmessage: ((ev: MessageEvent) => void) | null = null;
    onclose: ((ev: CloseEvent) => void) | null = null;
    onerror: ((ev: Event) => void) | null = null;
    binaryType: BinaryType = 'blob';

    private sentMessages: string[] = [];

    constructor(url: string, protocols?: string | string[]) {
      this.url = url;
      this.protocols = protocols ?? [];
      // Defer the open event so onopen can be assigned by the caller after
      // construction (matching real WebSocket microtask timing).
      setTimeout(() => {
        if (this.readyState === CONNECTING) {
          this.readyState = OPEN;
          this.onopen?.(new Event('open'));
        }
      }, 0);
    }

    send(data: string): void {
      if (this.readyState !== OPEN) {
        throw new DOMException('WebSocket is not in OPEN state', 'InvalidStateError');
      }
      this.sentMessages.push(data);
    }

    close(): void {
      if (this.readyState === CLOSED || this.readyState === CLOSING) return;
      this.readyState = CLOSING;
      this.readyState = CLOSED;
      this.onclose?.(new CloseEvent('close'));
    }

    /** Test helper: simulate an incoming message from the server. */
    emitMessage(data: unknown): void {
      this.onmessage?.({ data: typeof data === 'string' ? data : JSON.stringify(data) } as MessageEvent);
    }

    /** Test helper: simulate an error. */
    emitError(): void {
      this.onerror?.(new Event('error'));
    }

    /** Test helper: messages sent through this instance. */
    getSentMessages(): string[] {
      return this.sentMessages;
    }
  };
}

export type MockWebSocketClass = ReturnType<typeof createMockWebSocket>;
