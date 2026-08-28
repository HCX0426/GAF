/**
 * User-scoped notification WebSocket hook.
 *
 * Maintains a dedicated connection to `/ws/notifications/` and invokes the
 * provided callback for every notification payload received. The connection
 * automatically reconnects with exponential backoff and includes the current
 * JWT access token via the Sec-WebSocket-Protocol subprotocol.
 */
import { useEffect, useRef } from 'react';

import { useAuthStore } from '@/stores/useAuthStore';
import { useStableCallback } from './useStableCallback';

export interface NotificationPayload {
  level?: string;
  title?: string;
  message?: string;
  [key: string]: unknown;
}

export function useNotificationWebSocket(
  enabled: boolean,
  onNotification: (payload: NotificationPayload) => void,
): void {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const onNotificationRef = useStableCallback(onNotification);
  const disconnectPendingRef = useRef(false);
  const accessToken = useAuthStore((s) => s.accessToken);

  useEffect(() => {
    if (!enabled || !accessToken) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      return;
    }

    const maxReconnectAttempts = 10;
    const baseReconnectInterval = 3000;
    const maxReconnectInterval = 60000;

    const connect = () => {
      const token = accessToken;
      if (!token) return;

      // Avoid redundant connections while already connected or connecting with
      // the same token. This reduces churn under React StrictMode.
      if (
        wsRef.current &&
        wsRef.current.url.includes('/ws/notifications/') &&
        (wsRef.current.readyState === WebSocket.CONNECTING || wsRef.current.readyState === WebSocket.OPEN)
      ) {
        return;
      }

      disconnectPendingRef.current = false;
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const url = `${protocol}//${window.location.host}/ws/notifications/`;
      const subprotocols = [`access.${token}`];

      const ws = new WebSocket(url, subprotocols);
      wsRef.current = ws;

      ws.onopen = () => {
        // If the component unmounted while the socket was still connecting,
        // close it now to keep the cleanup contract without triggering the
        // spurious "closed before the connection is established" warning.
        if (disconnectPendingRef.current) {
          disconnectPendingRef.current = false;
          ws.close();
          return;
        }
        reconnectAttemptsRef.current = 0;
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const message = JSON.parse(event.data as string) as {
            type: string;
            payload?: NotificationPayload;
          };
          if (message.type === 'notification') {
            // spec-29a #31: legacy `data` fallback removed — backend
            // broadcast_notification + NotificationConsumer both use `payload`.
            const payload = message.payload ?? ({} as NotificationPayload);
            onNotificationRef.current(payload);
          }
        } catch {
          // ignore malformed message
        }
      };

      ws.onclose = () => {
        wsRef.current = null;
        if (reconnectAttemptsRef.current >= maxReconnectAttempts) {
          return;
        }
        const delay = Math.min(baseReconnectInterval * Math.pow(2, reconnectAttemptsRef.current), maxReconnectInterval);
        reconnectAttemptsRef.current += 1;
        reconnectTimerRef.current = setTimeout(connect, delay);
      };

      ws.onerror = () => {
        // Error handling is delegated to onclose for reconnection.
      };
    };

    connect();

    return () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (wsRef.current) {
        // Defer closing a still-connecting socket until onopen fires. This
        // avoids the console warning emitted when a CONNECTING socket is closed.
        if (wsRef.current.readyState === WebSocket.CONNECTING) {
          disconnectPendingRef.current = true;
        } else {
          wsRef.current.close();
        }
        wsRef.current = null;
      }
    };
  }, [enabled, accessToken]);
}

export default useNotificationWebSocket;
