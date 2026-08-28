---
maintainer: auto
source: agent/src/engine/nodes/*.py
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
- agent/src/engine/node.py
- agent/src/engine/nodes/__init__.py
- agent/src/engine/context.py
- agent/src/engine/pipeline_engine.py
- agent/src/engine/parser.py
- agent/src/engine/validator.py
- agent/src/core/result.py
- agent/src/core/exceptions.py
- docs/business/tasks/pipeline-authoring-guide.md
created_by: AI
generated: 2026-06-16
auto_updated: 2026-07-04
---

        # Auto-generated knowledge entry

        <!-- source: agent/src/engine/nodes/*.py -->
        <!-- generated: 2026-08-28 -->

        ## Symptom

        kb:pipeline:nodes, pipeline-step-type, PipelineNode, register_node

        ## Solution

        37 个节点类型 @register_node 注册, base class PipelineNode + AutoResult 输出

        ## Related files

        - `agent/src/engine/node.py`
- `agent/src/engine/nodes/__init__.py`
- `agent/src/engine/context.py`
- `agent/src/engine/pipeline_engine.py`
- `agent/src/engine/parser.py`
- `agent/src/engine/validator.py`
- `agent/src/core/result.py`
- `agent/src/core/exceptions.py`
- `docs/business/tasks/pipeline-authoring-guide.md`

        <!-- end of auto-generated section -->
