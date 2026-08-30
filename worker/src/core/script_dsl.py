"""Script DSL (Domain Specific Language) compiler for GAF automation tasks.

Provides a simplified syntax for defining automation pipelines that compiles
to MaaFramework-compatible Pipeline JSON format.

N126-F3 expanded features (2026-06-21):
- Multi-line scripts with proper indentation handling
- Variable interpolation via ${var} or $var syntax
- Variable assignment via `set name = value`
- Conditional branches: if/elif/else/end
- Loops: loop N / loop while <cond> / loop over <list> / break / continue
- Nested blocks with proper scope tracking
- Comments via # (full line) and trailing # (after action)

Example DSL source:

    # Login flow
    set username = "admin"
    set password = "secret123"

    click(100, 200)
    text_input(${username})
    click(100, 300)
    text_input(${password})
    click(200, 400)  # submit button

    if ${username} == "admin"
        click(500, 500)  # admin panel
    else
        click(600, 600)  # user panel
    end

    loop 3
        click(700, 700)
        wait(500)
    end
"""

import re
from typing import Any


class DSLCompileError(Exception):
    """Raised when DSL source code fails to compile"""

    def __init__(self, message: str, line: int = 0, col: int = 0):
        self.line = line
        self.col = col
        super().__init__(message)


# Regex for variable interpolation: ${name} or $name (word boundary)
_VAR_INTERP_RE = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}|\$([a-zA-Z_][a-zA-Z0-9_]*)")

# Regex for variable assignment: set name = value
_SET_RE = re.compile(r"^set\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)$")

# Regex for if/elif conditions: <lhs> <op> <rhs>
_COND_RE = re.compile(r"^(.+?)\s*(==|!=|<=|>=|<|>)\s*(.+)$")


class DSLCompiler:
    """Compile GAF Script DSL into executable pipeline definitions.

    The DSL provides a simplified Python-like syntax for defining
    automation task pipelines. Supports:
    - Basic actions: click/swipe/key_press/text_input/screenshot/wait
    - Variable assignment and interpolation
    - Conditional branches (if/elif/else/end)
    - Loops (loop N / loop while / loop over / break / continue)
    - Comments (# full line or trailing)
    """

    # Action type constants matching MaaFramework Pipeline protocol
    ACTION_CLICK = "Click"
    ACTION_SWIPE = "Swipe"
    ACTION_KEY_PRESS = "KeyPress"
    ACTION_TEXT_INPUT = "TextInput"
    ACTION_SCREENSHOT = "Screenshot"
    ACTION_OCR = "OCR"
    ACTION_TEMPLATE_MATCH = "TemplateMatch"
    ACTION_COLOR_DETECT = "ColorDetect"
    ACTION_WAIT = "Wait"
    ACTION_IF = "If"
    ACTION_ELIF = "Elif"
    ACTION_ELSE = "Else"
    ACTION_END = "End"
    ACTION_LOOP = "Loop"
    ACTION_BREAK = "Break"
    ACTION_CONTINUE = "Continue"
    ACTION_SET = "Set"
    TASK_START = "TaskStart"
    TASK_END = "TaskEnd"

    def __init__(self):
        self._source: str = ""
        self._pipeline: list[dict[str, Any]] = []
        self._variables: dict[str, Any] = {}
        self._block_stack: list[dict[str, Any]] = []  # Tracks if/loop blocks

    def compile(self, source: str) -> list[dict[str, Any]]:
        """Compile DSL source string into pipeline action list.

        Args:
            source: DSL source code string (may be multi-line).

        Returns:
            List of action dictionaries compatible with PipelineEngine nodes.

        Raises:
            DSLCompileError: If source contains syntax or semantic errors
                (unbalanced if/end, malformed conditions, etc.).
        """
        self._source = source
        self._pipeline = []
        self._variables = {}
        self._block_stack = []

        lines = source.splitlines()
        for idx, raw_line in enumerate(lines, start=1):
            # Strip trailing comments (but preserve # inside strings)
            line = self._strip_trailing_comment(raw_line).strip()
            if not line or line.startswith("#"):
                continue

            try:
                self._parse_line(line, idx)
            except DSLCompileError:
                raise
            except Exception as exc:
                raise DSLCompileError(
                    f"Line {idx}: parse error: {exc}", line=idx
                ) from exc

        # Check all blocks are closed
        if self._block_stack:
            unclosed = self._block_stack[-1]
            kind = unclosed.get("kind", "?")
            line = unclosed.get("line", "?")
            raise DSLCompileError(
                f"Unclosed block '{kind}' started at line {line}"
            )

        return self._pipeline

    def _strip_trailing_comment(self, line: str) -> str:
        """Remove trailing # comment from a line, preserving # inside strings.

        Args:
            line: Raw line text.

        Returns:
            Line with trailing comment removed.
        """
        in_string = False
        string_char = ""
        for i, ch in enumerate(line):
            if ch in ('"', "'") and not in_string:
                in_string = True
                string_char = ch
            elif ch == string_char and in_string:
                in_string = False
            elif ch == "#" and not in_string:
                return line[:i]
        return line

    def _parse_line(self, line: str, line_num: int) -> None:
        """Parse a single DSL line and append action(s) to pipeline.

        Dispatches to variable assignment, block control, or action parsing.

        Args:
            line: Stripped DSL line (no leading/trailing whitespace).
            line_num: 1-based line number for error reporting.
        """
        # Variable assignment: set name = value
        set_match = _SET_RE.match(line)
        if set_match:
            self._handle_set(set_match.group(1), set_match.group(2), line_num)
            return

        # Block control keywords
        lower = line.lower()
        if lower.startswith("if "):
            self._handle_if(line[3:].strip(), line_num)
            return
        if lower.startswith("elif "):
            self._handle_elif(line[5:].strip(), line_num)
            return
        if lower == "else":
            self._handle_else(line_num)
            return
        if lower == "end":
            self._handle_end(line_num)
            return
        if lower.startswith("loop"):
            self._handle_loop(line[4:].strip(), line_num)
            return
        if lower == "break":
            self._append_action({"type": self.ACTION_BREAK})
            return
        if lower == "continue":
            self._append_action({"type": self.ACTION_CONTINUE})
            return

        # Regular action: func(args)
        action = self._parse_action(line, line_num)
        if action is not None:
            self._append_action(action)

    def _handle_set(self, name: str, value_expr: str, line_num: int) -> None:
        """Handle variable assignment: set name = value.

        Values may be: int, float, quoted string, or ${other_var} reference.

        Args:
            name: Variable name.
            value_expr: Raw value expression string.
            line_num: Line number for error reporting.
        """
        value = self._eval_value(value_expr)
        self._variables[name] = value
        self._append_action({
            "type": self.ACTION_SET,
            "name": name,
            "value": value,
        })

    def _handle_if(self, cond_expr: str, line_num: int) -> None:
        """Handle if statement: opens a new if block on the block stack.

        Args:
            cond_expr: Condition expression string (e.g. "${x} == 1").
            line_num: Line number for error reporting.
        """
        condition = self._eval_condition(cond_expr)
        block = {
            "kind": "if",
            "line": line_num,
            "branches": [{"condition": condition, "actions": []}],
            "current_branch": 0,
            "else_actions": None,
        }
        self._block_stack.append(block)
        self._append_action({"type": self.ACTION_IF, "condition": condition})

    def _handle_elif(self, cond_expr: str, line_num: int) -> None:
        """Handle elif statement: adds a new branch to the current if block.

        Args:
            cond_expr: Condition expression string.

        Raises:
            DSLCompileError: If not inside an if block.
        """
        if not self._block_stack or self._block_stack[-1]["kind"] != "if":
            raise DSLCompileError(f"Line {line_num}: 'elif' outside 'if' block")
        condition = self._eval_condition(cond_expr)
        block = self._block_stack[-1]
        block["branches"].append({"condition": condition, "actions": []})
        block["current_branch"] = len(block["branches"]) - 1
        self._append_action({"type": self.ACTION_ELIF, "condition": condition})

    def _handle_else(self, line_num: int) -> None:
        """Handle else statement: marks else branch active in current if block.

        Args:
            line_num: Line number for error reporting.

        Raises:
            DSLCompileError: If not inside an if block, or else already defined.
        """
        if not self._block_stack or self._block_stack[-1]["kind"] != "if":
            raise DSLCompileError(f"Line {line_num}: 'else' outside 'if' block")
        block = self._block_stack[-1]
        if block["else_actions"] is not None:
            raise DSLCompileError(f"Line {line_num}: duplicate 'else' in if block")
        block["else_actions"] = []
        block["current_branch"] = -1  # Sentinel for else
        self._append_action({"type": self.ACTION_ELSE})

    def _handle_end(self, line_num: int) -> None:
        """Handle end statement: closes the innermost if/loop block.

        Args:
            line_num: Line number for error reporting.

        Raises:
            DSLCompileError: If no block is open.
        """
        if not self._block_stack:
            raise DSLCompileError(f"Line {line_num}: 'end' without matching if/loop")
        self._block_stack.pop()
        self._append_action({"type": self.ACTION_END})

    def _handle_loop(self, args: str, line_num: int) -> None:
        """Handle loop statement: opens a new loop block.

        Supported forms:
        - loop N  (fixed count, N is int or ${var})
        - loop while <cond>  (condition checked each iteration)
        - loop over ${list_var}  (iterate list elements)

        Args:
            args: Loop arguments string (after 'loop' keyword).
            line_num: Line number for error reporting.
        """
        args = args.strip()
        loop_spec: dict[str, Any] = {"type": self.ACTION_LOOP}

        if not args:
            raise DSLCompileError(f"Line {line_num}: 'loop' requires arguments (N / while <cond> / over <var>)")

        lower_args = args.lower()
        if lower_args.startswith("while "):
            cond_expr = args[6:].strip()
            loop_spec["mode"] = "while"
            loop_spec["condition"] = self._eval_condition(cond_expr)
        elif lower_args.startswith("over "):
            var_ref = args[5:].strip()
            var_name = self._extract_var_name(var_ref)
            if not var_name:
                raise DSLCompileError(
                    f"Line {line_num}: 'loop over' expects a variable reference, got: {var_ref}"
                )
            loop_spec["mode"] = "over"
            loop_spec["variable"] = var_name
        else:
            # Fixed count: loop N
            count = self._eval_value(args)
            if not isinstance(count, int) or count < 0:
                raise DSLCompileError(
                    f"Line {line_num}: loop count must be non-negative integer, got: {count!r}"
                )
            loop_spec["mode"] = "count"
            loop_spec["count"] = count

        block = {"kind": "loop", "line": line_num, "spec": loop_spec}
        self._block_stack.append(block)
        self._append_action(loop_spec)

    def _parse_action(self, line: str, line_num: int) -> dict[str, Any] | None:
        """Parse a single action line into an action dict.

        Supports basic syntax:
            click(x, y)
            swipe(x1, y1, x2, y2, duration=300)
            key_press("enter")
            text_input("hello")
            screenshot()
            wait(1000)

        Args:
            line: Stripped DSL line.
            line_num: Line number for error reporting.

        Returns:
            Action dict, or None for unrecognized lines.
        """
        if "(" not in line or ")" not in line:
            return None

        func_name = line[: line.index("(")].strip()
        args_str = line[line.index("(") + 1 : line.rindex(")")].strip()

        args, kwargs = self._parse_args(args_str, line_num)

        action_map = {
            "click": self.ACTION_CLICK,
            "swipe": self.ACTION_SWIPE,
            "key_press": self.ACTION_KEY_PRESS,
            "keypress": self.ACTION_KEY_PRESS,
            "text_input": self.ACTION_TEXT_INPUT,
            "textinput": self.ACTION_TEXT_INPUT,
            "screenshot": self.ACTION_SCREENSHOT,
            "wait": self.ACTION_WAIT,
        }

        action_type = action_map.get(func_name.lower())
        if action_type is None:
            return None

        # Interpolate variables in args and kwargs
        args = [self._interpolate(a) for a in args]
        kwargs = {k: self._interpolate(v) for k, v in kwargs.items()}

        result: dict[str, Any] = {"type": action_type}
        if args:
            result["args"] = args
        if kwargs:
            result.update(kwargs)

        return result

    def _append_action(self, action: dict[str, Any]) -> None:
        """Append an action to the pipeline.

        Args:
            action: Action dict to append.
        """
        self._pipeline.append(action)

    @staticmethod
    def _parse_args(args_str: str, line_num: int = 0) -> tuple[list, dict]:
        """Parse argument string into positional and keyword arguments.

        Handles nested parentheses, quoted strings, and comma separation.

        Args:
            args_str: Raw argument string between parentheses.
            line_num: Line number for error reporting.

        Returns:
            Tuple of (positional_args_list, kwargs_dict).
        """
        args: list = []
        kwargs: dict = {}

        if not args_str:
            return args, kwargs

        parts = []
        current = ""
        paren_depth = 0
        in_string = False
        string_char = ""

        for ch in args_str:
            if ch in ('"', "'") and not in_string:
                in_string = True
                string_char = ch
                current += ch
            elif ch == string_char and in_string:
                in_string = False
                current += ch
            elif ch == "(" and not in_string:
                paren_depth += 1
                current += ch
            elif ch == ")" and not in_string:
                paren_depth -= 1
                current += ch
            elif ch == "," and not in_string and paren_depth == 0:
                parts.append(current.strip())
                current = ""
            else:
                current += ch

        if current.strip():
            parts.append(current.strip())

        for part in parts:
            if "=" in part and not part.startswith(("'", '"')):
                eq_idx = part.index("=")
                key = part[:eq_idx].strip()
                val = part[eq_idx + 1 :].strip()
                kwargs[key] = DSLCompiler._coerce_value(val)
            else:
                val = part.strip()
                args.append(DSLCompiler._coerce_value(val))

        return args, kwargs

    @staticmethod
    def _coerce_value(val_str: str) -> Any:
        """Coerce a raw string value to int/float/str.

        Strips surrounding quotes for strings. Attempts int then float
        conversion; falls back to raw string if neither matches.

        Args:
            val_str: Raw value string (may be quoted).

        Returns:
            Coerced value (int, float, or str).
        """
        val = val_str.strip().strip("'\"")
        try:
            return int(val)
        except ValueError:
            try:
                return float(val)
            except ValueError:
                return val

    def _eval_value(self, expr: str) -> Any:
        """Evaluate a value expression to a Python value.

        Supports: int, float, quoted string, ${var} reference.

        Args:
            expr: Value expression string.

        Returns:
            Evaluated value (int, float, str, or referenced variable value).
        """
        expr = expr.strip()
        # Variable reference: ${name}
        var_name = self._extract_var_name(expr)
        if var_name is not None:
            if var_name not in self._variables:
                raise DSLCompileError(f"Undefined variable: {var_name}")
            return self._variables[var_name]
        return self._coerce_value(expr)

    def _eval_condition(self, cond_expr: str) -> dict[str, Any]:
        """Evaluate a condition expression to a dict structure.

        Supported operators: ==, !=, <, >, <=, >=

        Args:
            cond_expr: Condition expression string (e.g. "${x} == 1").

        Returns:
            Dict with "lhs", "op", "rhs" keys.

        Raises:
            DSLCompileError: If condition syntax is invalid.
        """
        match = _COND_RE.match(cond_expr.strip())
        if not match:
            # Single-value condition (truthy check)
            return {
                "lhs": self._interpolate_str(cond_expr.strip()),
                "op": "truthy",
                "rhs": None,
            }
        lhs = self._interpolate_str(match.group(1).strip())
        op = match.group(2)
        rhs = self._interpolate_str(match.group(3).strip())
        return {"lhs": lhs, "op": op, "rhs": rhs}

    def _interpolate(self, value: Any) -> Any:
        """Interpolate ${var} references in a value.

        For strings, replaces all ${var} occurrences with variable values.
        For non-strings, returns unchanged.

        Args:
            value: Value to interpolate.

        Returns:
            Interpolated value.
        """
        if isinstance(value, str):
            return self._interpolate_str(value)
        return value

    def _interpolate_str(self, s: str) -> str:
        """Replace ${var} and $var references in a string with values.

        Args:
            s: String potentially containing variable references.

        Returns:
            String with variables substituted. Unknown variables are left
            as-is (not raised) to allow forward references in conditions.
        """
        def replacer(m: re.Match) -> str:
            name = m.group(1) or m.group(2)
            if name in self._variables:
                return str(self._variables[name])
            return m.group(0)  # Leave unchanged if undefined

        return _VAR_INTERP_RE.sub(replacer, s)

    @staticmethod
    def _extract_var_name(expr: str) -> str | None:
        """Extract variable name from ${name} or $name expression.

        Args:
            expr: Expression string.

        Returns:
            Variable name if expr is a pure variable reference, else None.
        """
        expr = expr.strip()
        m = _VAR_INTERP_RE.fullmatch(expr)
        if m:
            return m.group(1) or m.group(2)
        return None

    def to_pipeline_dict(self) -> dict[str, Any]:
        """Export compiled pipeline as dictionary.

        Returns:
            Dictionary with pipeline metadata, action list, and variables.
        """
        return {
            "version": "1.1",  # Bumped for N126-F3 features
            "actions": self._pipeline,
            "action_count": len(self._pipeline),
            "variables": dict(self._variables),
        }

    # Backward compatibility: expose variables for inspection
    @property
    def variables(self) -> dict[str, Any]:
        """Return a copy of currently-defined variables."""
        return dict(self._variables)


def dsl_to_pipeline(source: str) -> list[dict[str, Any]]:
    """Convenience function: compile DSL source to pipeline action list.

    Args:
        source: DSL source code string.

    Returns:
        Compiled pipeline action list.
    """
    compiler = DSLCompiler()
    return compiler.compile(source)


def dsl_to_pipeline_dict(source: str) -> dict[str, Any]:
    """Convenience function: compile DSL source to pipeline dictionary.

    Args:
        source: DSL source code string.

    Returns:
        Full pipeline dictionary with metadata.
    """
    compiler = DSLCompiler()
    compiler.compile(source)
    return compiler.to_pipeline_dict()
