/**
 * useLogStream — WebSocket hook for real-time log entry push (C.5).
 *
 * Connects to the `/ws/logs/` channel (LogStreamConsumer) using JWT
 * subprotocol auth, dispatches incoming `log.entry` payloads to a
 * caller-provided callback. Automatically manages connection lifecycle
 * on mount/unmount and token changes.
 */
import { useEffect, useRef, useState } from 'react';
import { useAuthStore } from '@/stores/useAuthStore';
import { useStableCallback } from './useStableCallback';

/** Shape of a log.entry payload broadcast by DatabaseLogHandler via LOGS_GROUP. */
export interface LogStreamEntry {
  timestamp: string;
  level: string;
  source: string;
  message: string;
  traceback?: string;
  task_id?: number | null;
  agent_id?: number | null;
  device_id?: number | null;
}

/** Connect to /ws/logs/ and invoke onEntry for each pushed log entry. */
export function useLogStream(onEntry: (entry: LogStreamEntry) => void): {
  isConnected: boolean;
} {
  const accessToken = useAuthStore((s) => s.accessToken);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const wsRef = useRef<WebSocket | null>(null);
  const onEntryRef = useStableCallback(onEntry);
  // TD-080: connection state must be reactive so consumers can render
  // connection status. Previously this was a ref, which never triggered
  // re-renders — isConnected was effectively always the initial false.
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    if (!isAuthenticated || !accessToken) {
      return undefined;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws/logs/`;
    // C8: pass token via subprotocol to avoid leaking in URL/history/referrer.
    const subprotocols = [`access.${accessToken}`];
    const ws = new WebSocket(url, subprotocols);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
    };
    ws.onclose = () => {
      setIsConnected(false);
    };
    ws.onerror = () => {
      // Errors are surfaced via onclose; nothing to do here.
    };
    ws.onmessage = (event: MessageEvent) => {
      try {
        const message = JSON.parse(event.data as string) as {
          type: string;
          payload?: LogStreamEntry;
        };
        if (message.type === 'log.entry' && message.payload) {
          onEntryRef.current(message.payload);
        }
      } catch {
        // Ignore non-JSON frames.
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
      setIsConnected(false);
    };
  }, [isAuthenticated, accessToken]);

  return { isConnected };
}
