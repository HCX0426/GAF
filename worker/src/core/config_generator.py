"""Config generator: convert task definitions to form schemas for GUI auto-generation.

Provides schema-based form generation following Alas's YAML→GUI approach.
Generates field definitions that frontend components can render dynamically,
with validation rules, default values, and type information.

Reference: Alas's config_generated.py + task/argument/override → args.json pattern.
"""

import copy
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ConfigGenerator:
    """Generate form schemas from task type definitions.

    Converts structured task configuration into UI-renderable form field lists.
    Each field carries metadata (type, label, validation, options) so the
    frontend can auto-generate appropriate input components.
    """

    FIELD_TYPE_STRING = "string"
    FIELD_TYPE_INTEGER = "integer"
    FIELD_TYPE_FLOAT = "float"
    FIELD_TYPE_BOOLEAN = "boolean"
    FIELD_TYPE_SELECT = "select"
    FIELD_TYPE_MULTISELECT = "multiselect"
    FIELD_TYPE_TEXT = "text"
    FIELD_TYPE_JSON = "json"
    FIELD_TYPE_FILEPATH = "filepath"
    FIELD_TYPE_COLOR = "color"

    VALID_FIELD_TYPES = {
        FIELD_TYPE_STRING, FIELD_TYPE_INTEGER, FIELD_TYPE_FLOAT,
        FIELD_TYPE_BOOLEAN, FIELD_TYPE_SELECT, FIELD_TYPE_MULTISELECT,
        FIELD_TYPE_TEXT, FIELD_TYPE_JSON, FIELD_TYPE_FILEPATH, FIELD_TYPE_COLOR,
    }

    def __init__(self):
        self._schemas: dict[str, dict[str, Any]] = {}
        self._version = 1

    def generate_form_schema(self, task_type: str) -> dict[str, Any]:
        """Generate a complete form schema for a given task type

        Args:
            task_type: Task identifier (e.g., "pipeline", "scheduler", "device_config")

        Returns:
            Form schema dict with fields list, version, and metadata
        """
        if task_type in self._schemas:
            return copy.deepcopy(self._schemas[task_type])

        schema = self._build_schema_template(task_type)
        self._schemas[task_type] = schema
        return copy.deepcopy(schema)

    def _build_schema_template(self, task_type: str) -> dict[str, Any]:
        """Build schema from built-in templates or custom definition

        Args:
            task_type: Task type identifier

        Returns:
            Schema dictionary with fields, version, metadata
        """
        template_builders = {
            "pipeline": self._build_pipeline_schema,
            "scheduler": self._build_scheduler_schema,
            "device_config": self._build_device_schema,
            "ocr_task": self._build_ocr_schema,
            "general": self._build_general_schema,
        }

        builder = template_builders.get(task_type, self._build_general_schema)
        fields = builder()

        return {
            "version": self._version,
            "task_type": task_type,
            "fields": fields,
            "metadata": {
                "field_count": len(fields),
                "required_count": sum(1 for f in fields if f.get("required", False)),
                "generated_at": None,
            },
        }

    def schema_to_fields(self, schema: dict[str, Any]) -> list[dict[str, Any]]:
        """Convert schema to flat field list for frontend rendering

        Args:
            schema: Full schema dict from generate_form_schema()

        Returns:
            List of field dicts with all rendering metadata
        """
        fields = schema.get("fields", [])
        result = []
        for idx, field in enumerate(fields):
            entry = {
                "key": field.get("name", f"field_{idx}"),
                "label": field.get("label", field.get("name", "")),
                "type": field.get("type", self.FIELD_TYPE_STRING),
                "default_value": field.get("default"),
                "required": field.get("required", False),
                "options": field.get("options", []),
                "placeholder": field.get("placeholder", ""),
                "help_text": field.get("help_text", ""),
                "validation": field.get("validation", {}),
                "group": field.get("group", "default"),
                "visible": field.get("visible", True),
                "disabled": field.get("disabled", False),
                "order": idx,
            }
            result.append(entry)
        return result

    def validate_values(
        self, values: dict[str, Any], schema: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        """Validate user-submitted values against schema rules

        Args:
            values: User-submitted key-value pairs
            schema: Form schema with validation rules

        Returns:
            (is_valid, error_messages) tuple
        """
        errors = []
        fields = schema.get("fields", [])

        for field in fields:
            name = field.get("name")
            if not name:
                continue

            value = values.get(name)
            required = field.get("required", False)
            field_type = field.get("type", self.FIELD_TYPE_STRING)

            # Required check
            if required and (value is None or value == ""):
                errors.append(f"{field.get('label', name)} is required")
                continue

            # Type check
            if value is not None and value != "":
                type_error = self._validate_type(name, value, field_type)
                if type_error:
                    errors.append(type_error)
                    continue

            # Custom validation rules
            validation = field.get("validation", {})
            if validation:
                rule_errors = self._apply_validation_rules(value, name, validation)
                errors.extend(rule_errors)

        is_valid = len(errors) == 0
        return is_valid, errors

    def export_config(
        self, values: dict[str, Any], task_type: str
    ) -> dict[str, Any]:
        """Export validated values as structured configuration dict

        Args:
            values: Validated field values
            task_type: Task type for schema lookup

        Returns:
            Structured configuration dictionary
        """
        schema = self.generate_form_schema(task_type)
        config = {
            "__schema_version__": schema["version"],
            "__task_type__": task_type,
            "__generated__": True,
        }

        for field in schema["fields"]:
            name = field.get("name")
            if name in values:
                config[name] = values[name]
            elif "default" in field:
                config[name] = field["default"]

        return config

    def import_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Import configuration dict and fill default values

        Args:
            config: Configuration dictionary (may be partial)

        Returns:
            Complete values dict with defaults filled
        """
        task_type = config.get("__task_type__", "general")
        schema = self.generate_form_schema(task_type)
        values = {}

        for field in schema["fields"]:
            name = field.get("name")
            if name in config:
                values[name] = config[name]
            elif "default" in field:
                values[name] = field["default"]

        return values

    def register_custom_schema(
        self, task_type: str, fields: list[dict[str, Any]]
    ) -> None:
        """Register a custom form schema for a task type

        Args:
            task_type: Unique task type identifier
            fields: List of field definition dicts
        """
        self._schemas[task_type] = {
            "version": self._version,
            "task_type": task_type,
            "fields": fields,
            "metadata": {
                "field_count": len(fields),
                "required_count": sum(1 for f in fields if f.get("required", False)),
                "custom": True,
            },
        }
        logger.info("Registered custom schema: %s (%d fields)", task_type, len(fields))

    # ── Schema template builders ──────────────────────────────────────

    @staticmethod
    def _build_pipeline_schema() -> list[dict[str, Any]]:
        """Build pipeline task form schema"""
        return [
            {"name": "name", "type": "string", "label": "Task Name",
             "required": True, "placeholder": "Enter task name",
             "validation": {"min_length": 1, "max_length": 100}},
            {"name": "description", "type": "text", "label": "Description",
             "required": False, "placeholder": "Task description"},
            {"name": "mode", "type": "select", "label": "Execution Mode",
             "required": True, "options": [
                 {"value": "once", "label": "Run Once"},
                 {"value": "loop", "label": "Loop"},
                 {"value": "conditional", "label": "Conditional"},
             ], "default": "once"},
            {"name": "max_retries", "type": "integer", "label": "Max Retries",
             "required": False, "default": 3,
             "validation": {"min": 0, "max": 100}},
            {"name": "retry_delay_ms", "type": "integer", "label": "Retry Delay (ms)",
             "required": False, "default": 1000,
             "validation": {"min": 100, "max": 60000}},
            {"name": "timeout_seconds", "type": "integer", "label": "Timeout (s)",
             "required": False, "default": 300,
             "validation": {"min": 1, "max": 86400}},
            {"name": "enabled", "type": "boolean", "label": "Enabled",
             "required": False, "default": True},
            {"name": "tags", "type": "text", "label": "Tags",
             "required": False, "placeholder": "comma-separated tags"},
        ]

    @staticmethod
    def _build_scheduler_schema() -> list[dict[str, Any]]:
        """Build scheduler/cron form schema"""
        return [
            {"name": "cron_expression", "type": "string", "label": "Cron Expression",
             "required": True, "placeholder": "*/5 * * * *",
             "help_text": "Standard 5-field cron expression"},
            {"name": "timezone", "type": "select", "label": "Timezone",
             "required": True, "options": [
                 {"value": "UTC", "label": "UTC"},
                 {"value": "Asia/Shanghai", "label": "China Standard Time"},
                 {"value": "America/New_York", "label": "Eastern Time"},
                 {"value": "Europe/London", "label": "GMT"},
             ], "default": "Asia/Shanghai"},
            {"name": "start_date", "type": "string", "label": "Start Date",
             "required": False, "placeholder": "YYYY-MM-DD"},
            {"name": "end_date", "type": "string", "label": "End Date",
             "required": False, "placeholder": "YYYY-MM-DD"},
            {"name": "concurrent_limit", "type": "integer", "label": "Concurrent Limit",
             "required": False, "default": 1,
             "validation": {"min": 1, "max": 10}},
            {"name": "misfire_policy", "type": "select", "label": "Misfire Policy",
             "required": False, "options": [
                 {"value": "immediate", "label": "Run Immediately"},
                 {"value": "skip", "label": "Skip Missed"},
                 {"value": "catch_up", "label": "Catch Up"},
             ], "default": "immediate"},
            {"name": "enabled", "type": "boolean", "label": "Enabled",
             "required": False, "default": True},
        ]

    @staticmethod
    def _build_device_schema() -> list[dict[str, Any]]:
        """Build device configuration form schema"""
        return [
            {"name": "device_name", "type": "string", "label": "Device Name",
             "required": True},
            {"name": "device_type", "type": "select", "label": "Device Type",
             "required": True, "options": [
                 {"value": "windows", "label": "Windows Window"},
                 {"value": "emulator", "label": "Android Emulator"},
                 {"value": "adb", "label": "ADB Device"},
             ]},
            {"name": "screenshot_method", "type": "select", "label": "Screenshot Method",
             "required": False, "options": [
                 {"value": "auto", "label": "Auto Detect"},
                 {"value": "wgc", "label": "WGC"},
                 {"value": "dxgi", "label": "DXGI"},
                 {"value": "gdi", "label": "GDI BitBlt"},
                 {"value": "printwindow", "label": "PrintWindow"},
             ], "default": "auto"},
            {"name": "input_method", "type": "select", "label": "Input Method",
             "required": False, "options": [
                 {"value": "sendinput", "label": "SendInput (Foreground)"},
                 {"value": "postmessage", "label": "PostMessage (Background)"},
                 {"value": "sendmessage", "label": "SendMessage"},
             ], "default": "sendinput"},
            {"name": "background_mode", "type": "boolean", "label": "Background Mode",
             "required": False, "default": False},
            {"name": "window_title", "type": "string", "label": "Target Window Title",
             "required": False, "placeholder": "Leave empty for desktop"},
            {"name": "use_dc_cache", "type": "boolean", "label": "Enable DC Cache",
             "required": False, "default": True},
        ]

    @staticmethod
    def _build_ocr_schema() -> list[dict[str, Any]]:
        """Build OCR task form schema"""
        return [
            {"name": "engine", "type": "select", "label": "OCR Engine",
             "required": True, "options": [
                 {"value": "rapidocr", "label": "RapidOCR"},
                 {"value": "paddleocr", "label": "PaddleOCR"},
                 {"value": "auto", "label": "Auto Select"},
             ], "default": "rapidocr"},
            {"name": "language", "type": "select", "label": "Recognition Language",
             "required": False, "options": [
                 {"value": "ch", "label": "Chinese Simplified"},
                 {"value": "ch_trad", "label": "Chinese Traditional"},
                 {"value": "en", "label": "English"},
                 {"value": "jp", "label": "Japanese"},
                 {"value": "kr", "label": "Korean"},
             ], "default": "ch"},
            {"name": "confidence_threshold", "type": "float", "label": "Confidence Threshold",
             "required": False, "default": 0.8,
             "validation": {"min": 0.0, "max": 1.0}},
            {"name": "use_gpu", "type": "boolean", "label": "Use GPU Acceleration",
             "required": False, "default": True},
            {"name": "det_model_dir", "type": "filepath", "label": "Detection Model Path",
             "required": False, "placeholder": "Path to detection model"},
            {"name": "rec_model_dir", "type": "filepath", "label": "Recognition Model Path",
             "required": False, "placeholder": "Path to recognition model"},
            {"name": "enable_opencc", "type": "boolean", "label": "Enable OpenCC Conversion",
             "required": False, "default": False},
        ]

    @staticmethod
    def _build_general_schema() -> list[dict[str, Any]]:
        """Build generic fallback form schema"""
        return []

    # ── Validation helpers ───────────────────────────────────────────

    @staticmethod
    def _validate_type(name: str, value: Any, field_type: str) -> str | None:
        """Validate value matches expected type

        Args:
            name: Field name (for error message)
            value: Value to validate
            field_type: Expected type string

        Returns:
            Error message string, or None if valid
        """
        try:
            if field_type == "integer":
                int(value)
            elif field_type == "float":
                float(value)
            elif field_type == "boolean":
                if isinstance(value, str) and value.lower() not in ("true", "false", "1", "0", ""):
                    return f"{name} must be true/false or 1/0"
            elif field_type == "json":
                json.loads(value) if isinstance(value, str) else None
            elif field_type == "color" and isinstance(value, str) and not value.startswith("#"):
                return f"{name} must be a hex color (#RRGGBB)"
            return None
        except (ValueError, TypeError, json.JSONDecodeError):
            return f"{name} must be of type {field_type}"

    @staticmethod
    def _apply_validation_rules(
        value: Any, name: str, rules: dict[str, Any]
    ) -> list[str]:
        """Apply custom validation rules to a field value

        Args:
            value: Field value
            name: Field name
            rules: Validation rule dict

        Returns:
            List of error messages (empty if all pass)
        """
        errors = []
        min_val = rules.get("min_length") or rules.get("min")
        max_val = rules.get("max_length") or rules.get("max")

        if min_val is not None and value is not None:
            try:
                if len(str(value)) < int(min_val):
                    errors.append(f"{name} minimum length is {min_val}")
            except (TypeError, ValueError):
                pass

        if max_val is not None and value is not None:
            try:
                if len(str(value)) > int(max_val):
                    errors.append(f"{name} maximum length is {max_val}")
            except (TypeError, ValueError):
                pass

        pattern = rules.get("regex")
        if pattern and value is not None:
            import re
            if not re.match(pattern, str(value)):
                errors.append(f"{name} does not match required format")

        return errors
