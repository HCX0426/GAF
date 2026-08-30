# verification.md — P4 验收证据 (commit 8ff7889)

## 提交
- `8ff7889` refactor(protocol): rename AgentConsumer->WorkerConsumer and WS AgentSession->WorkerSession (31 files, 202+/175-, 治理 17/18 PASS + 1 WARN doc-path-drift)

## 测试 / 检查
| 项 | 结果 |
|----|------|
| pytest protocol | 284 passed / 3 deselected / 0 failed |
| pytest protocol+workers+device_bridge+monitors+tests+gaf_ai.test_ws_rpc+gaf_core | 772 passed / 85 deselected / 0 failed |
| makemigrations --check --dry-run | No changes detected |
| migrate --plan | 仅 protocol.0004 (Rename model + Rename table), 无环 |
| manage.py check | no issues |
| ruff (protocol + 3 个注释文件 + settings) | 7 I001 auto-fixed, All checks passed |

## 迁移内容
protocol.0004_rename_agentsession_to_workersession:
- RenameModel AgentSession -> WorkerSession
- AlterModelTable -> protocol_workersession
- 旧名残留: 仅 protocol/0001+0002 (冻结历史) + 0004 old_name + frontend 生成文件 (P6)