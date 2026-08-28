"""Skill YAML 加载与解析：读取 YAML 文件、校验结构、版本管理"""

import logging
import os
from typing import Any

import yaml
from django.conf import settings

logger = logging.getLogger(__name__)

# Always-required fields for every Skill YAML.
SKILL_REQUIRED_FIELDS = ["name", "description"]

# Optional fields recognised on every Skill YAML.
SKILL_OPTIONAL_FIELDS = [
    "version",
    "applicable_scenarios",
    "author",
    "model",
    "is_builtin",
    "context",
    "parameters",
    "output",
    "cost_control",
]

# Two mutually-compatible schemas are accepted:
#   * Legacy: parsing_steps (list) + output_template (dict) — used by
#     debug/tasks.py:_build_analysis_prompt for log-archive analysis.
#   * Design §3.1: system_prompt (str) + user_prompt_template (str) —
#     used by the 6 builtin Skills defined in
#     docs/business/ai/llm-integration.md §4.
# A YAML may carry either schema; validate() enforces each schema's
# internal consistency when its anchor field is present.
SKILL_LEGACY_FIELDS = ["parsing_steps", "output_template"]
SKILL_DESIGN_FIELDS = ["system_prompt", "user_prompt_template"]


class SkillLoader:
    """Skill 加载器：从 YAML 文件加载 Skill 定义并校验"""

    @staticmethod
    def load_from_yaml(file_path: str) -> dict[str, Any]:
        """从 YAML 文件加载 Skill 定义

        Args:
            file_path: YAML 文件路径

        Returns:
            解析后的 Skill 定义字典

        Raises:
            SkillLoadError: 加载或校验失败
        """
        if not os.path.isfile(file_path):
            raise SkillLoadError(f"Skill 文件不存在: {file_path}")

        try:
            with open(file_path, encoding='utf-8') as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise SkillLoadError(f"YAML 解析失败: {exc}") from exc

        if not isinstance(data, dict):
            raise SkillLoadError("Skill YAML 根元素必须是字典")

        errors = SkillLoader.validate(data)
        if errors:
            raise SkillLoadError(f"Skill 校验失败: {'; '.join(errors)}")

        return data

    @staticmethod
    def validate(data: dict[str, Any]) -> list[str]:
        """校验 Skill 定义结构

        Accepts two compatible schemas (see module docstring):
            * Legacy: ``parsing_steps`` + ``output_template``
            * Design §3.1: ``system_prompt`` + ``user_prompt_template``
        A YAML may carry either schema. If both schemas are absent the
        validator reports a missing-prompt-block error.

        Args:
            data: Skill 定义字典

        Returns:
            错误列表，空列表表示校验通过
        """
        errors = []

        for field in SKILL_REQUIRED_FIELDS:
            if field not in data:
                errors.append(f"缺少必需字段: {field}")
            elif not data[field]:
                errors.append(f"字段 {field} 不能为空")

        # ── Legacy schema: parsing_steps + output_template ──
        if "parsing_steps" in data:
            steps = data["parsing_steps"]
            if not isinstance(steps, list):
                errors.append("parsing_steps 必须是列表")
            elif len(steps) == 0:
                errors.append("parsing_steps 不能为空列表")

        if "output_template" in data:
            template = data["output_template"]
            if not isinstance(template, dict):
                errors.append("output_template 必须是字典")

        # ── Design §3.1 schema: system_prompt + user_prompt_template ──
        if "system_prompt" in data:
            sp = data["system_prompt"]
            if not isinstance(sp, str) or not sp.strip():
                errors.append("system_prompt 必须是非空字符串")

        if "user_prompt_template" in data:
            upt = data["user_prompt_template"]
            if not isinstance(upt, str) or not upt.strip():
                errors.append("user_prompt_template 必须是非空字符串")

        # If neither schema is present, the YAML carries no prompt block
        # and is effectively useless. Report a single consolidated error.
        has_legacy = any(f in data for f in SKILL_LEGACY_FIELDS)
        has_design = any(f in data for f in SKILL_DESIGN_FIELDS)
        if not has_legacy and not has_design and not errors:
            errors.append(
                "缺少 prompt 块: 需要 parsing_steps/output_template "
                "或 system_prompt/user_prompt_template"
            )

        # ── Optional field type checks ──
        if "applicable_scenarios" in data:
            scenarios = data["applicable_scenarios"]
            if not isinstance(scenarios, list):
                errors.append("applicable_scenarios 必须是列表")

        if "context" in data:
            ctx = data["context"]
            if not isinstance(ctx, dict):
                errors.append("context 必须是字典")

        if "parameters" in data:
            params = data["parameters"]
            if not isinstance(params, dict):
                errors.append("parameters 必须是字典")

        if "output" in data:
            out = data["output"]
            if not isinstance(out, dict):
                errors.append("output 必须是字典")

        if "cost_control" in data:
            cc = data["cost_control"]
            if not isinstance(cc, dict):
                errors.append("cost_control 必须是字典")

        return errors

    @staticmethod
    def load_builtin_skills() -> list[dict[str, Any]]:
        """加载所有内置 Skill YAML 文件

        从 ``backend/skills/builtin/`` 目录下扫描所有 ``.yaml`` /
        ``.yml`` 文件并加载。该子目录专门存放内置 Skill YAML，
        与 ``skills/`` 包根目录下的 Python 模块隔离，避免误扫描。

        Returns:
            成功加载的 Skill 定义列表
        """
        skills_dir = os.path.join(settings.BASE_DIR, 'skills', 'builtin')
        skills: list = []

        if not os.path.isdir(skills_dir):
            logger.warning("内置 Skills 目录不存在: %s", skills_dir)
            return skills

        for fname in sorted(os.listdir(skills_dir)):
            if not fname.endswith('.yaml') and not fname.endswith('.yml'):
                continue
            fpath = os.path.join(skills_dir, fname)
            try:
                skill_data = SkillLoader.load_from_yaml(fpath)
                skill_data['_source_file'] = fname
                skills.append(skill_data)
                logger.info(
                    "加载内置 Skill: %s (v%s)",
                    skill_data.get('name'),
                    skill_data.get('version', '0.1'),
                )
            except SkillLoadError as exc:
                logger.error("加载 Skill %s 失败: %s", fname, exc)

        return skills

    @staticmethod
    def sync_to_database() -> int:
        """将内置 Skills 同步到数据库

        遍历所有内置 Skill YAML 文件，对数据库中的记录进行
        create_or_update 操作。

        Returns:
            同步的 Skill 数量
        """
        from skills.models import SkillDefinition

        skills = SkillLoader.load_builtin_skills()
        count = 0

        for skill_data in skills:
            name = skill_data.get('name', '')
            obj, created = SkillDefinition.objects.update_or_create(
                name=name,
                defaults={
                    'description': skill_data.get('description', ''),
                    'yaml_content': yaml.dump(
                        skill_data, allow_unicode=True, default_flow_style=False
                    ),
                    'version': skill_data.get('version', '0.1'),
                    'applicable_scenarios': skill_data.get('applicable_scenarios', []),
                    'is_builtin': True,
                    'is_enabled': True,
                },
            )
            count += 1
            action = "创建" if created else "更新"
            logger.info("%s 内置 Skill: %s v%s", action, name, obj.version)

        return count


class SkillLoadError(Exception):
    """Skill 加载错误"""
