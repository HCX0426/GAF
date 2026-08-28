/**
 * Exception sound alert hook.
 *
 * Manages audio alert playback, volume control, mute state and optional
 * auto-unmute countdown. Sounds are loaded once via the Web Audio API and
 * played through a gain node so volume/mute changes take effect immediately.
 *
 * Integration: use this hook in a top-level component (e.g. AppLayout) and
 * wire it to global error/notification events.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

export type AlertLevel = 'warning' | 'critical';

export interface UseAudioAlertReturn {
  isMuted: boolean;
  volume: number;
  playAlert: (level: AlertLevel) => void;
  mute: (durationMinutes?: number) => void;
  unmute: () => void;
  setVolume: (v: number) => void;
}

/** localStorage keys for persisting user preferences */
const STORAGE_KEY_MUTED = 'gaf_audio_muted';
const STORAGE_KEY_VOLUME = 'gaf_audio_volume';
const STORAGE_KEY_UNMUTE_AT = 'gaf_audio_unmute_at';

/** Minimum interval (ms) between two alerts of the same level to avoid spam. */
const ALERT_THROTTLE_MS = 2000;

/** Sound asset paths relative to the public folder. */
const SOUND_PATHS: Record<AlertLevel, string> = {
  warning: '/sounds/warning.wav',
  critical: '/sounds/critical.wav',
};

function readMuted(): boolean {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_MUTED);
    // Default: muted (sound off) — user must explicitly unmute to hear alerts.
    // 之前默认 false (声音开), 用户反馈"agent启动的声音给我默认关闭", 改为默认 true.
    if (raw === null) return true;
    if (raw !== 'true') return false;
    // Honor a scheduled auto-unmute if the user previously muted with a duration.
    const unmuteAt = Number(localStorage.getItem(STORAGE_KEY_UNMUTE_AT));
    if (unmuteAt && Date.now() >= unmuteAt) {
      // Scheduled unmute has passed; clean up persisted state.
      localStorage.removeItem(STORAGE_KEY_UNMUTE_AT);
      localStorage.setItem(STORAGE_KEY_MUTED, 'false');
      return false;
    }
    return true;
  } catch {
    return true;
  }
}

function writeMuted(value: boolean): void {
  try {
    localStorage.setItem(STORAGE_KEY_MUTED, value ? 'true' : 'false');
  } catch {
    // silent failure
  }
}

function readVolume(): number {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_VOLUME);
    const parsed = raw === null ? 0.5 : Number(raw);
    return Number.isFinite(parsed) ? Math.max(0, Math.min(1, parsed)) : 0.5;
  } catch {
    return 0.5;
  }
}

function writeVolume(value: number): void {
  try {
    localStorage.setItem(STORAGE_KEY_VOLUME, String(Math.max(0, Math.min(1, value))));
  } catch {
    // silent failure
  }
}

function writeUnmuteAt(timestamp: number | null): void {
  try {
    if (timestamp === null) {
      localStorage.removeItem(STORAGE_KEY_UNMUTE_AT);
    } else {
      localStorage.setItem(STORAGE_KEY_UNMUTE_AT, String(timestamp));
    }
  } catch {
    // silent failure
  }
}

/**
 * Load and decode an audio file into an AudioBuffer.
 */
async function loadAudioBuffer(context: AudioContext, url: string): Promise<AudioBuffer | null> {
  try {
    const response = await fetch(url);
    if (!response.ok) return null;
    const arrayBuffer = await response.arrayBuffer();
    return await context.decodeAudioData(arrayBuffer);
  } catch {
    return null;
  }
}

export function useAudioAlert(): UseAudioAlertReturn {
  const [isMuted, setIsMuted] = useState(() => readMuted());
  const [volume, setVolumeState] = useState(() => readVolume());
  const audioContextRef = useRef<AudioContext | null>(null);
  const gainNodeRef = useRef<GainNode | null>(null);
  const buffersRef = useRef<Partial<Record<AlertLevel, AudioBuffer>>>({});
  const lastPlayRef = useRef<Partial<Record<AlertLevel, number>>>({});
  const unmuteTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** Ensure AudioContext and GainNode are lazily initialized. */
  const ensureContext = useCallback((): { context: AudioContext; gain: GainNode } | null => {
    if (typeof window === 'undefined') return null;
    if (!audioContextRef.current) {
      const Ctx =
        (window as typeof window & { AudioContext?: typeof AudioContext; webkitAudioContext?: typeof AudioContext })
          .AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!Ctx) return null;
      const context = new Ctx();
      const gain = context.createGain();
      gain.connect(context.destination);
      audioContextRef.current = context;
      gainNodeRef.current = gain;
    }
    return { context: audioContextRef.current, gain: gainNodeRef.current! };
  }, []);

  /** Sync gain node value with volume/mute state. */
  useEffect(() => {
    const gain = gainNodeRef.current;
    if (!gain) return;
    gain.gain.setTargetAtTime(isMuted ? 0 : volume, gain.context.currentTime, 0.01);
  }, [isMuted, volume]);

  /** Clear any pending auto-unmute timer on unmount. */
  useEffect(() => {
    return () => {
      if (unmuteTimerRef.current) {
        clearTimeout(unmuteTimerRef.current);
        unmuteTimerRef.current = null;
      }
    };
  }, []);

  const playAlert = useCallback(
    async (level: AlertLevel) => {
      if (isMuted) return;

      const now = Date.now();
      const last = lastPlayRef.current[level] || 0;
      if (now - last < ALERT_THROTTLE_MS) return;
      lastPlayRef.current[level] = now;

      const ctx = ensureContext();
      if (!ctx) return;
      const { context, gain } = ctx;

      // Lazy-load the requested buffer on first use.
      if (!buffersRef.current[level]) {
        const buffer = await loadAudioBuffer(context, SOUND_PATHS[level]);
        if (!buffer) return;
        buffersRef.current[level] = buffer;
      }

      // Browsers suspend AudioContext until a user gesture. Resume on demand.
      if (context.state === 'suspended') {
        try {
          await context.resume();
        } catch {
          return;
        }
      }

      const source = context.createBufferSource();
      source.buffer = buffersRef.current[level]!;
      source.connect(gain);
      source.start(0);
    },
    [isMuted, ensureContext],
  );

  const mute = useCallback((durationMinutes?: number) => {
    setIsMuted(true);
    writeMuted(true);

    if (unmuteTimerRef.current) {
      clearTimeout(unmuteTimerRef.current);
      unmuteTimerRef.current = null;
    }

    if (durationMinutes && durationMinutes > 0) {
      const unmuteAt = Date.now() + durationMinutes * 60 * 1000;
      writeUnmuteAt(unmuteAt);
      unmuteTimerRef.current = setTimeout(
        () => {
          setIsMuted(false);
          writeMuted(false);
          writeUnmuteAt(null);
        },
        durationMinutes * 60 * 1000,
      );
    } else {
      writeUnmuteAt(null);
    }
  }, []);

  const unmute = useCallback(() => {
    setIsMuted(false);
    writeMuted(false);
    writeUnmuteAt(null);
    if (unmuteTimerRef.current) {
      clearTimeout(unmuteTimerRef.current);
      unmuteTimerRef.current = null;
    }
  }, []);

  const setVolume = useCallback((v: number) => {
    const clamped = Math.max(0, Math.min(1, v));
    setVolumeState(clamped);
    writeVolume(clamped);
  }, []);

  return {
    isMuted,
    volume,
    playAlert,
    mute,
    unmute,
    setVolume,
  };
}

export default useAudioAlert;
