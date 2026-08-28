"""Model evaluation engine — runs multiple LLMs on test cases and scores outputs (P-031)."""
import logging
import time
from decimal import Decimal
from typing import Any

from django.utils import timezone

from .llm_service import call_llm
from .models import ModelEvaluation, ModelEvaluationResult

logger = logging.getLogger(__name__)


def run_evaluation(evaluation_id: int) -> None:
    """Run a model evaluation synchronously.

    For each test case × each model config, call the LLM and record the result.
    Scoring is done via a simple heuristic (response length + non-empty + no error)
    when no judge model is configured. When scoring_criteria is provided, scores
    are computed per criterion.
    """
    try:
        evaluation = ModelEvaluation.objects.get(pk=evaluation_id)
    except ModelEvaluation.DoesNotExist:
        logger.error('ModelEvaluation %s not found', evaluation_id)
        return

    evaluation.status = ModelEvaluation.Status.RUNNING
    evaluation.error_message = ''
    evaluation.save(update_fields=['status', 'error_message', 'updated_at'])

    test_cases = evaluation.test_cases or []
    models_config = evaluation.models_config or []
    criteria = evaluation.scoring_criteria or []

    if not test_cases:
        evaluation.status = ModelEvaluation.Status.FAILED
        evaluation.error_message = 'No test cases provided'
        evaluation.save(update_fields=['status', 'error_message', 'updated_at'])
        return

    if not models_config:
        evaluation.status = ModelEvaluation.Status.FAILED
        evaluation.error_message = 'No models to compare'
        evaluation.save(update_fields=['status', 'error_message', 'updated_at'])
        return

    has_error = False
    for case_idx, test_input in enumerate(test_cases):
        for model_cfg in models_config:
            result = _evaluate_single(
                evaluation=evaluation,
                case_idx=case_idx,
                test_input=str(test_input),
                model_cfg=model_cfg,
                criteria=criteria,
            )
            if not result.is_success:
                has_error = True

    evaluation.status = ModelEvaluation.Status.COMPLETED
    evaluation.completed_at = timezone.now()
    if has_error:
        evaluation.error_message = 'Some evaluations failed — see individual results'
    evaluation.save(update_fields=['status', 'completed_at', 'error_message', 'updated_at'])


def _evaluate_single(
    evaluation: ModelEvaluation,
    case_idx: int,
    test_input: str,
    model_cfg: dict[str, Any],
    criteria: list[dict[str, Any]],
) -> ModelEvaluationResult:
    """Evaluate a single model on a single test case."""
    provider = str(model_cfg.get('provider', 'openai'))
    model_name = str(model_cfg.get('model', model_cfg.get('default_model', 'gpt-4o-mini')))
    api_base = model_cfg.get('api_base') or None
    api_key = model_cfg.get('api_key') or None
    temperature = float(model_cfg.get('temperature', 0.3))
    max_tokens = int(model_cfg.get('max_tokens', 1024))

    messages = []
    if evaluation.system_prompt:
        messages.append({'role': 'system', 'content': evaluation.system_prompt})
    messages.append({'role': 'user', 'content': test_input})

    start = time.monotonic()
    response = call_llm(
        messages=messages,
        model=model_name,
        api_key=api_key,
        api_base=api_base,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=False,
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    is_success = 'error' not in response
    output_text = response.get('content', '')
    error_text = response.get('error', '') if not is_success else ''
    input_tokens = int(response.get('input_tokens', 0))
    output_tokens = int(response.get('output_tokens', 0))
    cost = Decimal(str(response.get('cost', 0)))

    scores: dict[str, float] = {}
    if is_success and criteria:
        scores = _compute_scores(output_text, criteria)
    elif is_success:
        # Default heuristic scoring when no criteria provided
        scores = _default_heuristic_score(output_text)

    avg_score = _weighted_average(scores, criteria) if scores else 0.0

    result = ModelEvaluationResult.objects.create(
        evaluation=evaluation,
        test_case_index=case_idx,
        provider=provider,
        model_name=model_name,
        output_text=output_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=cost,
        latency_ms=latency_ms,
        scores=scores,
        average_score=avg_score,
        error=error_text,
        is_success=is_success,
    )
    return result


def _compute_scores(output_text: str, criteria: list[dict[str, Any]]) -> dict[str, float]:
    """Compute scores per criterion using simple heuristics.

    Each criterion is scored 0-10 based on:
    - relevance: response length relative to a target (longer = better, up to a cap)
    - fluency: presence of complete sentences (periods/newlines)
    - accuracy: non-empty response
    - completeness: response length > 50 chars
    Custom criteria default to a length-based score.
    """
    scores: dict[str, float] = {}
    text_len = len(output_text.strip())
    has_content = text_len > 0
    has_sentences = output_text.count('.') + output_text.count('。') + output_text.count('\n') >= 1

    for criterion in criteria:
        name = str(criterion.get('name', 'score'))
        score = 5.0  # baseline
        if name == 'accuracy':
            score = 10.0 if has_content else 0.0
        elif name == 'fluency':
            score = 8.0 if has_sentences else 4.0 if has_content else 0.0
        elif name == 'relevance':
            score = min(10.0, text_len / 50.0) if has_content else 0.0
        elif name == 'completeness':
            score = 10.0 if text_len >= 50 else (5.0 if text_len >= 10 else 0.0)
        else:
            # Generic: length-based
            score = min(10.0, text_len / 100.0) if has_content else 0.0
        scores[name] = round(score, 2)
    return scores


def _default_heuristic_score(output_text: str) -> dict[str, float]:
    """Default scoring when no criteria provided."""
    text_len = len(output_text.strip())
    return {
        'quality': round(min(10.0, text_len / 100.0), 2) if text_len > 0 else 0.0,
        'length': round(min(10.0, text_len / 200.0), 2) if text_len > 0 else 0.0,
    }


def _weighted_average(scores: dict[str, float], criteria: list[dict[str, Any]]) -> float:
    """Compute weighted average of scores based on criterion weights."""
    if not scores:
        return 0.0
    total_weight = 0.0
    total_score = 0.0
    for criterion in criteria:
        name = str(criterion.get('name', ''))
        weight = float(criterion.get('weight', 1.0))
        if name in scores:
            total_weight += weight
            total_score += scores[name] * weight
    if total_weight == 0:
        # No criteria matched — simple average
        return round(sum(scores.values()) / len(scores), 2) if scores else 0.0
    return round(total_score / total_weight, 2)
