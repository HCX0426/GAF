# Solution

## Approach
1. Global rename TaskStep -> ExecutionStep (exclude TaskStepConfigLegacy)
2. Delete duplicate ExecutionStep class, add retry_count to canonical ExecutionStep
3. Rename FK execution -> task_result across 14 backend files
4. Rewrite ExecutionStepSerializer (execution->task_result, remove result_data/error_code/user_message)
5. Update frontend api.generated.ts (execution->task_result, add retry_count)
6. Generate Django migration 0058: AddField retry_count + DeleteModel TaskStep
7. Fix all related tests (test_node_trace, test_retry_from_step, test_dispatch_ack, etc.)
8. Fix remaining execution__ FK references in executions/views.py

## Files Changed
- 21 files changed, 206 insertions(+), 355 deletions(-)
- Backend: tasks/models.py, serializers.py, execution_views.py, admin.py, views.py, tests
- Frontend: api.generated.ts, executions.ts, tasks.ts, task.ts
