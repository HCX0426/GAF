"""
test_cross_language_parser.py (M1.B 6 用例)

验证 source_parser.py 跨 6 类源文件的解析能力:
1. test_python_ast - .py 用 ast
2. test_js_regex - .js/.ts 用正则
3. test_vue_script_extract - .vue 提取 <script>
4. test_powershell_filter - .ps1 function/filter
5. test_markdown_heading - .md heading 锚点
6. test_unknown_extension_fallback - 未知后缀空 list
"""

import textwrap
from pathlib import Path

import pytest

from scripts.source_parser import (
    parse_jsts,
    parse_markdown,
    parse_powershell,
    parse_python,
    parse_source,
    parse_vue,
    supported_extensions,
)

# ─────────────────────────────────────────────
# 1. Python AST
# ─────────────────────────────────────────────


def test_python_ast(tmp_path: Path):
    """Python ast 解析: 提取类 + 模块级函数 + 常量"""
    py = tmp_path / "demo.py"
    py.write_text(
        textwrap.dedent(
            '''\
            """module docstring"""

            DEFAULT_TIMEOUT = 30

            class Calculator:
                """计算器类"""

                def add(self, x: int, y: int) -> int:
                    return x + y

            async def fetch_data(url: str) -> dict:
                return {}

            def helper(name: str) -> None:
                pass
            '''
        ),
        encoding="utf-8",
    )

    elements = parse_python(py)
    by_name = {el.name: el for el in elements}

    # 1) 常量
    assert "DEFAULT_TIMEOUT" in by_name
    assert by_name["DEFAULT_TIMEOUT"].kind == "constant"
    assert by_name["DEFAULT_TIMEOUT"].line == 3

    # 2) 类
    assert "Calculator" in by_name
    assert by_name["Calculator"].kind == "class"
    assert by_name["Calculator"].line == 5

    # 3) 方法 (作为 function + parent=Calculator)
    assert "add" in by_name
    assert by_name["add"].kind == "function"
    assert by_name["add"].parent == "Calculator"
    assert by_name["add"].extras.get("async") is False

    # 4) 异步模块级函数
    assert "fetch_data" in by_name
    assert by_name["fetch_data"].extras.get("async") is True
    assert "url: str" in (by_name["fetch_data"].signature or "")

    # 5) 普通模块级函数
    assert "helper" in by_name
    assert by_name["helper"].parent is None


# ─────────────────────────────────────────────
# 2. JS/TS 正则
# ─────────────────────────────────────────────


def test_js_regex(tmp_path: Path):
    """JS/TS 正则: 提取 function / arrow / class"""
    js = tmp_path / "demo.ts"
    js.write_text(
        textwrap.dedent(
            '''\
            export class UserService {
                findOne(id: number) { return null; }
            }

            export function login(user: string, pwd: string) {
                return true;
            }

            async function fetchJSON(url: string) {
                return {};
            }

            export const debounce = (fn: Function) => {
                return fn;
            };
            '''
        ),
        encoding="utf-8",
    )

    elements = parse_jsts(js)
    by_name = {el.name: el for el in elements}

    # 1) class
    assert "UserService" in by_name
    assert by_name["UserService"].kind == "class"

    # 2) 普通 function
    assert "login" in by_name
    assert by_name["login"].kind == "function"
    assert by_name["login"].extras["js_kind"] == "function"

    # 3) async function
    assert "fetchJSON" in by_name
    assert by_name["fetchJSON"].extras["js_kind"] == "function"

    # 4) arrow function
    assert "debounce" in by_name
    assert by_name["debounce"].extras["js_kind"] == "arrow"

    # 5) 行号
    assert by_name["UserService"].line == 1
    assert by_name["login"].line == 5
    assert by_name["fetchJSON"].line == 9
    assert by_name["debounce"].line == 13


# ─────────────────────────────────────────────
# 3. Vue <script> 提取
# ─────────────────────────────────────────────


def test_vue_script_extract(tmp_path: Path):
    """Vue: 提取 <script> 块后, 用 JS 正则解析内部"""
    vue = tmp_path / "Counter.vue"
    vue.write_text(
        textwrap.dedent(
            '''\
            <template>
              <div>{{ count }}</div>
            </template>

            <script setup lang="ts">
            import { ref } from 'vue';

            export function useCounter() {
                const count = ref(0);
                return { count };
            }

            const helper = () => 42;
            </script>

            <style scoped>
            .counter { color: red; }
            </style>
            '''
        ),
        encoding="utf-8",
    )

    elements = parse_vue(vue)
    names = {el.name for el in elements}

    # 1) 应找到 useCounter (function)
    assert "useCounter" in names
    use_counter = next(el for el in elements if el.name == "useCounter")
    assert use_counter.kind == "function"
    assert use_counter.parent == "<vue script>"

    # 2) 应找到 helper (arrow)
    assert "helper" in names

    # 3) 不会匹配 <style> 块里的类名
    assert "counter" not in names

    # 4) 行号应指向 script 内部 (而非文件首行)
    assert all(el.line > 5 for el in elements)


# ─────────────────────────────────────────────
# 4. PowerShell function/filter
# ─────────────────────────────────────────────


def test_powershell_filter(tmp_path: Path):
    """PowerShell: 提取 function + filter, 含参数签名"""
    ps1 = tmp_path / "utils.ps1"
    # 写入 UTF-8 BOM
    ps1.write_bytes(
        b'\xef\xbb\xbf'
        + textwrap.dedent(
            '''\
            function Get-Greeting {
                param([string]$Name)
                "Hello, $Name"
            }

            filter To-Upper {
                $_.ToUpper()
            }

            function Send-Mail {
                param([string]$To, [string]$Subject)
                # ...
            }
            '''
        ).encode("utf-8")
    )

    elements = parse_powershell(ps1)
    by_name = {el.name: el for el in elements}

    # 1) function
    assert "Get-Greeting" in by_name
    assert by_name["Get-Greeting"].kind == "function"
    assert "[string]$Name" in (by_name["Get-Greeting"].signature or "")

    # 2) filter (注意 filter 也是一种关键字, 应区分)
    assert "To-Upper" in by_name
    assert by_name["To-Upper"].kind == "filter"

    # 3) 多参数
    assert "Send-Mail" in by_name
    sig = by_name["Send-Mail"].signature or ""
    assert "$To" in sig and "$Subject" in sig


# ─────────────────────────────────────────────
# 5. Markdown heading 锚点
# ─────────────────────────────────────────────


def test_markdown_heading(tmp_path: Path):
    """Markdown: 提取 1-6 级 heading, 生成 GitHub 风格锚点"""
    md = tmp_path / "README.md"
    md.write_text(
        textwrap.dedent(
            '''\
            # Top Title

            Some intro text.

            ## 二级标题 Sub Section

            ### 3.1 Subsection 数字开头

            Body line.
            '''
        ),
        encoding="utf-8",
    )

    elements = parse_markdown(md)
    by_name = {el.name: el for el in elements}

    # 1) 3 个 heading
    assert len(elements) == 3

    # 2) # → level 1
    assert by_name["Top Title"].extras["level"] == 1
    assert by_name["Top Title"].extras["anchor"] == "top-title"

    # 3) ## → level 2
    sec = by_name["二级标题 Sub Section"]
    assert sec.extras["level"] == 2
    # 锚点保留中文, 空格 → -, 小写
    assert "sub-section" in sec.extras["anchor"]

    # 4) ### → level 3
    sub = by_name["3.1 Subsection 数字开头"]
    assert sub.extras["level"] == 3
    # 数字开头保留 (GitHub 行为), 标点去除
    assert "subsection" in sub.extras["anchor"]


# ─────────────────────────────────────────────
# 6. 未知后缀 fallback
# ─────────────────────────────────────────────


def test_unknown_extension_fallback(tmp_path: Path):
    """未知后缀 (如 .xyz / 无后缀) → parse_source 返回空 list"""
    unknown = tmp_path / "data.xyz"
    unknown.write_text("class Foo:\n    pass\n", encoding="utf-8")

    no_ext = tmp_path / "Makefile"
    no_ext.write_text("build:\n\techo hi\n", encoding="utf-8")

    # 1) 未知后缀返回空
    assert parse_source(unknown) == []
    assert parse_python(unknown) == []  # 各 parser 也单独接受
    assert parse_jsts(unknown) == []
    assert parse_vue(unknown) == []
    assert parse_powershell(unknown) == []
    assert parse_markdown(unknown) == []

    # 2) parse_source 对无后缀也返回空
    assert parse_source(no_ext) == []

    # 3) supported_extensions 列出已知
    exts = supported_extensions()
    assert ".py" in exts
    assert ".ts" in exts
    assert ".vue" in exts
    assert ".ps1" in exts
    assert ".md" in exts
    assert ".xyz" not in exts
