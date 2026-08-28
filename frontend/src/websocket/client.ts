/**
 * WebSocket client management
 * supports connection, disconnect, send message, message subscribe, auto reconnect, reconnect callback
 */

/** message handle callback function type */
type MessageHandler = (data: Record<string, unknown>) => void;

/** reconnect callback function type */
type ReconnectHandler = () => void;

/** cached execution log entry (kept in the singleton so panels mounted after
 *  the event still show recent history) */
interface CachedExecutionLog {
  timestamp: string;
  level: string;
  message: string;
  execution_id?: string;
}

/** maximum log entries retained per execution in the client-side cache */
const MAX_CACHED_LOGS_PER_EXECUTION = 200;

import { WS_PATH, WS_HEARTBEAT_INTERVAL, WS_PONG_TIMEOUT } from '@/config/app';

/** WebSocket client class */
class WsClient {
  private ws: WebSocket | null = null;
  private url: string = '';
  private pendingToken: string = '';
  private handlers: Map<string, Set<MessageHandler>> = new Map();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 10;
  private baseReconnectInterval: number = 3000;
  private maxReconnectInterval: number = 60000;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  /** pong timeout timer started after each ping; cleared when a pong arrives */
  private pongTimeoutId: ReturnType<typeof setTimeout> | null = null;
  /** consecutive pongs missed (no pong received before WS_PONG_TIMEOUT) */
  private missedPongs = 0;
  private onReconnectCallbacks: Set<ReconnectHandler> = new Set();
  private onOpenCallbacks: Set<() => void> = new Set();
  private onCloseCallbacks: Set<() => void> = new Set();
  /** callbacks fired once after reconnect attempts are exhausted (H18 final-failure signal) */
  private onReconnectFailedCallbacks: Set<() => void> = new Set();
  private wasConnected: boolean = false;
  /** client-side cache of execution_log payloads keyed by execution_id */
  private executionLogCache: Map<string, CachedExecutionLog[]> = new Map();
  /** True when disconnect() was called while the socket was still CONNECTING.
   *  The connection will be closed in onopen instead, avoiding the spurious
   *  "WebSocket is closed before the connection is established" console warning
   *  caused by React StrictMode's mount/unmount/remount cycle. */
  private disconnectPending = false;

  /** establish WebSocket connection */
  connect(token: string): void {
    // Guard against redundant connect calls with the same token while already
    // connected or connecting. This prevents spurious "WebSocket is closed
    // before the connection is established" warnings when React StrictMode or
    // multiple components trigger connect concurrently.
    if (
      this.pendingToken === token &&
      this.ws &&
      (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)
    ) {
      return;
    }
    this.disconnectPending = false;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // C8 fix: do NOT put JWT in URL query string — it leaks via browser history,
    // access logs, referrer header. Pass token via Sec-WebSocket-Protocol subprotocol.
    this.url = `${protocol}//${window.location.host}${WS_PATH}`;
    this.pendingToken = token;
    this.doConnect();
  }

  /** execute connection operation */
  private doConnect(): void {
    if (this.ws) {
      this.ws.close();
    }

    // C8 fix: send token via subprotocol `access.<jwt>` instead of URL query string.
    // Server (FrontendConsumer) reads scope['subprotocols'] and echoes the chosen
    // subprotocol back via accept(subprotocol=...).
    const subprotocols = this.pendingToken ? [`access.${this.pendingToken}`] : [];
    this.ws = new WebSocket(this.url, subprotocols);

    this.ws.onopen = () => {
      // React StrictMode may unmount a component while its socket is still
      // connecting. In that case we close the connection immediately after it
      // opens so the remounted component can establish the canonical one.
      if (this.disconnectPending) {
        this.disconnectPending = false;
        this.ws?.close();
        return;
      }
      const isReconnect = this.wasConnected && this.reconnectAttempts > 0;
      this.reconnectAttempts = 0;
      this.wasConnected = true;
      this.startHeartbeat();
      // H17 fix: always fire open callbacks so UI layer knows connection is live.
      this.fireOpenCallbacks();
      if (isReconnect) {
        this.fireReconnectCallbacks();
      }
    };

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const message = JSON.parse(event.data as string) as {
          type: string;
          payload?: Record<string, unknown>;
        };
        // L10 fix: a pong reply clears the pending pong timeout and resets the
        // missed-pong counter so the client can detect half-open TCP connections.
        if (message.type === 'pong') {
          if (this.pongTimeoutId) {
            clearTimeout(this.pongTimeoutId);
            this.pongTimeoutId = null;
          }
          this.missedPongs = 0;
        }
        // spec-29a #31: legacy `data` fallback removed — all backend senders
        // (agents/signals.py, agents/views.py, accounts/services.py,
        // protocol/consumers.py) now wrap events in canonical `payload`.
        const payload = message.payload ?? {};
        this.dispatchMessage(message.type, payload);
      } catch (err) {
        // L10 fix: surface malformed JSON so backend protocol drift is debuggable
        // instead of failing silently.
        console.warn('[WS] message JSON parse failed:', event.data, err);
        return;
      }
    };

    this.ws.onclose = () => {
      this.stopHeartbeat();
      // H17 fix: notify UI layer before attempting reconnect.
      this.fireCloseCallbacks();
      this.tryReconnect();
    };

    this.ws.onerror = () => {
      // error handle in onclose in trigger reconnect
    };
  }

  /** disconnect WebSocket connection */
  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.stopHeartbeat();
    this.reconnectAttempts = this.maxReconnectAttempts;
    this.wasConnected = false;
    if (this.ws) {
      // If the socket is still connecting, defer the close until onopen fires.
      // Closing a CONNECTING socket triggers a console warning; deferring avoids
      // the noise while still ensuring the socket does not stay open.
      if (this.ws.readyState === WebSocket.CONNECTING) {
        this.disconnectPending = true;
      } else {
        this.ws.close();
      }
      this.ws = null;
    }
  }

  /** send message to service end */
  send(type: string, data: Record<string, unknown>): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      // H25 fix: use canonical `payload` field instead of legacy `data`.
      this.ws.send(JSON.stringify({ type, payload: data, timestamp: new Date().toISOString() }));
    }
  }

  /**
   * send subscribe message (A011 fix: comply spec §9.2 client → service end subscribe protocol )
   * @param channel channel name ( like 'screenshot', 'logs')
   * @param params subscribe param ( like { device_id: 'xxx' })
   */
  subscribe(channel: string, params: Record<string, unknown> = {}): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: 'subscribe', channel, params }));
    }
  }

  /**
   * send cancel subscribe message (A011 fix: comply spec §9.2 client → service end subscribe protocol )
   * @param channel channel name
   */
  unsubscribe(channel: string): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: 'unsubscribe', channel }));
    }
  }

  /** register message type handle device */
  onMessage(type: string, handler: MessageHandler): void {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, new Set());
    }
    this.handlers.get(type)!.add(handler);
  }

  /** remove message type handle device */
  offMessage(type: string, handler: MessageHandler): void {
    const handlers = this.handlers.get(type);
    if (handlers) {
      handlers.delete(handler);
    }
  }

  /** register reconnect success callback */
  onReconnect(callback: ReconnectHandler): void {
    this.onReconnectCallbacks.add(callback);
  }

  /** remove reconnect success callback */
  offReconnect(callback: ReconnectHandler): void {
    this.onReconnectCallbacks.delete(callback);
  }

  /** register connection open callback */
  onOpen(callback: () => void): void {
    this.onOpenCallbacks.add(callback);
  }

  /** remove connection open callback */
  offOpen(callback: () => void): void {
    this.onOpenCallbacks.delete(callback);
  }

  /** register connection close callback */
  onClose(callback: () => void): void {
    this.onCloseCallbacks.add(callback);
  }

  /** remove connection close callback */
  offClose(callback: () => void): void {
    this.onCloseCallbacks.delete(callback);
  }

  /** register reconnect-failed callback (fired once after max attempts exhausted) */
  onReconnectFailed(callback: () => void): void {
    this.onReconnectFailedCallbacks.add(callback);
  }

  /** remove reconnect-failed callback */
  offReconnectFailed(callback: () => void): void {
    this.onReconnectFailedCallbacks.delete(callback);
  }

  /** trigger has reconnect callback */
  private fireReconnectCallbacks(): void {
    this.onReconnectCallbacks.forEach((cb) => {
      try {
        cb();
      } catch {
        // Individual reconnect callback failed — skip to next
      }
    });
  }

  /** trigger has connection open callback */
  private fireOpenCallbacks(): void {
    this.onOpenCallbacks.forEach((cb) => {
      try {
        cb();
      } catch {
        // Individual open callback failed — skip to next
      }
    });
  }

  /** trigger has connection close callback */
  private fireCloseCallbacks(): void {
    this.onCloseCallbacks.forEach((cb) => {
      try {
        cb();
      } catch {
        // Individual close callback failed — skip to next
      }
    });
  }

  /** trigger reconnect-failed callbacks (H18 final-failure signal to UI layer) */
  private fireReconnectFailedCallbacks(): void {
    this.onReconnectFailedCallbacks.forEach((cb) => {
      try {
        cb();
      } catch {
        // Individual reconnect-failed callback failed — skip to next
      }
    });
  }

  /** dispatch message to to corresponding handle device */
  private dispatchMessage(type: string, data: Record<string, unknown>): void {
    if (type === 'execution_log') {
      this._cacheExecutionLog(data);
    }
    const handlers = this.handlers.get(type);
    if (handlers) {
      handlers.forEach((handler) => handler(data));
    }
    const allHandlers = this.handlers.get('*');
    if (allHandlers) {
      allHandlers.forEach((handler) => handler(data));
    }
  }

  /** cache execution_log payload for panels that mount after the event */
  private _cacheExecutionLog(data: Record<string, unknown>): void {
    const executionId = data.execution_id;
    if (typeof executionId !== 'string' && typeof executionId !== 'number') {
      return;
    }
    const key = String(executionId);
    const entry: CachedExecutionLog = {
      execution_id: key,
      timestamp: (data.timestamp as string) || new Date().toISOString(),
      level: (data.level as string) || 'INFO',
      message: (data.message as string) || JSON.stringify(data),
    };
    const existing = this.executionLogCache.get(key) || [];
    const next = [...existing, entry].slice(-MAX_CACHED_LOGS_PER_EXECUTION);
    this.executionLogCache.set(key, next);
  }

  /** retrieve cached execution logs for a given execution id */
  public getCachedExecutionLogs(executionId: string | number): CachedExecutionLog[] {
    return this.executionLogCache.get(String(executionId)) || [];
  }

  /** clear cached logs for an execution (useful when leaving the monitor view) */
  public clearCachedExecutionLogs(executionId: string | number): void {
    this.executionLogCache.delete(String(executionId));
  }

  /** attempt auto reconnect (H18 fix: exponential backoff + final-failure notification) */
  private tryReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      // H18 fix: notify UI layer that reconnection has given up.
      // fireCloseCallbacks was already called in onclose; here we re-fire to
      // signal the final state after exhausting all retry attempts, plus fire
      // the dedicated reconnect-failed callbacks so the UI can surface a
      // persistent notification to the user (TD-259 #14).
      this.fireCloseCallbacks();
      this.fireReconnectFailedCallbacks();
      return;
    }
    // Exponential backoff: 3s → 6s → 12s → 24s → 48s → 60s (capped).
    const delay = Math.min(this.baseReconnectInterval * Math.pow(2, this.reconnectAttempts), this.maxReconnectInterval);
    this.reconnectAttempts++;
    this.reconnectTimer = setTimeout(() => {
      this.doConnect();
    }, delay);
  }

  /** start heartbeat detect */
  private startHeartbeat(): void {
    this.heartbeatTimer = setInterval(() => {
      this.send('ping', {});
      // L10 fix: arm a pong timeout after each ping. If the server does not
      // reply with a pong within WS_PONG_TIMEOUT, count it as a missed pong.
      // Two consecutive missed pongs mean the connection is likely half-open
      // (TCP still alive but the peer is not processing frames), so we force
      // a disconnect and let the reconnect logic re-establish the socket.
      if (this.pongTimeoutId) {
        clearTimeout(this.pongTimeoutId);
      }
      this.pongTimeoutId = setTimeout(this.handlePongTimeout, WS_PONG_TIMEOUT);
    }, WS_HEARTBEAT_INTERVAL);
  }

  /** pong timeout handler: bump missed-pong counter, force reconnect if ≥ 2 */
  private handlePongTimeout = (): void => {
    this.pongTimeoutId = null;
    this.missedPongs++;
    if (this.missedPongs >= 2) {
      this.missedPongs = 0;
      // Force-close the socket; onclose will fire stopHeartbeat + tryReconnect.
      if (this.ws) {
        this.ws.close();
      }
    }
  };

  /** stop heartbeat detect */
  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    if (this.pongTimeoutId) {
      clearTimeout(this.pongTimeoutId);
      this.pongTimeoutId = null;
    }
    this.missedPongs = 0;
  }
}

/** WebSocket client singleton */
export const wsClient = new WsClient();
