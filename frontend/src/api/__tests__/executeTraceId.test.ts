/**
 * C1 (spec 2026-07-30): verify executeTask / executePipeline generate trace_id
 * before the API call and store it in sessionStorage for the request interceptor
 * to attach as X-Trace-Id header.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getLastTraceId } from '@/utils/traceId';

// Mock the axios client so no real HTTP request is made.
// The mock returns a bare response object (interceptors don't run in mock mode),
// so getLastTraceId() after the call returns exactly what executeTask generated.
vi.mock('@/api/client', () => ({
  default: {
    post: vi.fn().mockResolvedValue({
      data: { id: 1, status: 'pending', task: 42 },
    }),
    get: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

import client from '@/api/client';
import { executeTask } from '@/api/tasks';
import { executePipeline } from '@/api/pipelines';

describe('C1: executeTask trace_id generation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it('generates trace_id and stores in sessionStorage before API call', async () => {
    await executeTask(42);

    // After executeTask, sessionStorage should have a trace_id
    // (the mocked client doesn't run response interceptor, so this is the
    // trace_id that executeTask generated, not a backend-echoed one)
    const traceId = getLastTraceId();
    expect(traceId).toBeTruthy();
    expect(traceId).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
  });

  it('generates a new trace_id on each call', async () => {
    await executeTask(1);
    const traceId1 = getLastTraceId();

    await executeTask(2);
    const traceId2 = getLastTraceId();

    expect(traceId1).not.toBe(traceId2);
  });

  it('calls client.post with correct URL and parameters', async () => {
    await executeTask(42, { foo: 'bar' });

    expect(client.post).toHaveBeenCalledWith('/tasks/42/execute/', {
      parameters: { foo: 'bar' },
    });
  });

  it('works with no params', async () => {
    await executeTask(7);

    expect(client.post).toHaveBeenCalledWith('/tasks/7/execute/', {
      parameters: undefined,
    });
    expect(getLastTraceId()).toBeTruthy();
  });
});

describe('C1: executePipeline trace_id generation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it('generates trace_id and stores in sessionStorage before API call', async () => {
    await executePipeline(5);

    const traceId = getLastTraceId();
    expect(traceId).toBeTruthy();
    expect(traceId).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
  });

  it('generates a new trace_id on each call', async () => {
    await executePipeline(1);
    const traceId1 = getLastTraceId();

    await executePipeline(2);
    const traceId2 = getLastTraceId();

    expect(traceId1).not.toBe(traceId2);
  });

  it('calls apiClient.post with correct URL and device_id', async () => {
    await executePipeline(5, 'device-001');

    expect(client.post).toHaveBeenCalledWith('/pipeline/pipelines/5/execute/', {
      device_id: 'device-001',
    });
  });
});
