---
maintainer: auto
source: worker/src/engine/nodes/*.py
load_when:
- 新功能
- Bug修复
priority: high
symptom:
- kb:pipeline:nodes
- pipeline-step-type
- PipelineNode
- register_node
solution: 37 个节点类型 @register_node 注册, base class PipelineNode + AutoResult 输出
related_files:
- worker/src/engine/node.py
- worker/src/engine/nodes/__init__.py
- worker/src/engine/context.py
- worker/src/engine/pipeline_engine.py
- worker/src/engine/parser.py
- worker/src/engine/validator.py
- worker/src/core/result.py
- worker/src/core/exceptions.py
- docs/business/tasks/pipeline-authoring-guide.md
created_by: AI
generated: 2026-06-16
auto_updated: 2026-07-04
---

        # Auto-generated knowledge entry

        <!-- source: worker/src/engine/nodes/*.py -->
        <!-- generated: 2026-08-29 -->

        ## Symptom

        kb:pipeline:nodes, pipeline-step-type, PipelineNode, register_node

        ## Solution

        37 个节点类型 @register_node 注册, base class PipelineNode + AutoResult 输出

        ## Related files

        - `worker/src/engine/node.py`
- `worker/src/engine/nodes/__init__.py`
- `worker/src/engine/context.py`
- `worker/src/engine/pipeline_engine.py`
- `worker/src/engine/parser.py`
- `worker/src/engine/validator.py`
- `worker/src/core/result.py`
- `worker/src/core/exceptions.py`
- `docs/business/tasks/pipeline-authoring-guide.md`

        <!-- end of auto-generated section -->
