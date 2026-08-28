/**
 * WebSocket global connection Provider
 * based on auth status auto management WS connection lifecycle cycle, provides global send/subscribe capability
 */
import { createContext, useContext, useEffect, useState, useCallback, useRef, type ReactNode } from 'react';
import { App } from 'antd';
import { useAuthStore } from '@/stores/useAuthStore';
import { wsClient } from '@/websocket/client';

/** WebSocket Context value type */
interface WebSocketContextValue {
  send: (type: string, data: Record<string, unknown>) => void;
  isConnected: boolean;
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

/** WebSocket global connection management Provider */
export function WebSocketProvider({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const accessToken = useAuthStore((s) => s.accessToken);
  const [isConnected, setIsConnected] = useState(false);
  const { notification } = App.useApp();
  // Track whether a reconnect-failed notification is currently shown so we
  // don't stack duplicates on every fireReconnectFailedCallbacks invocation.
  const reconnectFailedKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (isAuthenticated && accessToken) {
      wsClient.connect(accessToken);

      const onOpen = () => {
        setIsConnected(true);
        // If a previous reconnect-failed notification is still on screen,
        // dismiss it now that the connection is healthy again.
        if (reconnectFailedKeyRef.current) {
          notification.destroy(reconnectFailedKeyRef.current);
          reconnectFailedKeyRef.current = null;
        }
      };
      const onClose = () => setIsConnected(false);
      // H18 / TD-259 #14: surface a persistent warning when the WS client has
      // exhausted all reconnect attempts. The user needs to know that live
      // updates (logs, screenshots, task progress) are no longer flowing.
      const onReconnectFailed = () => {
        if (reconnectFailedKeyRef.current) return; // already shown
        const key = 'ws-reconnect-failed';
        reconnectFailedKeyRef.current = key;
        notification.warning({
          key,
          title: '实时连接已断开',
          description:
            'WebSocket 重连已失败 10 次，实时数据推送（日志、截图、任务进度）可能不再更新。请检查网络或刷新页面。',
          duration: 0, // persistent until dismissed or connection restored
          placement: 'top',
        });
      };

      wsClient.onOpen(onOpen);
      wsClient.onClose(onClose);
      wsClient.onReconnectFailed(onReconnectFailed);

      return () => {
        wsClient.offOpen(onOpen);
        wsClient.offClose(onClose);
        wsClient.offReconnectFailed(onReconnectFailed);
        wsClient.disconnect();
      };
    }
    return undefined;
  }, [isAuthenticated, accessToken, notification]);

  /** send WS message */
  const send = useCallback((type: string, data: Record<string, unknown>) => {
    wsClient.send(type, data);
  }, []);

  return <WebSocketContext.Provider value={{ send, isConnected }}>{children}</WebSocketContext.Provider>;
}

/** get WebSocket Context */
export function useWebSocketContext(): WebSocketContextValue {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocketContext 必须在 WebSocketProvider 内部使用');
  }
  return context;
}
