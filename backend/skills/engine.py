"""Skill 自动匹配引擎：根据关键词和场景自动匹配最合适的 Skill"""

import logging
import re
from typing import Any

from skills.models import SkillDefinition

logger = logging.getLogger(__name__)

SCENE_KEYWORDS: dict[str, list[str]] = {
    "error_diagnosis": ["error", "exception", "traceback", "失败", "报错", "崩溃", "crash", "fail"],
    "template_analysis": ["template", "模板", "匹配", "match", "识别", "recognize", "find"],
    "coordinate": ["coordinate", "坐标", "偏移", "offset", "位置", "position", "click"],
    "task_optimization": ["task", "任务", "优化", "optimize", "流程", "flow", "chain"],
    "anomaly": ["anomaly", "异常", "pattern", "模式", "监控", "monitor", "alert"],
    "qa": ["question", "问题", "qa", "问答", "技术", "technical", "how", "why"],
}


def extract_keywords(text: str) -> list[str]:
    """从文本中提取关键词

    Args:
        text: 输入文本

    Returns:
        提取的关键词列表
    """
    tokens = re.findall(r'[a-zA-Z_]+|[\u4e00-\u9fff]{2,}', text.lower())
    result = list(tokens)
    chinese_segments = re.findall(r'[\u4e00-\u9fff]{3,}', text)
    for seg in chinese_segments:
        for i in range(len(seg) - 1):
            bigram = seg[i:i+2]
            if bigram not in result:
                result.append(bigram)
    return result


def match_skills(
    keywords: list[str],
    scene: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """根据关键词和场景自动匹配 Skill

    Args:
        keywords: 关键词列表
        scene: 可选的场景标识
        limit: 返回结果数量上限

    Returns:
        匹配的 Skill 列表，按匹配度降序排列
    """
    all_skills = SkillDefinition.objects.filter(is_enabled=True)
    scored_skills: list[dict[str, Any]] = []

    for skill in all_skills:
        score = 0.0

        if scene and scene in SCENE_KEYWORDS:
            scene_kw = SCENE_KEYWORDS[scene]
            overlap = set(keywords) & set(scene_kw)
            if overlap:
                score += len(overlap) / len(scene_kw) * 40

        skill_text = f"{skill.name} {skill.description}".lower()
        for kw in keywords:
            if kw in skill_text:
                score += 10

        if skill.is_builtin:
            score += 5

        if score > 0:
            scored_skills.append({
                "skill_id": skill.pk,
                "skill_name": skill.name,
                "description": skill.description,
                "score": score,
                "is_builtin": skill.is_builtin,
            })

    scored_skills.sort(key=lambda x: x["score"], reverse=True)
    logger.info("Skill 匹配完成: %d 个关键词, %d 个匹配结果", len(keywords), len(scored_skills))
    return scored_skills[:limit]
