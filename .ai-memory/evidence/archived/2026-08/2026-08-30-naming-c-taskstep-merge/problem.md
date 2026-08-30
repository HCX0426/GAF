# Problem

## Background
TaskStep and ExecutionStep are two overlapping runtime step models. TaskStep is a legacy dead model (zero production writes), ExecutionStep is the authoritative runtime model.

## Impact
- Conceptual duplication: two step models with overlapping semantics
- Maintenance burden: serializers, views, tests reference both
- Migration complexity: FK execution -> task_result needs rename

## Trigger
Naming normalization plan C-4 (docs/analysis/concept-naming-normalization.md section 5/OQ-3)
