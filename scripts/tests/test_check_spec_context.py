"""test_check_spec_context.py — Tests for check_spec_context.py (TD-342, spec-2026-07-26-meta-governance-fix T3).

Covers:
1. test_find_active_spec_name_from_evidence  — B2 evidence spec_id 提取
2. test_find_active_spec_name_from_active_dir — fallback 到 active specs dir
3. test_spec_context_exists_exact             — 精确匹配 <spec-name>-context.md
4. test_spec_context_exists_no_suffix         — 无 -context 后缀匹配
5. test_spec_context_exists_not_found         — 文件不存在
6. test_main_small_change_noop                — 小修改 noop
7. test_main_big_change_with_spec_context     — 大修改 + spec-context 存在 + N173 字段完整 → pass
8. test_main_big_change_with_spec_context_n173_missing — N173 字段缺失 → exit 1
9. test_check_n173_timing_fields_section      — "## N173 用时字段" 段解析
10. test_check_n173_timing_fields_frontmatter — frontmatter 解析
11. test_check_n173_placeholder_detection      — 占位符识别
12. test_check_n173_root_cause_required_when_over_baseline — within_baseline=false 时 root_cause 必填

Run with:
    conda run -n gaf python -m pytest scripts/tests/test_check_spec_context.py -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

pytestmark = pytest.mark.unit

from hooks import check_spec_context  # type: ignore


class TestCheckSpecContext(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.spec_context_dir = self.tmp_path / "spec-context"
        self.spec_context_dir.mkdir()
        self.active_specs_dir = self.tmp_path / "active"
        self.active_specs_dir.mkdir()

        # Patch module-level paths
        self._orig_spec_context_dir = check_spec_context.SPEC_CONTEXT_DIR
        self._orig_active_specs_dir = check_spec_context.ACTIVE_SPECS_DIR
        check_spec_context.SPEC_CONTEXT_DIR = self.spec_context_dir
        check_spec_context.ACTIVE_SPECS_DIR = self.active_specs_dir

    def tearDown(self) -> None:
        check_spec_context.SPEC_CONTEXT_DIR = self._orig_spec_context_dir
        check_spec_context.ACTIVE_SPECS_DIR = self._orig_active_specs_dir
        self.tmp.cleanup()

    def test_find_active_spec_name_from_evidence(self) -> None:
        """B2 evidence spec_id 提取 spec name."""
        mock_evidence = {"spec_id": "spec-2026-07-26-td341-ref-docs-merge"}
        with patch.object(check_spec_context, "read_b2_evidence", return_value=mock_evidence):
            spec_name = check_spec_context.find_active_spec_name()
        self.assertEqual(spec_name, "2026-07-26-td341-ref-docs-merge")

    def test_find_active_spec_name_from_active_dir(self) -> None:
        """无 B2 evidence 时, fallback 到 active specs dir (最新 mtime)."""
        # 创建两个 spec 文件, 一个较新
        old_spec = self.active_specs_dir / "2026-07-25-old-spec.md"
        new_spec = self.active_specs_dir / "2026-07-26-new-spec.md"
        old_spec.write_text("old", encoding="utf-8")
        # 设置 mtime: new_spec 较新
        import time
        new_spec.write_text("new", encoding="utf-8")
        os.utime(old_spec, (time.time() - 100, time.time() - 100))
        os.utime(new_spec, (time.time(), time.time()))

        with patch.object(check_spec_context, "read_b2_evidence", return_value=None):
            spec_name = check_spec_context.find_active_spec_name()
        self.assertEqual(spec_name, "2026-07-26-new-spec")

    def test_spec_context_exists_exact(self) -> None:
        """精确匹配 <spec-name>-context.md."""
        context_file = self.spec_context_dir / "2026-07-26-test-context.md"
        context_file.write_text("content", encoding="utf-8")

        self.assertTrue(check_spec_context.spec_context_exists("2026-07-26-test"))

    def test_spec_context_exists_no_suffix(self) -> None:
        """无 -context 后缀匹配 (兼容命名)."""
        context_file = self.spec_context_dir / "2026-07-26-test.md"
        context_file.write_text("content", encoding="utf-8")

        self.assertTrue(check_spec_context.spec_context_exists("2026-07-26-test"))

    def test_spec_context_exists_not_found(self) -> None:
        """文件不存在."""
        self.assertFalse(check_spec_context.spec_context_exists("nonexistent-spec"))
        self.assertFalse(check_spec_context.spec_context_exists(None))

    def test_main_small_change_noop(self) -> None:
        """小修改 (is_big=False) → noop, exit 0."""
        mock_result = {"is_big": False, "reasons": []}
        with patch.object(check_spec_context, "check_big_change_staged", return_value=mock_result):
            rc = check_spec_context.main([])
        self.assertEqual(rc, 0)

    def test_main_big_change_with_spec_context(self) -> None:
        """大修改 (is_big=True) + B2 valid + spec-context 存在 + N173 字段完整 → exit 0."""
        mock_result = {"is_big": True, "reasons": ["files_changed >= 10"]}
        mock_evidence = {"spec_id": "spec-2026-07-26-test-spec"}
        # 创建 spec-context 文件 — 含完整 N173 用时字段
        context_file = self.spec_context_dir / "2026-07-26-test-spec-context.md"
        context_file.write_text(
            "---\n"
            "spec_id: spec-2026-07-26-test-spec\n"
            "---\n"
            "\n"
            "## 7. N173 用时字段\n"
            "\n"
            "- `start_ts`: 2026-07-26T10:00:00+08:00\n"
            "- `end_ts`: 2026-07-26T10:30:00+08:00\n"
            "- `duration_min`: 30\n"
            "- `within_baseline`: true\n"
            "- `root_cause_if_over`: -\n",
            encoding="utf-8",
        )

        with patch.object(check_spec_context, "check_big_change_staged", return_value=mock_result), \
             patch.object(check_spec_context, "read_b2_evidence", return_value=mock_evidence), \
             patch.object(check_spec_context, "is_b2_evidence_valid", return_value=(True, None)):
            rc = check_spec_context.main([])
        self.assertEqual(rc, 0)

    def test_main_big_change_no_active_spec_skips(self) -> None:
        """大修改 + B2 valid + 无活跃 spec (active/ 为空, 归档/清理 commit) → exit 0."""
        mock_result = {"is_big": True, "reasons": ["files_changed >= 10"]}
        mock_evidence = {"spec_id": "spec-2026-07-26-test-spec"}
        with patch.object(check_spec_context, "check_big_change_staged", return_value=mock_result), \
             patch.object(check_spec_context, "read_b2_evidence", return_value=mock_evidence), \
             patch.object(check_spec_context, "is_b2_evidence_valid", return_value=(True, None)), \
             patch.object(check_spec_context, "find_active_spec_name", return_value=None):
            rc = check_spec_context.main([])
        self.assertEqual(rc, 0)

    def test_main_big_change_with_spec_context_n173_missing(self) -> None:
        """大修改 + spec-context 存在但 N173 字段缺失 → exit 1 (Wave 1 强化)."""
        mock_result = {"is_big": True, "reasons": ["files_changed >= 10"]}
        mock_evidence = {"spec_id": "spec-2026-07-26-test-spec"}
        # spec-context 存在但无 N173 字段
        context_file = self.spec_context_dir / "2026-07-26-test-spec-context.md"
        context_file.write_text(
            "---\nspec_id: spec-2026-07-26-test-spec\n---\n\n# spec-context (no N173 fields)",
            encoding="utf-8",
        )

        with patch.object(check_spec_context, "check_big_change_staged", return_value=mock_result), \
             patch.object(check_spec_context, "read_b2_evidence", return_value=mock_evidence), \
             patch.object(check_spec_context, "is_b2_evidence_valid", return_value=(True, None)):
            rc = check_spec_context.main([])
        self.assertEqual(rc, 1)

    def test_check_n173_timing_fields_section(self) -> None:
        """N173 字段从 '## N173 用时字段' 段解析 (支持 ## 7. N173 序号形式)."""
        context_file = self.spec_context_dir / "test-section-context.md"
        context_file.write_text(
            "# spec-context\n\n"
            "## 7. N173 用时字段 (本 spec 自应用)\n\n"
            "- `start_ts`: 2026-07-26T10:00:00+08:00\n"
            "- `end_ts`: 2026-07-26T10:30:00+08:00\n"
            "- `duration_min`: 30\n"
            "- `within_baseline`: true\n"
            "- `root_cause_if_over`: -\n",
            encoding="utf-8",
        )
        ok, missing = check_spec_context.check_n173_timing_fields(context_file)
        self.assertTrue(ok, f"应通过, missing={missing}")
        self.assertEqual(missing, [])

    def test_check_n173_timing_fields_frontmatter(self) -> None:
        """N173 字段从 frontmatter 解析 (优先解析)."""
        context_file = self.spec_context_dir / "test-frontmatter-context.md"
        context_file.write_text(
            "---\n"
            "spec_id: spec-test\n"
            "start_ts: 2026-07-26T10:00:00+08:00\n"
            "end_ts: 2026-07-26T10:30:00+08:00\n"
            "duration_min: 30\n"
            "within_baseline: true\n"
            "root_cause_if_over: -\n"
            "---\n\n# spec-context\n",
            encoding="utf-8",
        )
        ok, missing = check_spec_context.check_n173_timing_fields(context_file)
        self.assertTrue(ok, f"应通过, missing={missing}")

    def test_check_n173_placeholder_detection(self) -> None:
        """占位符识别 — (待填写) / TBD / <fill> 等视为未填."""
        context_file = self.spec_context_dir / "test-placeholder-context.md"
        context_file.write_text(
            "## N173 用时字段\n\n"
            "- `start_ts`: 2026-07-26T10:00:00+08:00\n"
            "- `end_ts`: (Wave 3 完成后填写)\n"
            "- `duration_min`: (计算后填写)\n"
            "- `within_baseline`: (对照基线)\n",
            encoding="utf-8",
        )
        ok, missing = check_spec_context.check_n173_timing_fields(context_file)
        self.assertFalse(ok)
        self.assertIn("end_ts", missing)
        self.assertIn("duration_min", missing)
        self.assertIn("within_baseline", missing)
        # start_ts 已填, 不在 missing
        self.assertNotIn("start_ts", missing)

    def test_check_n173_root_cause_required_when_over_baseline(self) -> None:
        """within_baseline=false 时 root_cause_if_over 必填."""
        context_file = self.spec_context_dir / "test-over-baseline-context.md"
        context_file.write_text(
            "## N173 用时字段\n\n"
            "- `start_ts`: 2026-07-26T10:00:00+08:00\n"
            "- `end_ts`: 2026-07-26T11:30:00+08:00\n"
            "- `duration_min`: 90\n"
            "- `within_baseline`: false\n"
            "- `root_cause_if_over`: N173 根因 #2 commit 重试\n",
            encoding="utf-8",
        )
        ok, missing = check_spec_context.check_n173_timing_fields(context_file)
        self.assertTrue(ok, f"超基线但有根因应通过, missing={missing}")

        # 超基线但 root_cause_if_over 占位符 → 失败
        context_file.write_text(
            "## N173 用时字段\n\n"
            "- `start_ts`: 2026-07-26T10:00:00+08:00\n"
            "- `end_ts`: 2026-07-26T11:30:00+08:00\n"
            "- `duration_min`: 90\n"
            "- `within_baseline`: false\n"
            "- `root_cause_if_over`: (超基线时填)\n",
            encoding="utf-8",
        )
        ok, missing = check_spec_context.check_n173_timing_fields(context_file)
        self.assertFalse(ok)
        self.assertTrue(any("root_cause_if_over" in m for m in missing))

    def test_main_big_change_without_spec_context(self) -> None:
        """大修改 (is_big=True) + B2 valid + spec-context 缺失 → exit 1."""
        mock_result = {"is_big": True, "reasons": ["files_changed >= 10"]}
        mock_evidence = {"spec_id": "spec-2026-07-26-missing-spec"}

        with patch.object(check_spec_context, "check_big_change_staged", return_value=mock_result), \
             patch.object(check_spec_context, "read_b2_evidence", return_value=mock_evidence), \
             patch.object(check_spec_context, "is_b2_evidence_valid", return_value=(True, None)):
            rc = check_spec_context.main([])
        self.assertEqual(rc, 1)

    def test_main_big_change_invalid_b2_noop(self) -> None:
        """大修改 + B2 invalid → noop (check_big_change_hook.py 已阻塞)."""
        mock_result = {"is_big": True, "reasons": ["files_changed >= 10"]}
        mock_evidence = {"spec_id": "spec-2026-07-26-test"}

        with patch.object(check_spec_context, "check_big_change_staged", return_value=mock_result), \
             patch.object(check_spec_context, "read_b2_evidence", return_value=mock_evidence), \
             patch.object(check_spec_context, "is_b2_evidence_valid", return_value=(False, "expired")):
            rc = check_spec_context.main([])
        self.assertEqual(rc, 0)

    def test_main_no_fail_mode(self) -> None:
        """--no-fail 模式: spec-context 缺失也 exit 0."""
        mock_result = {"is_big": True, "reasons": ["files_changed >= 10"]}
        mock_evidence = {"spec_id": "spec-2026-07-26-missing-spec"}

        with patch.object(check_spec_context, "check_big_change_staged", return_value=mock_result), \
             patch.object(check_spec_context, "read_b2_evidence", return_value=mock_evidence), \
             patch.object(check_spec_context, "is_b2_evidence_valid", return_value=(True, None)):
            rc = check_spec_context.main(["--no-fail"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
