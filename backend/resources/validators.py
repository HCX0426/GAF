"""资源包校验机制：Schema 校验、版本兼容性检查、完整性验证"""

import json
import logging
import os
from typing import Any

from resources.models import ResourcePack

logger = logging.getLogger(__name__)

REQUIRED_DIRS = ["templates"]
OPTIONAL_DIRS = ["config", "monitors", "tasks", "custom_tasks"]

MANIFEST_REQUIRED_FIELDS = ["name", "version", "target_app", "author", "gaf_version"]
MANIFEST_RECOMMENDED_FIELDS = ["description"]

GAF_VERSION = "0.1.0"


def validate_resource_pack_structure(directory_path: str) -> dict[str, Any]:
    """校验资源包目录结构完整性，包括 manifest.json 必需字段和目录结构。

    Args:
        directory_path: 资源包目录路径

    Returns:
        校验结果 {"valid", "errors", "warnings"}
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not os.path.isdir(directory_path):
        return {"valid": False, "errors": [f"目录不存在: {directory_path}"], "warnings": []}

    _validate_manifest(directory_path, errors, warnings)
    _validate_required_dirs(directory_path, errors)
    _validate_optional_dirs(directory_path, warnings)
    _validate_config_dir(directory_path, errors, warnings)
    _validate_templates_dir(directory_path, warnings)
    _validate_tasks_dir(directory_path, warnings)
    _validate_monitors_dir(directory_path, warnings)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def _validate_manifest(directory_path: str, errors: list[str], warnings: list[str]) -> None:
    """校验 manifest.json 文件的存在性和必需字段。

    Args:
        directory_path: 资源包目录路径
        errors: 错误列表，校验失败时追加
        warnings: 警告列表，校验警告时追加
    """
    manifest_path = os.path.join(directory_path, "manifest.json")
    if not os.path.isfile(manifest_path):
        errors.append("缺少必需文件: manifest.json")
        return

    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except json.JSONDecodeError as exc:
        errors.append(f"manifest.json JSON 解析失败: {exc}")
        return

    for field in MANIFEST_REQUIRED_FIELDS:
        if field not in manifest:
            errors.append(f"manifest.json 缺少必需字段: {field}")
        elif not manifest[field]:
            errors.append(f"manifest.json 必需字段为空: {field}")

    for field in MANIFEST_RECOMMENDED_FIELDS:
        if field not in manifest or not manifest[field]:
            warnings.append(f"manifest.json 建议填写字段: {field}")

    _validate_manifest_version(manifest, warnings)


def _validate_manifest_version(manifest: dict, warnings: list[str]) -> None:
    """校验 manifest.json 中版本号字段的格式。

    Args:
        manifest: 解析后的 manifest 字典
        warnings: 警告列表
    """
    version = manifest.get("version", "")
    if version and not _is_valid_semver(version):
        warnings.append(f"manifest.json version 字段不符合语义化版本格式: {version}")

    gaf_version = manifest.get("gaf_version", "")
    if gaf_version and not gaf_version.startswith(">="):
        warnings.append(f"manifest.json gaf_version 建议使用 '>=' 前缀: {gaf_version}")


def _is_valid_semver(version_str: str) -> bool:
    """检查字符串是否符合语义化版本号格式 (x.y.z)。

    Args:
        version_str: 版本号字符串

    Returns:
        是否为合法的语义化版本号
    """
    parts = version_str.split(".")
    if len(parts) != 3:
        return False
    try:
        [int(p) for p in parts]
        return True
    except ValueError:
        return False


def _validate_required_dirs(directory_path: str, errors: list[str]) -> None:
    """校验必需目录是否存在。

    Args:
        directory_path: 资源包目录路径
        errors: 错误列表
    """
    for req_dir in REQUIRED_DIRS:
        dir_path = os.path.join(directory_path, req_dir)
        if not os.path.isdir(dir_path):
            errors.append(f"缺少必需目录: {req_dir}/")


def _validate_optional_dirs(directory_path: str, warnings: list[str]) -> None:
    """校验可选目录，缺失时给出警告。

    Args:
        directory_path: 资源包目录路径
        warnings: 警告列表
    """
    for opt_dir in OPTIONAL_DIRS:
        dir_path = os.path.join(directory_path, opt_dir)
        if not os.path.isdir(dir_path):
            warnings.append(f"缺少可选目录: {opt_dir}/")


def _validate_config_dir(directory_path: str, errors: list[str], warnings: list[str]) -> None:
    """校验 config/ 目录下的配置文件。

    Args:
        directory_path: 资源包目录路径
        errors: 错误列表
        warnings: 警告列表
    """
    config_dir = os.path.join(directory_path, "config")
    if not os.path.isdir(config_dir):
        return

    settings_path = os.path.join(config_dir, "settings.json")
    if os.path.isfile(settings_path):
        try:
            with open(settings_path, encoding="utf-8") as f:
                settings = json.load(f)
            _validate_settings_fields(settings, warnings)
        except json.JSONDecodeError as exc:
            errors.append(f"config/settings.json JSON 解析失败: {exc}")
    else:
        warnings.append("config/ 目录缺少 settings.json")

    rois_path = os.path.join(config_dir, "rois.json")
    if os.path.isfile(rois_path):
        try:
            with open(rois_path, encoding="utf-8") as f:
                rois = json.load(f)
            _validate_rois_format(rois, warnings)
        except json.JSONDecodeError as exc:
            errors.append(f"config/rois.json JSON 解析失败: {exc}")
    else:
        warnings.append("config/ 目录缺少 rois.json")


def _validate_settings_fields(settings: dict, warnings: list[str]) -> None:
    """校验 settings.json 中的配置字段。

    Args:
        settings: 解析后的 settings 字典
        warnings: 警告列表
    """
    recommended_keys = ["base_resolution", "ocr_engine", "screenshot_method_preference"]
    for key in recommended_keys:
        if key not in settings:
            warnings.append(f"config/settings.json 建议包含字段: {key}")

    base_res = settings.get("base_resolution")
    if base_res is not None:
        if not isinstance(base_res, list) or len(base_res) != 2:
            warnings.append("config/settings.json base_resolution 格式应为 [宽, 高]")
        elif not all(isinstance(v, int) for v in base_res):
            warnings.append("config/settings.json base_resolution 值应为整数")


def _validate_rois_format(rois: dict, warnings: list[str]) -> None:
    """校验 rois.json 中 ROI 区域的格式。

    Args:
        rois: 解析后的 rois 字典
        warnings: 警告列表
    """
    for name, value in rois.items():
        if not isinstance(value, list) or len(value) != 4:
            warnings.append(f"config/rois.json ROI '{name}' 格式应为 [x, y, w, h]")
        elif not all(isinstance(v, (int, float)) for v in value):
            warnings.append(f"config/rois.json ROI '{name}' 值应为数字")


def _validate_templates_dir(directory_path: str, warnings: list[str]) -> None:
    """校验 templates/ 目录下的模板图片。

    Args:
        directory_path: 资源包目录路径
        warnings: 警告列表
    """
    templates_dir = os.path.join(directory_path, "templates")
    if not os.path.isdir(templates_dir):
        return

    image_extensions = ('.png', '.jpg', '.jpeg', '.bmp')
    has_images = False
    for _root, _dirs, files in os.walk(templates_dir):
        for f in files:
            if f.lower().endswith(image_extensions):
                has_images = True
                break
        if has_images:
            break

    if not has_images:
        warnings.append("templates/ 目录为空，没有模板图片")


def _validate_tasks_dir(directory_path: str, warnings: list[str]) -> None:
    """校验 tasks/ 目录下的任务定义文件。

    Args:
        directory_path: 资源包目录路径
        warnings: 警告列表
    """
    tasks_dir = os.path.join(directory_path, "tasks")
    if not os.path.isdir(tasks_dir):
        return

    task_extensions = ('.yaml', '.yml', '.json')
    task_files = [
        f for f in os.listdir(tasks_dir)
        if os.path.isfile(os.path.join(tasks_dir, f)) and f.endswith(task_extensions)
    ]
    if not task_files:
        warnings.append("tasks/ 目录为空，没有任务定义文件")


def _validate_monitors_dir(directory_path: str, warnings: list[str]) -> None:
    """校验 monitors/ 目录下的监控规则文件。

    Args:
        directory_path: 资源包目录路径
        warnings: 警告列表
    """
    monitors_dir = os.path.join(directory_path, "monitors")
    if not os.path.isdir(monitors_dir):
        return

    monitor_extensions = ('.yaml', '.yml')
    monitor_files = [
        f for f in os.listdir(monitors_dir)
        if os.path.isfile(os.path.join(monitors_dir, f)) and f.endswith(monitor_extensions)
    ]
    if not monitor_files:
        warnings.append("monitors/ 目录为空，没有监控规则文件")


def validate_version_compatibility(pack_version: str) -> dict[str, Any]:
    """校验资源包版本兼容性。

    Args:
        pack_version: 资源包声明的 GAF 版本兼容性

    Returns:
        校验结果 {"compatible", "current_version", "pack_version"}
    """
    try:
        current_parts = [int(x) for x in GAF_VERSION.split(".")]
        clean_version = pack_version.lstrip(">=")
        pack_parts = [int(x) for x in clean_version.split(".")]
        compatible = current_parts[0] == pack_parts[0]
    except (ValueError, IndexError):
        compatible = False

    return {
        "compatible": compatible,
        "current_version": GAF_VERSION,
        "pack_version": pack_version,
    }


def validate_resource_pack(pack: ResourcePack) -> dict[str, Any]:
    """对资源包执行完整校验。

    Args:
        pack: ResourcePack 模型实例

    Returns:
        完整校验结果
    """
    structure_result = validate_resource_pack_structure(pack.directory_path)

    version_result = {"compatible": True, "current_version": GAF_VERSION, "pack_version": ""}
    if pack.gaf_version_compat:
        version_result = validate_version_compatibility(pack.gaf_version_compat)

    all_valid = structure_result["valid"] and version_result["compatible"]

    return {
        "valid": all_valid,
        "structure": structure_result,
        "version": version_result,
    }
