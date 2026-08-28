"""Regression guard: no subprocess call may use text=True / universal_newlines=True
without an explicit encoding= (Windows gbk-locale decode hazard).

History: during pytest runs of the doc_health tests (2026-08-23) the batch emitted
``UnicodeDecodeError: 'gbk' codec can't decode byte ...`` from subprocess reader
threads. Root cause: ``subprocess.run(..., text=True)`` with no ``encoding=``
decodes stdout/stderr with the Windows *locale* codec (gbk), which cannot decode
UTF-8 bytes emitted by our tooling. Fix is to always pass ``encoding="utf-8"``.
"""

from __future__ import annotations

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]  # scripts/
SUBPROCESS_FUNCS = {"run", "check_output", "Popen", "call", "check_call"}


def _iter_py(root: pathlib.Path):
    for p in root.rglob("*.py"):
        # Exclude this regression test file itself (it has no offending call,
        # but avoid any self-reference noise).
        if p.name == "test_subprocess_encoding.py":
            continue
        yield p


def test_no_text_true_without_encoding() -> None:
    offenders: list[str] = []
    for p in _iter_py(REPO):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = None
            if isinstance(func, ast.Attribute):
                val = func.value
                if isinstance(val, ast.Name) and val.id == "subprocess":
                    name = func.attr
            elif isinstance(func, ast.Name):
                name = func.id
            if name not in SUBPROCESS_FUNCS:
                continue
            has_text = False
            has_encoding = False
            for kw in node.keywords:
                if kw.arg in ("text", "universal_newlines"):
                    if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        has_text = True
                elif kw.arg == "encoding":
                    has_encoding = True
            if has_text and not has_encoding:
                offenders.append(f"{p.relative_to(REPO)}:{node.lineno}")
    assert not offenders, (
        "subprocess calls using text=True/universal_newlines=True without "
        "encoding= (Windows gbk decode hazard):\n" + "\n".join(sorted(offenders))
    )
