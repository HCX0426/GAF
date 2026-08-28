"""项目问答上下文构建 (migrated from qa app — 2026-08-04)."""

import json
import logging
import os
from typing import Any

from django.apps import apps
from django.conf import settings

logger = logging.getLogger(__name__)

MAX_CONTEXT_TOKENS = 8000
CHARS_PER_TOKEN = 4


def build_qa_context(question: str, extra_context: dict[str, Any] | None = None) -> dict[str, Any]:
    sections: list[str] = []
    metadata: dict[str, Any] = {"sections": [], "total_chars": 0}

    project_overview = _get_project_overview()
    sections.append(project_overview)
    metadata["sections"].append("project_overview")

    skill_summary = _get_skill_summary()
    if skill_summary:
        sections.append(skill_summary)
        metadata["sections"].append("skill_summary")

    directory_structure = _get_directory_structure()
    if directory_structure:
        sections.append(directory_structure)
        metadata["sections"].append("directory_structure")

    model_summary = _get_model_summary()
    if model_summary:
        sections.append(model_summary)
        metadata["sections"].append("model_summary")

    rag_section = _get_rag_context(question)
    if rag_section:
        sections.append(rag_section["text"])
        metadata["sections"].append("rag_retrieval")
        metadata["rag_results"] = rag_section["results"]

    if extra_context:
        extra_text = "## 用户补充上下文\n" + json.dumps(extra_context, ensure_ascii=False, indent=2)
        sections.append(extra_text)
        metadata["sections"].append("extra_context")

    context_text = "\n\n".join(sections)
    max_chars = MAX_CONTEXT_TOKENS * CHARS_PER_TOKEN
    if len(context_text) > max_chars:
        context_text = context_text[:max_chars] + "\n\n[上下文已截断]"

    metadata["total_chars"] = len(context_text)
    metadata["estimated_tokens"] = len(context_text) // CHARS_PER_TOKEN
    return {"context_text": context_text, "metadata": metadata}


def _get_project_overview() -> str:
    return """## GAF 项目架构概述

GAF (General Automation Framework) 是一个通用桌面自动化框架，采用三层架构：

1. **Agent 层**：运行在目标应用所在机器，负责设备控制、图像识别、任务执行、监控守护
2. **Server 层**：Django 后端，提供 REST API + WebSocket
3. **Client 层**：React Web 前端"""


def _get_skill_summary() -> str:
    try:
        from skills.models import SkillDefinition
        skills = SkillDefinition.objects.filter(is_enabled=True)
        if not skills.exists():
            return ""
        lines = ["## 可用 Skills"]
        for skill in skills:
            scenarios = ", ".join(skill.applicable_scenarios[:5]) if skill.applicable_scenarios else "无"
            lines.append(f"- **{skill.name}** (v{skill.version}): {skill.description} [场景: {scenarios}]")
        return "\n".join(lines)
    except Exception:
        return ""


def _get_directory_structure() -> str:
    base_dir = settings.BASE_DIR
    lines = ["## 项目目录结构"]

    def _walk(directory, prefix="", depth=0):
        if depth > 3:
            return
        try:
            entries = sorted(os.listdir(directory))
        except OSError:
            return
        skip = {'.git', '__pycache__', 'node_modules', '.venv', 'migrations', 'staticfiles', '.next'}
        entries = [e for e in entries if e not in skip and not e.startswith('.')]
        for i, entry in enumerate(entries[:15]):
            path = os.path.join(directory, entry)
            connector = "└── " if i == len(entries[:15]) - 1 else "├── "
            lines.append(f"{prefix}{connector}{entry}")
            if os.path.isdir(path) and depth < 3:
                extension = "    " if i == len(entries[:15]) - 1 else "│   "
                _walk(path, prefix + extension, depth + 1)

    _walk(str(base_dir))
    return "\n".join(lines)


def _get_model_summary() -> str:
    lines = ["## 关键数据模型"]
    model_configs = [
        ("accounts", "User"), ("agents", "Agent"), ("tasks", "Task"),
        ("tasks", "TaskExecution"), ("tasks", "CustomTask"), ("tasks", "ScheduledTask"),
        ("resources", "ResourcePack"), ("skills", "SkillDefinition"),
        ("debug", "DebugLogArchive"), ("debug", "LLMAnalysisResult"),
        ("gaf_ai", "QASession"), ("gaf_ai", "LLMUsageLog"),
        ("monitors", "MonitorRule"), ("monitors", "MonitorEvent"),
    ]
    for app_label, model_name in model_configs:
        try:
            model = apps.get_model(app_label, model_name)
            fields = []
            for field in model._meta.get_fields():
                if hasattr(field, 'name') and field.name != 'id':
                    field_type = field.__class__.__name__
                    fields.append(f"{field.name}({field_type})")
            lines.append(f"- **{model_name}**: {', '.join(fields[:8])}")
        except LookupError:
            continue
    return "\n".join(lines)


def _get_rag_context(question: str) -> dict[str, Any] | None:
    try:
        from gaf_ai.rag import get_rag_retriever
        retriever = get_rag_retriever()
        results = retriever.search(question, top_k=5)
        if not results:
            return None
        lines = ["## 相关代码/文档（RAG 检索）"]
        for i, r in enumerate(results, 1):
            filepath = r.get("filepath", "")
            score = r.get("score", 0)
            content = r.get("content", "")[:300]
            lines.append(f"### {i}. {filepath} (score: {score:.3f})")
            lines.append(f"```\n{content}\n```")
        return {"text": "\n".join(lines), "results": results}
    except Exception as e:
        logger.warning(f"RAG retrieval failed: {e}")
        return None
