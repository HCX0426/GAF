/**
 * SSE (Server-Sent Events) streaming data Hook
 * used for receive AI streaming response, real-time log etc. push data
 *
 * H14 fix: browser-native EventSource does not support custom Authorization
 * headers, so any backend SSE endpoint that requires a Bearer token would
 * always 401. Replaced with fetch() + ReadableStream manual SSE parsing so
 * we can inject the access token via the standard Authorization header.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { buildAuthHeaders } from '@/utils/tokenStore';

/** SSE event data type */
interface SSEEvent {
  event: string;
  data: string;
  id?: string;
}

/** useSSEStream Hook param */
interface UseSSEStreamOptions {
  url: string;
  onMessage?: (event: SSEEvent) => void;
  onError?: (error: Error) => void;
  onComplete?: () => void;
  autoStart?: boolean;
  /** Custom error message when SSE connection fails (default: 'SSE 连接错误') */
  errorMessage?: string;
}

/** useSSEStream Hook return value type */
interface UseSSEStreamResult {
  messages: SSEEvent[];
  isConnected: boolean;
  error: string | null;
  start: () => void;
  stop: () => void;
  clearMessages: () => void;
}

/**
 * Parse a raw SSE block (separated by blank line) into an SSEEvent.
 * Returns null for comment-only blocks (lines starting with ':').
 */
function parseSSEBlock(block: string): SSEEvent | null {
  const lines = block.split(/\r?\n/);
  let event = 'message';
  const dataParts: string[] = [];
  let id: string | undefined;

  for (const line of lines) {
    if (!line || line.startsWith(':')) continue;
    const colonIdx = line.indexOf(':');
    const field = colonIdx === -1 ? line : line.slice(0, colonIdx);
    // Per spec, a leading space after the colon is stripped.
    let value = colonIdx === -1 ? '' : line.slice(colonIdx + 1);
    if (value.startsWith(' ')) value = value.slice(1);

    if (field === 'event') {
      event = value;
    } else if (field === 'data') {
      dataParts.push(value);
    } else if (field === 'id') {
      id = value;
    }
    // 'retry' field is ignored — we don't auto-reconnect SSE (caller controls lifecycle)
  }

  if (dataParts.length === 0 && event === 'message') {
    return null;
  }
  return { event, data: dataParts.join('\n'), id };
}

/**
 * management SSE connection status and data stream
 * supports auto connection and manual control
 */
export function useSSEStream({
  url,
  onMessage,
  onError,
  onComplete,
  autoStart = true,
  errorMessage = 'SSE 连接错误',
}: UseSSEStreamOptions): UseSSEStreamResult {
  const [messages, setMessages] = useState<SSEEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const readerRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null);

  /** Stop the SSE stream and release all resources. */
  const stop = useCallback(() => {
    if (readerRef.current) {
      // reader.cancel() is async but we don't need to await — abort below
      // will signal the fetch to release the underlying connection.
      // spec35 #12: log the failure (usually "already closed") so stream
      // teardown issues are debuggable instead of fully silent.
      readerRef.current.cancel().catch((err) => {
        console.warn('[useSSEStream] reader.cancel failed:', err);
      });
      readerRef.current = null;
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsConnected(false);
  }, []);

  /** Start the SSE stream. */
  const start = useCallback(() => {
    stop();

    const controller = new AbortController();
    abortControllerRef.current = controller;

    // H14 fix: inject Bearer token. EventSource cannot do this; fetch can.
    // M22: use shared buildAuthHeaders utility.
    const headers = buildAuthHeaders({
      Accept: 'text/event-stream',
      'Cache-Control': 'no-cache',
    });

    (async () => {
      try {
        const res = await fetch(url, {
          method: 'GET',
          headers,
          signal: controller.signal,
        });
        if (!res.ok) {
          throw new Error(`SSE connection failed: ${res.status}`);
        }
        if (!res.body) {
          throw new Error('SSE response has no body');
        }
        setIsConnected(true);
        setError(null);

        const reader = res.body.getReader();
        readerRef.current = reader;
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        // Read loop: accumulate chunks, split on blank line to get SSE blocks.
        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // Split on \n\n (or \r\n\r\n) — each block is one SSE event.
          let sepIdx: number;
          // eslint-disable-next-line no-cond-assign
          while ((sepIdx = buffer.search(/\r?\n\r?\n/)) !== -1) {
            const block = buffer.slice(0, sepIdx);
            // Move buffer past the separator (length depends on \r\n vs \n).
            const match = buffer.match(/\r?\n\r?\n/);
            buffer = match ? buffer.slice(sepIdx + match[0].length) : buffer.slice(sepIdx + 2);

            const parsed = parseSSEBlock(block);
            if (!parsed) continue;

            setMessages((prev) => [...prev, parsed]);
            onMessage?.(parsed);

            // Backend signals stream end via a `complete` event.
            if (parsed.event === 'complete') {
              onComplete?.();
              stop();
              return;
            }
          }
        }

        // Stream ended naturally (server closed connection).
        setIsConnected(false);
      } catch (err) {
        if ((err as Error).name === 'AbortError') {
          // Expected when stop() is called — not a real error.
          return;
        }
        const msg = (err as Error).message || errorMessage;
        setError(msg);
        onError?.(err as Error);
        setIsConnected(false);
      } finally {
        readerRef.current = null;
        abortControllerRef.current = null;
      }
    })();
  }, [url, stop, onMessage, onError, onComplete]);

  useEffect(() => {
    if (autoStart && url) {
      start();
    }
    return () => stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoStart, url]);

  /** clear message history */
  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  return { messages, isConnected, error, start, stop, clearMessages };
}
