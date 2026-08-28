/**
 * WebSocket message subscribe Hook
 * wraps wsClient message subscribe, auto handle React lifecycle cycle in register and cleanup
 */
import { useEffect } from 'react';
import { wsClient } from '@/websocket/client';
import { useStableCallback } from './useStableCallback';

/** message handle callback type */
type MessageHandler = (data: Record<string, unknown>) => void;

/**
 * subscribe WebSocket message type
 * component mount when register handle device, unmount when auto remove
 *
 * H15 fix: handler is stored in a ref and the subscription effect only depends
 * on `type`. Without this, callers that pass an inline handler (not wrapped
 * in useCallback) would re-subscribe on every parent re-render, causing
 * offMessage + onMessage churn and potential missed messages.
 *
 * TD-052: ref pattern extracted to useStableCallback shared utility.
 *
 * @param type message type,'*' represents subscribe has message
 * @param handler message handle callback
 */
export function useWebSocket(type: string, handler: MessageHandler): void {
  const handlerRef = useStableCallback(handler);

  useEffect(() => {
    const stableHandler: MessageHandler = (data) => handlerRef.current(data);
    wsClient.onMessage(type, stableHandler);
    return () => {
      wsClient.offMessage(type, stableHandler);
    };
  }, [type]);
}

/**
 * send WebSocket message
 * @returns send function
 */
export function useWebSocketSend(): (type: string, data: Record<string, unknown>) => void {
  return (type: string, data: Record<string, unknown>) => {
    wsClient.send(type, data);
  };
}
