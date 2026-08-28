/**
 * Agent management API
 * Covers agent CRUD, token generation, deletion
 */
import client from './client';
import type { Agent, PaginatedResponse } from '@/types/models';

/** Fetch agent list */
export async function fetchAgents(params?: Record<string, unknown>): Promise<PaginatedResponse<Agent>> {
  const res = await client.get<PaginatedResponse<Agent>>('/agents/', { params });
  return res.data;
}

/** Fetch single agent detail */
export async function fetchAgent(agentId: number): Promise<Agent> {
  const res = await client.get<Agent>(`/agents/${agentId}/`);
  return res.data;
}

/** Generate agent token */
export async function generateAgentToken(agentId: number): Promise<Agent> {
  const res = await client.post<Agent>(`/agents/${agentId}/generate-token/`);
  return res.data;
}

/** Delete agent */
export async function deleteAgent(agentId: number): Promise<void> {
  await client.delete(`/agents/${agentId}/`);
}
