"""test_sync_ai_memory.py — Unit tests for sync_ai_memory.py and symptom_synonyms.py.

Covers the 8 cases listed in spec.md Appendix G §G.1:

1. test_yaml_parse_with_chinese        — front matter with CJK values
2. test_yaml_parse_with_special_chars   — front matter with `:` `#` `{}`
3. test_3_maintainer_modes              — auto / derived-manual / manual
4. test_query_command                   — `--query 弹窗` returns matches
5. test_query_with_category             — `--query popup:agent:duplicate` matches
6. test_root_param                      — `--root /tmp/test` operates on alt repo
7. test_no_yaml_dependency              — friendly error when PyYAML missing
8. test_no_front_matter                 — warning when front matter absent

Run with: `conda run -n gaf python -m pytest GAF/scripts/tests/test_sync_ai_memory.py -v`
or simply: `python GAF/scripts/tests/test_sync_ai_memory.py` (uses embedded
test runner that invokes unittest).
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List

import pytest

# Make the parent scripts/ directory importable so we can load the modules
# under test without installing them as a package.
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import sync_ai_memory  # noqa: E402
import symptom_synonyms  # noqa: E402

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Fixtures: small synthetic .ai-memory repos
# ---------------------------------------------------------------------------


SAMPLE_LESSON_YAML = """\
---
date: '2026-06-10'
maintainer: auto
symptom: [popup:agent:duplicate, 弹窗, agent 重复]
solution: 文件锁 + SW_HIDE
related_files:
  - agent/src/client/connection.py
created_by: AI
priority: high
---

# Agent popup bug

Long-running story of how the agent process kept spawning duplicates
because the file lock wasn't being acquired atomically with the
process fork.
"""

SAMPLE_LESSON_API_404 = """\
---
date: 2026-06-14
symptom: [api:404:task, 任务创建 404, POST tasks 404]
solution: 在 urls.py 末尾追加 tasks/ 路由
related_files:
  - backend/tasks/urls.py
created_by: AI
priority: high
---

# API 404 on POST /api/v2/tasks/

The router prefix was wrong.
"""

SAMPLE_NO_FRONT_MATTER = """\
# This file has no front matter

Just plain markdown.
"""

SAMPLE_SPECIAL_CHARS = """\
---
maintainer: auto
source: backend/foo/bar.py:func_with_colon#anchor
symptom: ["#hash", "{curly}", "key: value"]
solution: "escape: with quotes"
related_files:
  - "path/with:colon/file.py"
created_by: user
priority: medium
---

# Special chars body
"""

SAMPLE_DERIVED_MANUAL = """\
---
maintainer: derived-manual
source: backend/data-flow.md
symptom: [data-flow]
solution: 人工 review
related_files:
  - backend/data-flow.md
created_by: AI
priority: medium
---

# Derived-manual file (should be skipped)
"""

SAMPLE_MANUAL = """\
---
maintainer: manual
symptom: [custom]
solution: 人类只读
related_files: []
created_by: user
priority: low
---

# Manual file (should be skipped)
"""


def _make_temp_ai_memory(files: dict) -> Path:
    """Create a temporary directory tree mimicking .ai-memory/.

    `files` is a mapping of relative paths -> file content.
    Returns the root path; caller is responsible for cleanup.
    """
    tmp = Path(tempfile.mkdtemp(prefix="gaf_test_ai_memory_"))
    for rel, content in files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp


# ---------------------------------------------------------------------------
# 1. test_yaml_parse_with_chinese
# ---------------------------------------------------------------------------


class YamlParseWithChineseTests(unittest.TestCase):
    def test_yaml_parse_with_chinese(self):
        data, body, had_fm = sync_ai_memory.parse_front_matter(SAMPLE_LESSON_YAML)
        self.assertTrue(had_fm, "front matter should be detected")
        self.assertEqual(data["date"], "2026-06-10")
        self.assertIn("popup:agent:duplicate", data["symptom"])
        self.assertIn("弹窗", data["symptom"])
        self.assertEqual(data["solution"], "文件锁 + SW_HIDE")
        self.assertEqual(data["created_by"], "AI")
        self.assertEqual(data["maintainer"], "auto")
        self.assertIn("agent/src/client/connection.py", data["related_files"])
        self.assertIn("popup", body)


# ---------------------------------------------------------------------------
# 2. test_yaml_parse_with_special_chars
# ---------------------------------------------------------------------------


class YamlParseWithSpecialCharsTests(unittest.TestCase):
    def test_yaml_parse_with_special_chars(self):
        data, body, had_fm = sync_ai_memory.parse_front_matter(SAMPLE_SPECIAL_CHARS)
        self.assertTrue(had_fm)
        self.assertEqual(data["maintainer"], "auto")
        self.assertEqual(data["source"], "backend/foo/bar.py:func_with_colon#anchor")
        self.assertIn("#hash", data["symptom"])
        self.assertIn("{curly}", data["symptom"])
        self.assertIn("key: value", data["symptom"])
        self.assertEqual(data["solution"], "escape: with quotes")
        self.assertEqual(data["related_files"], ["path/with:colon/file.py"])


# ---------------------------------------------------------------------------
# 3. test_3_maintainer_modes
# ---------------------------------------------------------------------------


class ThreeMaintainerModesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = _make_temp_ai_memory(
            {
                "lessons/auto-test.md": SAMPLE_LESSON_YAML,
                "lessons/derived-test.md": SAMPLE_DERIVED_MANUAL,
                "lessons/manual-test.md": SAMPLE_MANUAL,
            }
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_auto_mode_regenerates(self):
        path = self.tmp / "lessons" / "auto-test.md"
        action, _msg = sync_ai_memory.handle_file(path)
        self.assertEqual(action, "regenerated")
        # Body should now contain the auto-generated skeleton marker.
        new_text = path.read_text(encoding="utf-8")
        self.assertIn("<!-- source:", new_text)
        self.assertIn("Auto-generated knowledge entry", new_text)

    def test_derived_manual_mode_skips(self):
        path = self.tmp / "lessons" / "derived-test.md"
        original = path.read_text(encoding="utf-8")
        action, _msg = sync_ai_memory.handle_file(path)
        self.assertEqual(action, "skipped")
        # File content must not change.
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_manual_mode_skips(self):
        path = self.tmp / "lessons" / "manual-test.md"
        original = path.read_text(encoding="utf-8")
        action, _msg = sync_ai_memory.handle_file(path)
        self.assertEqual(action, "skipped")
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_auto_mode_read_only_when_hook_flag_set(self):
        # v8.4 N105 fix: when handle_file is invoked with hook_mode=True,
        # an auto-mode file must NOT be rewritten — the hook runner is
        # expected to leave the working tree alone (otherwise the
        # framework silently reverts our write).
        path = self.tmp / "lessons" / "auto-test.md"
        original = path.read_text(encoding="utf-8")
        action, msg = sync_ai_memory.handle_file(path, hook_mode=True)
        self.assertEqual(action, "read-only")
        self.assertIn("hook context", msg)
        # File content must be unchanged.
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_auto_mode_read_only_via_env_var(self):
        # Same as above, but exercising the env-based detection path
        # that the `gaf-sync` pre-commit hook uses.
        path = self.tmp / "lessons" / "auto-test.md"
        original = path.read_text(encoding="utf-8")
        import os
        os.environ["PRE_COMMIT"] = "1"
        try:
            action, _msg = sync_ai_memory.handle_file(path)
            self.assertEqual(action, "read-only")
            self.assertEqual(path.read_text(encoding="utf-8"), original)
        finally:
            os.environ.pop("PRE_COMMIT", None)

    def test_auto_mode_writes_when_allow_hook_writes(self):
        # Override knob for maintenance scripts that DO want to
        # refresh auto-maintained files even from a hook.
        path = self.tmp / "lessons" / "auto-test.md"
        import os
        os.environ["PRE_COMMIT"] = "1"
        os.environ["GAF_ALLOW_HOOK_WRITES"] = "1"
        try:
            action, _msg = sync_ai_memory.handle_file(path)
            self.assertEqual(action, "regenerated")
        finally:
            os.environ.pop("PRE_COMMIT", None)
            os.environ.pop("GAF_ALLOW_HOOK_WRITES", None)


# ---------------------------------------------------------------------------
# 4. test_query_command
# ---------------------------------------------------------------------------


class QueryCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = _make_temp_ai_memory(
            {
                "lessons/popup.md": SAMPLE_LESSON_YAML,
                "lessons/api.md": SAMPLE_LESSON_API_404,
            }
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_query_chinese_keyword(self):
        results = sync_ai_memory.query_lessons("弹窗", self.tmp)
        names = [r["path"].name for r in results]
        self.assertIn("popup.md", names)
        self.assertNotIn("api.md", names)

    def test_query_english_keyword(self):
        results = sync_ai_memory.query_lessons("agent duplicate", self.tmp)
        names = [r["path"].name for r in results]
        self.assertIn("popup.md", names)


# ---------------------------------------------------------------------------
# 5. test_query_with_category
# ---------------------------------------------------------------------------


class QueryWithCategoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = _make_temp_ai_memory(
            {
                "lessons/popup.md": SAMPLE_LESSON_YAML,
                "lessons/api.md": SAMPLE_LESSON_API_404,
            }
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_query_full_category(self):
        results = sync_ai_memory.query_lessons("popup:agent:duplicate", self.tmp)
        names = [r["path"].name for r in results]
        self.assertIn("popup.md", names)
        self.assertNotIn("api.md", names)

    def test_query_partial_category(self):
        results = sync_ai_memory.query_lessons("api:404", self.tmp)
        names = [r["path"].name for r in results]
        self.assertIn("api.md", names)


# ---------------------------------------------------------------------------
# 6. test_root_param
# ---------------------------------------------------------------------------


class RootParamTests(unittest.TestCase):
    def test_root_param_is_resolved(self):
        tmp = _make_temp_ai_memory({"lessons/x.md": SAMPLE_LESSON_YAML})
        try:
            # Mirror of CLI: --root <path> must resolve relative to that path.
            from sync_ai_memory import collect_lessons
            lessons = collect_lessons(tmp)
            self.assertEqual(len(lessons), 1)
            self.assertEqual(lessons[0]["path"].name, "x.md")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 7. test_no_yaml_dependency
# ---------------------------------------------------------------------------


class NoYamlDependencyTests(unittest.TestCase):
    def test_friendly_error_when_yaml_missing(self):
        # Temporarily stub out the yaml module and verify the error.
        original = sync_ai_memory.yaml
        sync_ai_memory.yaml = None
        try:
            with self.assertRaises(sync_ai_memory.FrontMatterError) as ctx:
                sync_ai_memory.parse_front_matter(SAMPLE_LESSON_YAML)
            self.assertIn("PyYAML", str(ctx.exception))
        finally:
            sync_ai_memory.yaml = original


# ---------------------------------------------------------------------------
# 8. test_no_front_matter
# ---------------------------------------------------------------------------


class NoFrontMatterTests(unittest.TestCase):
    def test_warning_when_front_matter_absent(self):
        tmp = _make_temp_ai_memory({"lessons/bare.md": SAMPLE_NO_FRONT_MATTER})
        try:
            action, msg = sync_ai_memory.handle_file(tmp / "lessons" / "bare.md")
            self.assertEqual(action, "warning")
            self.assertIn("no front matter", msg)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Bonus: symptom_synonyms expand_query behaviour
# ---------------------------------------------------------------------------


class SynonymExtensionTests(unittest.TestCase):
    def test_register_category_basic(self):
        ok = symptom_synonyms.register_category(
            "ci:test:flaky",
            ["flaky test", "测试抖动"],
        )
        self.assertTrue(ok)
        # Either a substring of any synonym or the category itself should
        # expand the keyword set so future --query can find the lesson.
        keywords = symptom_synonyms.expand_query("flaky")
        self.assertTrue(
            any("flaky" in k for k in keywords),
            f"expected 'flaky' in expanded keywords, got {keywords!r}",
        )
        self.assertIn("ci:test:flaky", keywords)

    def test_register_rejects_too_few_synonyms(self):
        ok = symptom_synonyms.register_category("ci:x", ["only one"])
        self.assertFalse(ok)

    def test_register_rejects_all_english(self):
        # No CJK character anywhere → reject (bilingual rule).
        ok = symptom_synonyms.register_category(
            "ci:alleng", ["flaky only", "english only"],
        )
        self.assertFalse(ok)

    def test_register_rejects_all_chinese(self):
        # No ASCII letter anywhere → reject (bilingual rule).
        ok = symptom_synonyms.register_category(
            "ci:allchn", ["测试一", "测试二"],
        )
        self.assertFalse(ok)

    def test_register_rejects_uppercase(self):
        ok = symptom_synonyms.register_category("CI:Test", ["x", "测试"])
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
