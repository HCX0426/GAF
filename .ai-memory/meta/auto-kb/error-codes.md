---
maintainer: auto
source: agent/src/core/exceptions.py, backend/**/exceptions.py, backend/config/settings/base.py
load_when:
- Bug修复
priority: high
symptom:
- kb:error:codes
- error-handling
- exception-hierarchy
- AutoBaseError
- DRF-exception
solution: Agent 端 6 类 AutoBaseError + 后端 LLMAPI/SkillLoad/Decryption 异常 + DRF 默认状态码 + 协议 build_error_frame
related_files:
- agent/src/core/exceptions.py
- agent/src/core/result.py
- agent/src/ai/llm_client.py
- backend/skills/loader.py
- backend/accounts/crypto.py
- backend/protocol/serializers.py
- backend/config/settings/base.py
created_by: AI
generated: 2026-06-16
auto_updated: 2026-07-26
---

        # Auto-generated knowledge entry

        <!-- source: agent/src/core/exceptions.py, backend/**/exceptions.py, backend/config/settings/base.py -->
        <!-- generated: 2026-08-29 -->

        ## Symptom

        kb:error:codes, error-handling, exception-hierarchy, AutoBaseError, DRF-exception

        ## Solution

        Agent 端 6 类 AutoBaseError + 后端 LLMAPI/SkillLoad/Decryption 异常 + DRF 默认状态码 + 协议 build_error_frame

        ## Related files

        - `agent/src/core/exceptions.py`
- `agent/src/core/result.py`
- `agent/src/ai/llm_client.py`
- `backend/skills/loader.py`
- `backend/accounts/crypto.py`
- `backend/protocol/serializers.py`
- `backend/config/settings/base.py`

        <!-- end of auto-generated section -->
