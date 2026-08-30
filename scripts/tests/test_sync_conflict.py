"""test_sync_conflict.py — M1.C auto 模式 CONFLICT 标记测试

验证 sync_ai_memory.py:
1. _extract_source_hint 从 body 提取 `<!-- source: ... -->` 路径
2. _resolve_source_files 解析 glob 模式
3. _check_source_conflict 检测源文件 mtime > memory mtime
4. _mark_conflict 在 body 头部加 [CONFLICT] 警告块
5. handle_file auto 模式: 源文件新 → 返回 "conflict" + body 含 [CONFLICT]
6. handle_file auto 模式: 源文件旧 → 返回 "regenerated" + body 不含 [CONFLICT]
7. handle_file auto 模式: 源文件不存在 → 不报错
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

import pytest

# Make the parent scripts/ directory importable
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import sync_ai_memory  # noqa: E402

pytestmark = pytest.mark.unit

# ─────────────────────────────────────────────
# 1. _extract_source_hint
# ─────────────────────────────────────────────


class ExtractSourceHintTests(unittest.TestCase):
    def test_extracts_simple_path(self):
        body = "<!-- source: backend/foo.py -->\nBody content"
        self.assertEqual(sync_ai_memory._extract_source_hint(body), "backend/foo.py")

    def test_extracts_glob_path(self):
        body = "<!-- source: worker/src/engine/nodes/*.py -->\nBody"
        self.assertEqual(
            sync_ai_memory._extract_source_hint(body),
            "worker/src/engine/nodes/*.py",
        )

    def test_returns_none_when_missing(self):
        body = "Just some body without hint"
        self.assertIsNone(sync_ai_memory._extract_source_hint(body))

    def test_handles_chinese_path(self):
        body = "<!-- source: 文档/规范.md -->\nBody"
        self.assertEqual(sync_ai_memory._extract_source_hint(body), "文档/规范.md")


# ─────────────────────────────────────────────
# 2. _resolve_source_files
# ─────────────────────────────────────────────


class ResolveSourceFilesTests(unittest.TestCase):
    def test_resolves_glob_to_existing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "a.py").write_text("# a")
            (tmp_path / "b.py").write_text("# b")
            (tmp_path / "c.txt").write_text("# c")

            files = sync_ai_memory._resolve_source_files(tmp_path, "*.py")
            names = sorted(f.name for f in files)
            self.assertEqual(names, ["a.py", "b.py"])

    def test_resolves_direct_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            f = tmp_path / "single.py"
            f.write_text("# single")

            files = sync_ai_memory._resolve_source_files(tmp_path, "single.py")
            self.assertEqual([f.name for f in files], ["single.py"])

    def test_returns_empty_for_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            files = sync_ai_memory._resolve_source_files(tmp_path, "nonexistent.py")
            self.assertEqual(files, [])


# ─────────────────────────────────────────────
# 3. _check_source_conflict
# ─────────────────────────────────────────────


class CheckSourceConflictTests(unittest.TestCase):
    def test_no_conflict_when_source_older(self):
        """源文件 mtime < memory mtime → 不算冲突"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "src.py"
            memory = tmp_path / "memory.md"

            # memory 写入 (mtime 更新)
            memory.write_text("x")
            time.sleep(0.05)
            # src 写入 (mtime 在 memory 之后, 但 source 应该比 memory 旧才算不冲突)
            # 实际上, src mtime > memory mtime → 冲突
            # 要测试"不冲突", 让 src mtime < memory mtime
            memory.write_text("y")  # 再更新 memory
            time.sleep(0.05)
            src.write_text("z")  # src 后写, mtime 更新
            # 当前状态: src mtime > memory mtime → 应该冲突
            # 重新构造: 让 memory mtime > src mtime
            time.sleep(0.05)
            memory.write_text("x2")  # memory 再更新一次
            time.sleep(0.05)
            # 此时 memory mtime > src mtime
            body = f"<!-- source: src.py -->\nBody"
            # memory_path 用相对于 tmp_path 的相对路径解析 src
            # 修复: _check_source_conflict 用 REPO_ROOT_DEFAULT, 不接受 root 参数
            # 这里用 monkeypatch 改 REPO_ROOT_DEFAULT
            old_root = sync_ai_memory.REPO_ROOT_DEFAULT
            sync_ai_memory.REPO_ROOT_DEFAULT = tmp_path
            try:
                conflicts = sync_ai_memory._check_source_conflict(memory, {}, body)
            finally:
                sync_ai_memory.REPO_ROOT_DEFAULT = old_root
            # memory mtime > src mtime → 不冲突
            self.assertEqual(conflicts, [])

    def test_conflict_when_source_newer(self):
        """源文件 mtime > memory mtime → 冲突"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "src.py"
            memory = tmp_path / "memory.md"

            memory.write_text("memory content")
            time.sleep(0.05)
            src.write_text("source content")  # 后写, mtime 更新

            body = "<!-- source: src.py -->\nBody"

            old_root = sync_ai_memory.REPO_ROOT_DEFAULT
            sync_ai_memory.REPO_ROOT_DEFAULT = tmp_path
            try:
                conflicts = sync_ai_memory._check_source_conflict(memory, {}, body)
            finally:
                sync_ai_memory.REPO_ROOT_DEFAULT = old_root

            self.assertEqual(len(conflicts), 1)
            self.assertEqual(conflicts[0].name, "src.py")

    def test_no_conflict_when_source_missing(self):
        """源文件不存在 → 不报错, 返回空"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            memory = tmp_path / "memory.md"
            memory.write_text("x")
            body = "<!-- source: nonexistent.py -->\nBody"

            old_root = sync_ai_memory.REPO_ROOT_DEFAULT
            sync_ai_memory.REPO_ROOT_DEFAULT = tmp_path
            try:
                conflicts = sync_ai_memory._check_source_conflict(memory, {}, body)
            finally:
                sync_ai_memory.REPO_ROOT_DEFAULT = old_root

            self.assertEqual(conflicts, [])

    def test_falls_back_to_front_matter_source(self):
        """body 没 source hint → 用 front matter source"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "fm.py"
            memory = tmp_path / "memory.md"

            memory.write_text("x")
            time.sleep(0.05)
            src.write_text("y")  # 后写, mtime 更新

            old_root = sync_ai_memory.REPO_ROOT_DEFAULT
            sync_ai_memory.REPO_ROOT_DEFAULT = tmp_path
            try:
                conflicts = sync_ai_memory._check_source_conflict(
                    memory, {"source": "fm.py"}, "Body without hint"
                )
            finally:
                sync_ai_memory.REPO_ROOT_DEFAULT = old_root

            self.assertEqual(len(conflicts), 1)
            self.assertEqual(conflicts[0].name, "fm.py")


# ─────────────────────────────────────────────
# 4. _mark_conflict
# ─────────────────────────────────────────────


class MarkConflictTests(unittest.TestCase):
    def test_marks_with_conlict_marker(self):
        body = "<!-- source: src.py -->\nBody"
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.py"
            src.write_text("x")
            marked = sync_ai_memory._mark_conflict(body, [src])
        self.assertIn("[CONFLICT]", marked)
        self.assertIn("src.py", marked)

    def test_empty_conflicts_returns_original(self):
        body = "Original body"
        result = sync_ai_memory._mark_conflict(body, [])
        self.assertEqual(result, body)

    def test_marker_after_source_hint(self):
        body = "<!-- source: x.py -->\nRest"
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "x.py"
            src.write_text("x")
            marked = sync_ai_memory._mark_conflict(body, [src])
        # CONFLICT 标记应在 source hint 之后
        hint_pos = marked.find("<!-- source:")
        conflict_pos = marked.find("[CONFLICT]")
        self.assertGreater(conflict_pos, hint_pos)


# ─────────────────────────────────────────────
# 5+6+7. handle_file auto 模式 CONFLICT 集成测试
# ─────────────────────────────────────────────


class HandleFileAutoConflictTests(unittest.TestCase):
    def _make_memory_file(self, body_hint_path: str) -> Path:
        """创建临时 .ai-memory/foo.md 文件, 含 source hint"""
        tmp = tempfile.NamedTemporaryFile(
            suffix=".md", mode="w", encoding="utf-8", delete=False
        )
        tmp.write(
            f"---\n"
            f"maintainer: auto\n"
            f"source: {body_hint_path}\n"
            f"symptom: [test]\n"
            f"solution: test solution\n"
            f"related_files: []\n"
            f"created_by: AI\n"
            f"---\n\n"
            f"<!-- source: {body_hint_path} -->\n"
            f"Body content\n"
        )
        tmp.close()
        return Path(tmp.name)

    def test_handle_file_returns_conflict_when_source_newer(self):
        """源文件 mtime > memory mtime → handle_file 返回 conflict + body 含 [CONFLICT]"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # 先写 memory (mtime 旧)
            memory = tmp_path / "memory.md"
            memory.write_text(
                f"---\n"
                f"maintainer: auto\n"
                f"source: newer_src.py\n"
                f"symptom: [test]\n"
                f"solution: test solution\n"
                f"related_files: []\n"
                f"created_by: AI\n"
                f"---\n\n"
                f"<!-- source: newer_src.py -->\n"
                f"Body\n"
            )
            time.sleep(0.2)  # wait 200ms for mtime resolution
            # 后写 src (mtime 新)
            src = tmp_path / "newer_src.py"
            src.write_text("# source")

            old_root = sync_ai_memory.REPO_ROOT_DEFAULT
            sync_ai_memory.REPO_ROOT_DEFAULT = tmp_path
            try:
                # hook_mode=False 强制非 hook 模式 (避免 read-only)
                action, message = sync_ai_memory.handle_file(memory, hook_mode=False)
            finally:
                sync_ai_memory.REPO_ROOT_DEFAULT = old_root

            self.assertEqual(action, "conflict")
            self.assertIn("CONFLICT", message)
            # 重新读 memory 内容确认 [CONFLICT] 标记写入
            new_content = memory.read_text(encoding="utf-8")
            self.assertIn("[CONFLICT]", new_content)
            self.assertIn("newer_src.py", new_content)

    def test_handle_file_returns_regenerated_when_source_older(self):
        """源文件 mtime < memory mtime → handle_file 返回 regenerated + body 不含 [CONFLICT]"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # 先写 src (mtime 旧)
            src = tmp_path / "older_src.py"
            src.write_text("# source")
            time.sleep(0.2)  # wait 200ms for mtime resolution
            # 再写 memory (mtime 新)
            memory = tmp_path / "memory.md"
            memory.write_text(
                f"---\n"
                f"maintainer: auto\n"
                f"source: older_src.py\n"
                f"symptom: [test]\n"
                f"solution: test solution\n"
                f"related_files: []\n"
                f"created_by: AI\n"
                f"---\n\n"
                f"<!-- source: older_src.py -->\n"
                f"Body\n"
            )

            old_root = sync_ai_memory.REPO_ROOT_DEFAULT
            sync_ai_memory.REPO_ROOT_DEFAULT = tmp_path
            try:
                action, message = sync_ai_memory.handle_file(memory, hook_mode=False)
            finally:
                sync_ai_memory.REPO_ROOT_DEFAULT = old_root

            self.assertEqual(action, "regenerated")
            new_content = memory.read_text(encoding="utf-8")
            self.assertNotIn("[CONFLICT]", new_content)

    def test_handle_file_no_error_when_source_missing(self):
        """源文件不存在 → 不报错, 正常 regenerated"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            memory = tmp_path / "memory.md"
            memory.write_text(
                f"---\n"
                f"maintainer: auto\n"
                f"source: nonexistent.py\n"
                f"symptom: [test]\n"
                f"solution: test solution\n"
                f"related_files: []\n"
                f"created_by: AI\n"
                f"---\n\n"
                f"<!-- source: nonexistent.py -->\n"
                f"Body\n"
            )

            old_root = sync_ai_memory.REPO_ROOT_DEFAULT
            sync_ai_memory.REPO_ROOT_DEFAULT = tmp_path
            try:
                action, _ = sync_ai_memory.handle_file(memory, hook_mode=False)
            finally:
                sync_ai_memory.REPO_ROOT_DEFAULT = old_root

            # 没源文件 → 不算冲突, 正常 regenerate
            self.assertEqual(action, "regenerated")

    def test_handle_file_dry_run_marks_would_conflict(self):
        """--dry-run 模式下, 源文件新 → 返回 'conflict' 但不写文件"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # 先写 memory (mtime 旧)
            memory = tmp_path / "memory.md"
            memory.write_text(
                f"---\n"
                f"maintainer: auto\n"
                f"source: newer_src.py\n"
                f"symptom: [test]\n"
                f"solution: test solution\n"
                f"related_files: []\n"
                f"created_by: AI\n"
                f"---\n\n"
                f"<!-- source: newer_src.py -->\n"
                f"Body\n"
            )
            time.sleep(0.2)
            # 后写 src (mtime 新)
            src = tmp_path / "newer_src.py"
            src.write_text("# source")
            original_content = memory.read_text(encoding="utf-8")

            old_root = sync_ai_memory.REPO_ROOT_DEFAULT
            sync_ai_memory.REPO_ROOT_DEFAULT = tmp_path
            try:
                action, _ = sync_ai_memory.handle_file(memory, dry_run=True, hook_mode=False)
            finally:
                sync_ai_memory.REPO_ROOT_DEFAULT = old_root

            self.assertEqual(action, "conflict")
            # dry_run → 文件未被修改
            self.assertEqual(memory.read_text(encoding="utf-8"), original_content)


if __name__ == "__main__":
    unittest.main()
