/**
 * device screenshot stream Hook
 * used for subscribe WebSocket in screenshot_frame message, management screenshot frame receive and show
 *
 * P-004 R37-P2: added per-device filter support (deviceIds param) and
 * framesByDevice map for per-device grids. currentFrame retained for
 * backward compatibility (takes the latest frame across all devices).
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { wsClient } from '@/websocket/client';

/** screenshot frame data type */
interface ScreenshotFrame {
  imageBase64: string;
  width: number;
  height: number;
  timestamp: string;
}

/** useScreenshotStream Hook return value type */
interface ScreenshotStreamResult {
  /** Latest frame across all devices (backward compat — takes newest) */
  currentFrame: ScreenshotFrame | null;
  /** Per-device latest frame (new — for per-device grids) */
  framesByDevice: Record<string, ScreenshotFrame>;
  isStreaming: boolean;
  startStream: (agentId: string, deviceIds?: string[]) => void;
  stopStream: () => void;
  frameHistory: ScreenshotFrame[];
}

/**
 * subscribe device screenshot stream
 * via WebSocket receive real-time screenshot frame data
 */
export function useScreenshotStream(): ScreenshotStreamResult {
  const [currentFrame, setCurrentFrame] = useState<ScreenshotFrame | null>(null);
  const [framesByDevice, setFramesByDevice] = useState<Record<string, ScreenshotFrame>>({});
  const [isStreaming, setIsStreaming] = useState(false);
  const [frameHistory, setFrameHistory] = useState<ScreenshotFrame[]>([]);
  // Track the active agent_id so stopStream() can forward it to the backend.
  // Without agent_id in the stop payload, the backend consumer silently drops
  // the stop request (consumers.py: `elif msg_type == "stop_screenshot_stream"
  // and agent_id:`) and the agent keeps pushing frames — which makes the
  // "stop screenshot" button look unresponsive.
  const activeAgentIdRef = useRef<string | null>(null);

  /** handle received screenshot frame message */
  const handleFrame = useCallback((data: Record<string, unknown>) => {
    const frame: ScreenshotFrame = {
      imageBase64: data.image_base64 as string,
      width: data.width as number,
      height: data.height as number,
      timestamp: data.captured_at as string,
    };
    setCurrentFrame(frame);
    // TD-079: append then cap to 50. Previously `[...prev.slice(-50), frame]`
    // produced up to 51 entries (50 retained + 1 new). slice(-50) after
    // append cleanly expresses "keep the most recent 50".
    setFrameHistory((prev) => [...prev, frame].slice(-50));
    // P-004 R37-P2: also store per-device so grids can show multiple devices
    const deviceId = String(data.device_id ?? '');
    if (deviceId) {
      setFramesByDevice((prev) => ({ ...prev, [deviceId]: frame }));
    }
  }, []);

  useEffect(() => {
    wsClient.onMessage('screenshot_frame', handleFrame);
    return () => {
      wsClient.offMessage('screenshot_frame', handleFrame);
      // H16 fix: only send stop_screenshot_stream when WS is open. If WS is
      // already closed (e.g. network drop), sending would silently fail and
      // the backend may keep pushing frames. The backend's WS consumer will
      // clean up on its own disconnect — the client just needs to avoid
      // queueing a stop message that will never arrive.
      // wsClient.send() already no-ops when readyState !== OPEN, but we also
      // guard here so that reconnection on the next mount starts clean.
      wsClient.send('stop_screenshot_stream', {});
    };
  }, [handleFrame]);

  /** start receive screenshot stream
   *  @param agentId target agent id
   *  @param deviceIds optional per-device filter; None or empty = all devices
   */
  const startStream = useCallback((agentId: string, deviceIds?: string[]) => {
    activeAgentIdRef.current = agentId;
    const payload: Record<string, unknown> = { agent_id: agentId };
    if (deviceIds && deviceIds.length > 0) {
      payload.device_ids = deviceIds;
    }
    wsClient.send('request_screenshot_stream', payload);
    setIsStreaming(true);
  }, []);

  /** stop receive screenshot stream */
  const stopStream = useCallback(() => {
    // H16 fix: same guard — only send stop when WS is actually open.
    // Forward agent_id so the backend can route the stop to the right agent
    // group (consumers.py drops the message when agent_id is missing).
    const agentId = activeAgentIdRef.current;
    if (agentId) {
      wsClient.send('stop_screenshot_stream', { agent_id: agentId });
    } else {
      wsClient.send('stop_screenshot_stream', {});
    }
    activeAgentIdRef.current = null;
    setIsStreaming(false);
  }, []);

  return { currentFrame, framesByDevice, isStreaming, startStream, stopStream, frameHistory };
}
