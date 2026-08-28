/**
 * llm domain models (s37 split from models.ts — TD-365).
 */
export interface LlmConfig {
  id?: number;
  provider: string;
  api_key: string;
  api_base: string;
  default_model: string;
  temperature: number;
  max_tokens: number;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

/** Model evaluation status */

export type ModelEvaluationStatus = 'pending' | 'running' | 'completed' | 'failed';

/** Single model config in an evaluation */

export interface EvaluationModelConfig {
  provider: string;
  model: string;
  api_base?: string;
  api_key?: string;
  temperature?: number;
  max_tokens?: number;
}

/** Scoring criterion for evaluation */

export interface ScoringCriterion {
  name: string;
  weight: number;
  description?: string;
}

/** Result of evaluating one model on one test case */

export interface ModelEvaluationResult {
  id: number;
  test_case_index: number;
  provider: string;
  model_name: string;
  output_text: string;
  input_tokens: number;
  output_tokens: number;
  cost: number;
  latency_ms: number;
  scores: Record<string, number>;
  average_score: number;
  error: string;
  is_success: boolean;
  created_at: string;
}

/** Model evaluation — compares multiple LLMs on test cases */

export interface ModelEvaluation {
  id: number;
  name: string;
  description: string;
  system_prompt: string;
  test_cases: string[];
  models_config: EvaluationModelConfig[];
  scoring_criteria: ScoringCriterion[];
  status: ModelEvaluationStatus;
  error_message: string;
  created_by: number;
  created_by_name: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  results: ModelEvaluationResult[];
}

/** Payload for creating a new evaluation */

export interface CreateModelEvaluationPayload {
  name: string;
  description?: string;
  system_prompt?: string;
  test_cases: string[];
  models_config: EvaluationModelConfig[];
  scoring_criteria?: ScoringCriterion[];
}

/** Aggregated summary per model (from /summary/ endpoint) */

export interface ModelEvaluationSummaryItem {
  provider: string;
  model_name: string;
  total_cases: number;
  success_count: number;
  failure_count: number;
  success_rate: number;
  avg_score: number;
  total_cost: number;
  avg_latency_ms: number;
  total_input_tokens: number;
  total_output_tokens: number;
}

export interface ModelEvaluationSummary {
  evaluation_id: number;
  evaluation_name: string;
  status: ModelEvaluationStatus;
  summary: ModelEvaluationSummaryItem[];
}

/** unattended recover strategy config */
