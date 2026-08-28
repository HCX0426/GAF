/**
 * C1 spec 2026-07-30: trace_id 前端生成与存储单测。
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { generateTraceId, getLastTraceId, setLastTraceId } from '@/utils/traceId';

describe('traceId', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  describe('generateTraceId', () => {
    it('returns UUID v4 format (8-4-4-4-12 hex with version/variant bits)', () => {
      const id = generateTraceId();
      // UUID v4: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx (y = 8/9/a/b)
      expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
    });

    it('returns unique values on successive calls', () => {
      const id1 = generateTraceId();
      const id2 = generateTraceId();
      expect(id1).not.toBe(id2);
    });
  });

  describe('getLastTraceId', () => {
    it('returns empty string when not set', () => {
      expect(getLastTraceId()).toBe('');
    });

    it('returns value set by setLastTraceId', () => {
      setLastTraceId('550e8400-e29b-41d4-a716-446655440000');
      expect(getLastTraceId()).toBe('550e8400-e29b-41d4-a716-446655440000');
    });
  });

  describe('setLastTraceId', () => {
    it('overwrites previous value', () => {
      setLastTraceId('first-uuid');
      setLastTraceId('second-uuid');
      expect(getLastTraceId()).toBe('second-uuid');
    });
  });
});
