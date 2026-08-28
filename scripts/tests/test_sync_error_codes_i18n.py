"""test_sync_error_codes_i18n.py — Unit tests for ErrorCode ↔ frontend i18n sync.

Covers the main behaviors of scripts/bootstrap/sync_error_codes_i18n.py:

1. test_parse_enum_file_extracts_members_with_comments — AST + 行内注释提取
2. test_build_expected_keys_combines_int_and_str_enums — ErrorCode 数字 + NodeErrorCode 字符串 key
3. test_scan_frontend_i18n_extracts_keys_per_locale — common.ts 每个 locale 段独立扫描
4. test_build_report_detects_missing_and_extra_keys — 缺失 / 多余 key 分类正确
5. test_update_appends_missing_keys_preserves_existing — --update 自动补全不破坏人工翻译

Run with: `conda run -n gaf python -m pytest scripts/tests/test_sync_error_codes_i18n.py -q`
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

pytestmark = pytest.mark.unit


def _load_module():
    """Load sync_error_codes_i18n.py as an isolated module (avoid import side effects).

    Note: 必须 register 到 sys.modules, 否则 @dataclass (with `from __future__ import annotations`)
    解析字符串注解时会调 sys.modules.get(cls.__module__).__dict__ 导致 NoneType 报错.
    """
    mod_path = SCRIPTS_DIR / "bootstrap" / "sync_error_codes_i18n.py"
    mod_name = "_sync_error_codes_i18n_test"
    spec = importlib.util.spec_from_file_location(mod_name, mod_path)
    assert spec and spec.loader, "failed to load spec"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod  # 关键: register 后 @dataclass 才能解析字符串注解
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(mod_name, None)
        raise
    return mod


_BACKEND_FIXTURE = '''"""Test fixture: backend error codes."""
from enum import IntEnum, StrEnum


class ErrorCode(IntEnum):
    SUCCESS = 0
    INVALID_PARAMS = 1001  # 请求参数不合法, 请检查输入
    NEW_CODE = 9999  # 新增的测试码


class NodeErrorCode(StrEnum):
    NO_MATCH = "NO_MATCH"  # 模板/特征匹配未找到
    NEW_NODE = "NEW_NODE"  # 新增的节点错误码
'''


_AGENT_FIXTURE = '''"""Test fixture: agent error codes."""
from enum import StrEnum


class NodeErrorCode(StrEnum):
    NO_MATCH = "NO_MATCH"  # 模板/特征匹配未找到
    NEW_NODE = "NEW_NODE"  # 新增的节点错误码
'''


_FRONTEND_FIXTURE = """import type { LocaleMessages } from '@/i18n/types';

export const common: LocaleMessages = {
  'zh-CN': {
    'common.save': '保存',
    'error.codes.0': '操作成功',
    'error.codes.1001': '请求参数不合法, 请检查输入',
    'error.codes.NO_MATCH': '未找到匹配',
  },
  'en-US': {
    'common.save': 'Save',
    'error.codes.0': 'Operation successful',
    'error.codes.1001': 'Invalid request parameters, please check input',
    'error.codes.NO_MATCH': 'No match found',
  },
  'ja-JP': {
    'common.save': '保存',
    'error.codes.0': '操作成功',
    'error.codes.1001': 'リクエストパラメータが不正です',
    'error.codes.NO_MATCH': 'マッチが見つかりません',
  },
  'ko-KR': {
    'common.save': '저장',
    'error.codes.0': '작업 성공',
    'error.codes.1001': '요청 파라미터가 올바르지 않습니다',
    'error.codes.NO_MATCH': '일치하는 항목을 찾을 수 없습니다',
  },
};
"""


def test_parse_enum_file_extracts_members_with_comments(tmp_path):
    mod = _load_module()
    fixture = tmp_path / "error_codes.py"
    fixture.write_text(_BACKEND_FIXTURE, encoding="utf-8")

    members = mod._parse_enum_file(fixture, "backend")
    # ErrorCode 3 members + NodeErrorCode 2 members = 5
    assert len(members) == 5
    by_name = {m.name: m for m in members}
    # IntEnum value 转 str
    assert by_name["INVALID_PARAMS"].value == "1001"
    assert by_name["INVALID_PARAMS"].enum_class == "ErrorCode"
    # 注释提取
    assert "请求参数不合法" in by_name["INVALID_PARAMS"].comment
    # NodeErrorCode
    assert by_name["NO_MATCH"].value == "NO_MATCH"
    assert by_name["NO_MATCH"].enum_class == "NodeErrorCode"
    assert "模板" in by_name["NO_MATCH"].comment


def test_build_expected_keys_combines_int_and_str_enums():
    mod = _load_module()
    backend = mod._parse_enum_file.__wrapped__ if hasattr(mod._parse_enum_file, "__wrapped__") else None
    # 直接构造 EnumMember 列表测试逻辑
    from dataclasses import dataclass
    members = [
        mod.EnumMember(name="SUCCESS", value="0", comment="", enum_class="ErrorCode", source_file="backend"),
        mod.EnumMember(name="INVALID_PARAMS", value="1001", comment="", enum_class="ErrorCode", source_file="backend"),
        mod.EnumMember(name="NO_MATCH", value="NO_MATCH", comment="", enum_class="NodeErrorCode", source_file="backend"),
        mod.EnumMember(name="NO_MATCH", value="NO_MATCH", comment="", enum_class="NodeErrorCode", source_file="agent"),
    ]
    expected = mod.build_expected_keys(members[:3], members[3:])
    assert expected == {"error.codes.0", "error.codes.1001", "error.codes.NO_MATCH"}


def test_scan_frontend_i18n_extracts_keys_per_locale(tmp_path, monkeypatch):
    mod = _load_module()
    fixture = tmp_path / "common.ts"
    fixture.write_text(_FRONTEND_FIXTURE, encoding="utf-8")
    monkeypatch.setattr(mod, "FRONTEND_COMMON_TS", fixture)

    result = mod.scan_frontend_i18n()
    for loc in ("zh-CN", "en-US", "ja-JP", "ko-KR"):
        assert result[loc] == {
            "error.codes.0",
            "error.codes.1001",
            "error.codes.NO_MATCH",
        }, f"locale {loc} mismatch"


def test_build_report_detects_missing_and_extra_keys(tmp_path, monkeypatch):
    mod = _load_module()
    backend_fixture = tmp_path / "backend_err.py"
    backend_fixture.write_text(_BACKEND_FIXTURE, encoding="utf-8")
    agent_fixture = tmp_path / "agent_err.py"
    agent_fixture.write_text(_AGENT_FIXTURE, encoding="utf-8")
    frontend_fixture = tmp_path / "common.ts"
    frontend_fixture.write_text(_FRONTEND_FIXTURE, encoding="utf-8")

    monkeypatch.setattr(mod, "BACKEND_ERROR_CODES", backend_fixture)
    monkeypatch.setattr(mod, "AGENT_ERROR_CODES", agent_fixture)
    monkeypatch.setattr(mod, "FRONTEND_COMMON_TS", frontend_fixture)

    report = mod.build_report()
    # expected = {0, 1001, 9999, NO_MATCH, NEW_NODE} = 5 keys
    assert len(report.expected_keys) == 5
    # frontend has {0, 1001, NO_MATCH} = 3 keys
    for loc in ("zh-CN", "en-US", "ja-JP", "ko-KR"):
        assert set(report.missing[loc]) == {"error.codes.9999", "error.codes.NEW_NODE"}, \
            f"locale {loc} missing mismatch: {report.missing[loc]}"
        assert report.extra[loc] == [], f"locale {loc} should have no extra key"
    assert report.has_diff() is True


def test_update_appends_missing_keys_preserves_existing(tmp_path, monkeypatch):
    mod = _load_module()
    backend_fixture = tmp_path / "backend_err.py"
    backend_fixture.write_text(_BACKEND_FIXTURE, encoding="utf-8")
    agent_fixture = tmp_path / "agent_err.py"
    agent_fixture.write_text(_AGENT_FIXTURE, encoding="utf-8")
    frontend_fixture = tmp_path / "common.ts"
    frontend_fixture.write_text(_FRONTEND_FIXTURE, encoding="utf-8")

    monkeypatch.setattr(mod, "BACKEND_ERROR_CODES", backend_fixture)
    monkeypatch.setattr(mod, "AGENT_ERROR_CODES", agent_fixture)
    monkeypatch.setattr(mod, "FRONTEND_COMMON_TS", frontend_fixture)

    report = mod.build_report()
    updated = mod.update_frontend_i18n(report)
    assert updated is True

    # 重新扫描确认 missing 已补齐
    new_report = mod.build_report()
    assert not new_report.has_diff(), "after update, no diff expected"

    # 验证已有人工翻译被保留 (不破坏)
    new_src = frontend_fixture.read_text(encoding="utf-8")
    assert "请求参数不合法, 请检查输入" in new_src  # zh-CN 原翻译保留
    assert "Invalid request parameters" in new_src  # en-US 原翻译保留
    assert "リクエストパラメータが不正です" in new_src  # ja-JP 原翻译保留
    assert "요청 파라미터가 올바르지 않습니다" in new_src  # ko-KR 原翻译保留

    # 验证新增的 key 用了源码注释作为 zh-CN 文案
    assert "新增的测试码" in new_src  # error.codes.9999 zh-CN
    assert "新增的节点错误码" in new_src  # error.codes.NEW_NODE zh-CN
    # en-US 用 enum name Title Case
    assert "New Code" in new_src  # error.codes.9999 en-US
    assert "New Node" in new_src  # error.codes.NEW_NODE en-US
    # ja-JP / ko-KR 用 <TODO> 占位
    assert "<TODO: translate> NEW_NODE" in new_src
