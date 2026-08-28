"""
GAF 跨语言 source 解析器 (M1.B v8.3.1)

支持从 GAF 项目中 6 类源文件提取结构化元素 (类/函数/常量/heading),
为 `.ai-memory/` 的 `auto` 模式文件提供精确的内容生成能力。

设计原则:
- 5 类显式语言 + 1 类 fallback
- 每类返回相同结构的 `SourceElement` 列表
- 行号 1-based, 与编辑器一致
- 失败回退: 解析失败不抛错, 返回空 list, 由 sync_ai_memory 兜底

使用:
    from source_parser import parse_source

    elements = parse_source(Path("backend/foo/urls.py"))
    for el in elements:
        print(f"{el.kind:8} L{el.line:4}  {el.name}")
"""

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SourceElement:
    """从源文件提取的单个结构元素"""

    kind: str  # class / function / constant / heading / filter / unknown
    name: str  # 元素名 (类名/函数名/常量名/heading 文本)
    line: int  # 1-based 行号
    parent: str | None = None  # 父级 (如方法所在的类名)
    signature: str | None = None  # 函数签名 (如 "(self, x: int) -> bool")
    extras: dict = field(default_factory=dict)  # 额外信息 (heading level 等)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "name": self.name,
            "line": self.line,
            "parent": self.parent,
            "signature": self.signature,
            **self.extras,
        }


# ─────────────────────────────────────────────
# 1. Python AST 解析
# ─────────────────────────────────────────────


def parse_python(path: Path) -> list[SourceElement]:
    """用 ast 模块解析 .py 文件, 提取 class/function/常量赋值

    Returns:
        类 (含方法)、模块级函数、模块级常量赋值
    """
    if path.suffix.lower() != ".py":
        return []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []

    elements: list[SourceElement] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            # 提取类本身 + 它的方法
            elements.append(
                SourceElement(
                    kind="class",
                    name=node.name,
                    line=node.lineno,
                )
            )
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    sig = _format_func_signature(item)
                    elements.append(
                        SourceElement(
                            kind="function",
                            name=item.name,
                            line=item.lineno,
                            parent=node.name,
                            signature=sig,
                            extras={"async": isinstance(item, ast.AsyncFunctionDef)},
                        )
                    )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sig = _format_func_signature(node)
            elements.append(
                SourceElement(
                    kind="function",
                    name=node.name,
                    line=node.lineno,
                    signature=sig,
                    extras={"async": isinstance(node, ast.AsyncFunctionDef)},
                )
            )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            # 注解赋值: x: int = 5
            elements.append(
                SourceElement(
                    kind="constant",
                    name=node.target.id,
                    line=node.lineno,
                )
            )
        elif isinstance(node, ast.Assign):
            # 普通赋值: X = 5 (取第一个 target)
            if node.targets and isinstance(node.targets[0], ast.Name):
                elements.append(
                    SourceElement(
                        kind="constant",
                        name=node.targets[0].id,
                        line=node.lineno,
                    )
                )
    return elements


def _format_func_signature(func_node) -> str:
    """ast.FunctionDef → "(self, x: int) -> bool" 形式签名

    包含参数类型注解 (Python 3.10+ 使用 ast.unparse 简化)
    """
    args: list[str] = []
    posonly = getattr(func_node.args, "posonlyargs", [])
    for a in posonly:
        args.append(_format_arg(a))
    if posonly:
        args.append("/")
    for a in func_node.args.args:
        args.append(_format_arg(a))
    if func_node.args.vararg:
        vararg_str = f"*{func_node.args.vararg.arg}"
        if func_node.args.vararg.annotation is not None:
            vararg_str += f": {ast.unparse(func_node.args.vararg.annotation)}"
        args.append(vararg_str)
    elif func_node.args.kwonlyargs:
        args.append("*")
    for a in func_node.args.kwonlyargs:
        args.append(_format_arg(a))
    if func_node.args.kwarg:
        kwarg_str = f"**{func_node.args.kwarg.arg}"
        if func_node.args.kwarg.annotation is not None:
            kwarg_str += f": {ast.unparse(func_node.args.kwarg.annotation)}"
        args.append(kwarg_str)

    sig = f"({', '.join(args)})"
    if func_node.returns is not None:
        ret = ast.unparse(func_node.returns)
        sig += f" -> {ret}"
    return sig


def _format_arg(arg_node) -> str:
    """ast.arg → 'name' 或 'name: type' (含注解)"""
    if arg_node.annotation is not None:
        return f"{arg_node.arg}: {ast.unparse(arg_node.annotation)}"
    return arg_node.arg


# ─────────────────────────────────────────────
# 2. JS/TS 正则解析
# ─────────────────────────────────────────────

# 匹配 function/async function/export function 声明
# 捕获组 1 = 函数名
_JS_FUNCTION_RE = re.compile(
    r"^[ \t]*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(",
    re.MULTILINE,
)
# 匹配箭头函数 const/let/var x = () => ...
# 捕获组 1 = 函数名
_JS_ARROW_CONST_RE = re.compile(
    r"^[ \t]*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>",
    re.MULTILINE,
)
# 匹配类声明
_JS_CLASS_RE = re.compile(
    r"^[ \t]*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)


def parse_jsts(path: Path) -> list[SourceElement]:
    """用正则解析 .js / .ts / .jsx / .tsx 文件

    行号计算: 用 m.start() + len(leading_whitespace) 跳过行首空白,
    避免 `^` 在 MULTILINE 模式下匹配空行末尾导致行号偏小 1
    """
    if path.suffix.lower() not in {".js", ".jsx", ".ts", ".tsx"}:
        return []
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    elements: list[SourceElement] = []

    # 函数声明
    for m in _JS_FUNCTION_RE.finditer(source):
        line = _line_from_match(source, m)
        elements.append(
            SourceElement(
                kind="function",
                name=m.group(1),
                line=line,
                extras={"js_kind": "function"},
            )
        )

    # 箭头函数 (const x = () => ...)
    for m in _JS_ARROW_CONST_RE.finditer(source):
        line = _line_from_match(source, m)
        elements.append(
            SourceElement(
                kind="function",
                name=m.group(1),
                line=line,
                extras={"js_kind": "arrow"},
            )
        )

    # 类
    for m in _JS_CLASS_RE.finditer(source):
        line = _line_from_match(source, m)
        elements.append(
            SourceElement(
                kind="class",
                name=m.group(1),
                line=line,
            )
        )

    return elements


def _line_from_match(source: str, m: re.Match) -> int:
    """从 re.Match 计算行号 (基于 m.start() 之后的非空白位置)

    与 re.MULTILINE 模式下 `^` 匹配空行末尾的情况不同,
    我们要找的是标识符所在的行, 不是 `^` 匹配的行
    """
    # 跳过 m.start() 处的空白, 找到第一个非空白字符
    pos = m.start()
    while pos < len(source) and source[pos] in " \t":
        pos += 1
    return source[:pos].count("\n") + 1


# ─────────────────────────────────────────────
# 3. Vue `<script>` 提取
# ─────────────────────────────────────────────

_VUE_SCRIPT_RE = re.compile(
    r"<script\b[^>]*>(.*?)</script>",
    re.DOTALL | re.IGNORECASE,
)


def parse_vue(path: Path) -> list[SourceElement]:
    """从 .vue 提取 <script> 块, 然后用 JS 解析器再解析"""
    if path.suffix.lower() != ".vue":
        return []
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    elements: list[SourceElement] = []
    for script_match in _VUE_SCRIPT_RE.finditer(source):
        script_body = script_match.group(1)
        script_start_line = source[: script_match.start()].count("\n") + 1

        # 在 script_body 内部直接跑 JS 正则 (不通过 parse_jsts, 避免
        # 重新走 read_text + 偏移计算; 偏移在调用方手工加 script_start_line)
        for m in _JS_FUNCTION_RE.finditer(script_body):
            line = script_start_line + _line_from_match(script_body, m) - 1
            elements.append(
                SourceElement(
                    kind="function",
                    name=m.group(1),
                    line=line,
                    parent="<vue script>",
                    extras={"js_kind": "function"},
                )
            )
        for m in _JS_ARROW_CONST_RE.finditer(script_body):
            line = script_start_line + _line_from_match(script_body, m) - 1
            elements.append(
                SourceElement(
                    kind="function",
                    name=m.group(1),
                    line=line,
                    parent="<vue script>",
                    extras={"js_kind": "arrow"},
                )
            )
        for m in _JS_CLASS_RE.finditer(script_body):
            line = script_start_line + _line_from_match(script_body, m) - 1
            elements.append(
                SourceElement(
                    kind="class",
                    name=m.group(1),
                    line=line,
                    parent="<vue script>",
                )
            )

    return elements


# ─────────────────────────────────────────────
# 4. PowerShell function/Filter 解析
# ─────────────────────────────────────────────

_PS_FUNC_RE = re.compile(
    r"^[ \t]*(?:function|filter)\s+([A-Za-z_][\w-]*)\s*(?:\(([^)]*)\))?",
    re.MULTILINE | re.IGNORECASE,
)

# 提取 param() 块内容 (后续分析参数)
_PS_PARAM_RE = re.compile(
    r"\{\s*(?:#[^\n]*\n\s*)*param\s*\((.*?)\)",
    re.DOTALL | re.IGNORECASE,
)


def parse_powershell(path: Path) -> list[SourceElement]:
    """用正则解析 .ps1 文件, 提取 function / filter 块 + param 参数"""
    if path.suffix.lower() != ".ps1":
        return []
    try:
        source = path.read_text(encoding="utf-8-sig")  # 处理 BOM
    except (UnicodeDecodeError, OSError):
        try:
            source = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return []

    elements: list[SourceElement] = []
    # 找到每个 function/filter 的开始位置
    func_matches = list(_PS_FUNC_RE.finditer(source))

    for idx, m in enumerate(func_matches):
        func_start = m.start()
        # 计算行号 (用 m.start() + 跳过空白)
        line = _line_from_match(source, m)
        name = m.group(1)
        params_decl = m.group(2) or ""

        # 区分 function vs filter
        keyword = m.group(0).strip().lower().split()[0]
        kind = "filter" if keyword == "filter" else "function"

        # 查找 param() 块 (可能在 function 体内)
        # 范围: 从 func_start 到下一个 function/filter 或文件结尾
        func_end = func_matches[idx + 1].start() if idx + 1 < len(func_matches) else len(source)
        func_body = source[func_start:func_end]

        param_match = _PS_PARAM_RE.search(func_body)
        if param_match and not params_decl:
            # 提取 param 块中的参数 (保留类型注解)
            param_text = param_match.group(1).strip()
            # 移除行注释
            param_text = re.sub(r"#[^\n]*", "", param_text)
            # 清理空白
            params_decl = re.sub(r"\s+", " ", param_text).strip()

        sig = f"({params_decl})" if params_decl else None
        elements.append(
            SourceElement(
                kind=kind,
                name=name,
                line=line,
                signature=sig,
                extras={"ps_kind": keyword},
            )
        )
    return elements


# ─────────────────────────────────────────────
# 5. Markdown heading 锚点
# ─────────────────────────────────────────────

_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def parse_markdown(path: Path) -> list[SourceElement]:
    """从 .md 文件提取所有 heading (1-6 级), 生成 GitHub 风格锚点"""
    if path.suffix.lower() != ".md":
        return []
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    elements: list[SourceElement] = []
    for m in _MD_HEADING_RE.finditer(source):
        line = _line_from_match(source, m)
        level = len(m.group(1))
        title = m.group(2).strip()
        # GitHub 风格锚点: 小写、空格→-、去标点
        anchor = _github_anchor(title)
        elements.append(
            SourceElement(
                kind="heading",
                name=title,
                line=line,
                extras={"level": level, "anchor": anchor},
            )
        )
    return elements


def _github_anchor(title: str) -> str:
    """GitHub 风格: 'Hello World!' → 'hello-world'"""
    s = title.lower()
    s = re.sub(r"[^\w\s\u4e00-\u9fff-]", "", s)  # 保留中英文 + 数字 + -
    s = re.sub(r"\s+", "-", s.strip())
    return s


# ─────────────────────────────────────────────
# 6. 统一入口
# ─────────────────────────────────────────────

# 后缀 → 解析器
_PARSERS = {
    ".py": parse_python,
    ".js": parse_jsts,
    ".jsx": parse_jsts,
    ".ts": parse_jsts,
    ".tsx": parse_jsts,
    ".vue": parse_vue,
    ".ps1": parse_powershell,
    ".md": parse_markdown,
}


def parse_source(path: Path) -> list[SourceElement]:
    """根据文件后缀自动选解析器; 未知后缀返回空 list (fallback 到行号模式)

    Args:
        path: 源文件路径

    Returns:
        SourceElement 列表; 解析失败/未知后缀 → 空 list
    """
    suffix = path.suffix.lower()
    parser = _PARSERS.get(suffix)
    if parser is None:
        return []
    return parser(path)


def supported_extensions() -> list[str]:
    """返回所有支持的扩展名"""
    return sorted(_PARSERS.keys())
