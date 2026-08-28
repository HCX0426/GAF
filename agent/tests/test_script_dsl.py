"""DSLCompiler unit tests (N126-F3).

Covers:
- Backward compatibility: basic actions (click/swipe/wait/etc.)
- Variable assignment and interpolation
- Conditional branches (if/elif/else/end)
- Loops (loop N / loop while / loop over / break / continue)
- Comments (full-line # and trailing #)
- Error handling (unclosed blocks, elif outside if, etc.)
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.script_dsl import (
    DSLCompileError,
    DSLCompiler,
    dsl_to_pipeline,
    dsl_to_pipeline_dict,
)

pytestmark = pytest.mark.unit

# ============================================================
# Backward compatibility: basic actions
# ============================================================

class TestBasicActions:
    """Existing single-line action parsing must still work."""

    def test_click(self):
        result = dsl_to_pipeline("click(100, 200)")
        assert len(result) == 1
        assert result[0]["type"] == "Click"
        assert result[0]["args"] == [100, 200]

    def test_swipe_with_kwargs(self):
        result = dsl_to_pipeline('swipe(100, 200, 300, 400, duration=500)')
        assert result[0]["type"] == "Swipe"
        assert result[0]["args"] == [100, 200, 300, 400]
        assert result[0]["duration"] == 500

    def test_text_input_string(self):
        result = dsl_to_pipeline('text_input("hello")')
        assert result[0]["type"] == "TextInput"
        assert result[0]["args"] == ["hello"]

    def test_wait(self):
        result = dsl_to_pipeline("wait(1000)")
        assert result[0]["type"] == "Wait"
        assert result[0]["args"] == [1000]

    def test_multiple_actions(self):
        result = dsl_to_pipeline("click(1, 1)\nclick(2, 2)")
        assert len(result) == 2
        assert result[0]["args"] == [1, 1]
        assert result[1]["args"] == [2, 2]

    def test_empty_source(self):
        assert dsl_to_pipeline("") == []

    def test_comments_only(self):
        result = dsl_to_pipeline("# comment 1\n# comment 2\n")
        assert result == []


# ============================================================
# Variable assignment and interpolation (N126-F3)
# ============================================================

class TestVariables:
    """Variable assignment and ${var} interpolation."""

    def test_set_int(self):
        compiler = DSLCompiler()
        compiler.compile('set x = 42')
        assert compiler.variables["x"] == 42

    def test_set_string(self):
        compiler = DSLCompiler()
        compiler.compile('set name = "admin"')
        assert compiler.variables["name"] == "admin"

    def test_set_float(self):
        compiler = DSLCompiler()
        compiler.compile('set pi = 3.14')
        assert compiler.variables["pi"] == 3.14

    def test_set_from_var_reference(self):
        compiler = DSLCompiler()
        compiler.compile('set x = 10\nset y = ${x}')
        assert compiler.variables["y"] == 10

    def test_interpolation_in_text_input(self):
        result = dsl_to_pipeline('set name = "admin"\ntext_input(${name})')
        assert result[1]["args"] == ["admin"]

    def test_interpolation_partial_string(self):
        result = dsl_to_pipeline('set user = "bob"\ntext_input("hello_${user}_end")')
        assert result[1]["args"] == ["hello_bob_end"]

    def test_undefined_variable_in_set(self):
        with pytest.raises(DSLCompileError, match="Undefined variable"):
            dsl_to_pipeline('set y = ${undefined_var}')

    def test_unknown_var_left_unchanged_in_action(self):
        """In actions (not set), unknown ${var} is left as-is."""
        result = dsl_to_pipeline('text_input(${unknown})')
        assert result[0]["args"] == ["${unknown}"]


# ============================================================
# Conditional branches (N126-F3)
# ============================================================

class TestIfBranches:
    """if/elif/else/end conditional blocks."""

    def test_simple_if(self):
        result = dsl_to_pipeline('if ${x} == 1\nclick(100, 100)\nend')
        # Should produce: If action, Click action, End action
        types = [a["type"] for a in result]
        assert "If" in types
        assert "Click" in types
        assert "End" in types

    def test_if_else(self):
        result = dsl_to_pipeline(
            'if ${x} == 1\n'
            '  click(100, 100)\n'
            'else\n'
            '  click(200, 200)\n'
            'end'
        )
        types = [a["type"] for a in result]
        assert types.count("If") == 1
        assert types.count("Else") == 1
        assert types.count("End") == 1

    def test_if_elif_else(self):
        result = dsl_to_pipeline(
            'if ${x} == 1\n'
            '  click(100, 100)\n'
            'elif ${x} == 2\n'
            '  click(200, 200)\n'
            'else\n'
            '  click(300, 300)\n'
            'end'
        )
        types = [a["type"] for a in result]
        assert types.count("If") == 1
        assert types.count("Elif") == 1
        assert types.count("Else") == 1
        assert types.count("End") == 1

    def test_if_condition_operators(self):
        """All 6 comparison operators should parse."""
        for op in ["==", "!=", "<", ">", "<=", ">="]:
            result = dsl_to_pipeline(f'if ${{x}} {op} 1\nclick(1, 1)\nend')
            if_action = next(a for a in result if a["type"] == "If")
            assert if_action["condition"]["op"] == op

    def test_unclosed_if_raises(self):
        with pytest.raises(DSLCompileError, match="Unclosed block"):
            dsl_to_pipeline('if ${x} == 1\nclick(1, 1)')

    def test_elif_outside_if_raises(self):
        with pytest.raises(DSLCompileError, match="'elif' outside 'if'"):
            dsl_to_pipeline('elif ${x} == 1\nclick(1, 1)\nend')

    def test_else_outside_if_raises(self):
        with pytest.raises(DSLCompileError, match="'else' outside 'if'"):
            dsl_to_pipeline('else\nclick(1, 1)\nend')

    def test_duplicate_else_raises(self):
        with pytest.raises(DSLCompileError, match="duplicate 'else'"):
            dsl_to_pipeline(
                'if ${x} == 1\n'
                '  click(1, 1)\n'
                'else\n'
                '  click(2, 2)\n'
                'else\n'
                '  click(3, 3)\n'
                'end'
            )

    def test_end_without_if_raises(self):
        with pytest.raises(DSLCompileError, match="'end' without matching"):
            dsl_to_pipeline('end')

    def test_nested_if(self):
        result = dsl_to_pipeline(
            'if ${x} == 1\n'
            '  if ${y} == 2\n'
            '    click(100, 100)\n'
            '  end\n'
            'end'
        )
        types = [a["type"] for a in result]
        assert types.count("If") == 2
        assert types.count("End") == 2


# ============================================================
# Loops (N126-F3)
# ============================================================

class TestLoops:
    """loop N / loop while / loop over / break / continue."""

    def test_loop_count(self):
        result = dsl_to_pipeline('loop 3\nclick(100, 100)\nend')
        loop_action = next(a for a in result if a["type"] == "Loop")
        assert loop_action["mode"] == "count"
        assert loop_action["count"] == 3

    def test_loop_while(self):
        result = dsl_to_pipeline('loop while ${x} < 10\nclick(1, 1)\nend')
        loop_action = next(a for a in result if a["type"] == "Loop")
        assert loop_action["mode"] == "while"
        assert loop_action["condition"]["op"] == "<"

    def test_loop_over(self):
        result = dsl_to_pipeline(
            'set items = "list"\n'
            'loop over ${items}\n'
            '  click(1, 1)\n'
            'end'
        )
        loop_action = next(a for a in result if a["type"] == "Loop")
        assert loop_action["mode"] == "over"
        assert loop_action["variable"] == "items"

    def test_loop_break(self):
        result = dsl_to_pipeline('loop 5\nbreak\nend')
        types = [a["type"] for a in result]
        assert "Break" in types

    def test_loop_continue(self):
        result = dsl_to_pipeline('loop 5\ncontinue\nend')
        types = [a["type"] for a in result]
        assert "Continue" in types

    def test_loop_count_from_var(self):
        result = dsl_to_pipeline('set n = 5\nloop ${n}\nclick(1, 1)\nend')
        loop_action = next(a for a in result if a["type"] == "Loop")
        assert loop_action["mode"] == "count"
        assert loop_action["count"] == 5

    def test_loop_negative_count_raises(self):
        with pytest.raises(DSLCompileError, match="non-negative integer"):
            dsl_to_pipeline('loop -1\nclick(1, 1)\nend')

    def test_loop_no_args_raises(self):
        with pytest.raises(DSLCompileError, match="requires arguments"):
            dsl_to_pipeline('loop\nclick(1, 1)\nend')

    def test_loop_over_no_var_raises(self):
        with pytest.raises(DSLCompileError, match="expects a variable reference"):
            dsl_to_pipeline('loop over not_a_var\nclick(1, 1)\nend')

    def test_unclosed_loop_raises(self):
        with pytest.raises(DSLCompileError, match="Unclosed block"):
            dsl_to_pipeline('loop 3\nclick(1, 1)')

    def test_nested_loops(self):
        result = dsl_to_pipeline(
            'loop 3\n'
            '  loop 2\n'
            '    click(1, 1)\n'
            '  end\n'
            'end'
        )
        types = [a["type"] for a in result]
        assert types.count("Loop") == 2
        assert types.count("End") == 2


# ============================================================
# Comments (N126-F3)
# ============================================================

class TestComments:
    """Full-line # comments and trailing # comments."""

    def test_full_line_comment(self):
        result = dsl_to_pipeline('# this is a comment\nclick(1, 1)')
        assert len(result) == 1
        assert result[0]["type"] == "Click"

    def test_trailing_comment(self):
        result = dsl_to_pipeline('click(1, 1)  # this is trailing')
        assert len(result) == 1
        assert result[0]["args"] == [1, 1]

    def test_comment_with_hash_in_string(self):
        """# inside a string literal should not start a comment."""
        result = dsl_to_pipeline('text_input("hash#symbol")')
        assert result[0]["args"] == ["hash#symbol"]

    def test_mixed_comments(self):
        source = (
            '# header comment\n'
            'click(1, 1)  # trailing\n'
            '# middle comment\n'
            'click(2, 2)\n'
        )
        result = dsl_to_pipeline(source)
        assert len(result) == 2


# ============================================================
# to_pipeline_dict and convenience functions
# ============================================================

class TestPipelineDict:
    """to_pipeline_dict and module-level convenience functions."""

    def test_to_pipeline_dict_has_version(self):
        d = dsl_to_pipeline_dict('click(1, 1)')
        assert d["version"] == "1.1"
        assert d["action_count"] == 1
        assert len(d["actions"]) == 1

    def test_to_pipeline_dict_includes_variables(self):
        d = dsl_to_pipeline_dict('set x = 42\nclick(${x}, ${x})')
        assert d["variables"]["x"] == 42

    def test_dsl_to_pipeline_returns_list(self):
        result = dsl_to_pipeline('click(1, 1)')
        assert isinstance(result, list)


# ============================================================
# Complex scripts (integration)
# ============================================================

class TestComplexScripts:
    """Multi-feature integration tests."""

    def test_login_flow(self):
        source = (
            '# Login flow\n'
            'set username = "admin"\n'
            'set password = "secret"\n'
            'click(100, 200)  # username field\n'
            'text_input(${username})\n'
            'click(100, 300)  # password field\n'
            'text_input(${password})\n'
            'click(200, 400)  # submit\n'
        )
        result = dsl_to_pipeline(source)
        # 2 set + 5 actions (click+input+click+input+click) = 7
        assert len(result) == 7
        assert result[0]["type"] == "Set"
        assert result[2]["args"] == [100, 200]
        assert result[3]["args"] == ["admin"]

    def test_loop_with_conditional(self):
        source = (
            'set counter = 0\n'
            'loop 5\n'
            '  if ${counter} == 3\n'
            '    break\n'
            '  end\n'
            '  click(1, 1)\n'
            'end\n'
        )
        result = dsl_to_pipeline(source)
        types = [a["type"] for a in result]
        assert "Set" in types
        assert "Loop" in types
        assert "If" in types
        assert "Break" in types
        assert "End" in types

    def test_branching_with_multiple_elif(self):
        source = (
            'if ${x} == 1\n'
            '  click(1, 1)\n'
            'elif ${x} == 2\n'
            '  click(2, 2)\n'
            'elif ${x} == 3\n'
            '  click(3, 3)\n'
            'else\n'
            '  click(0, 0)\n'
            'end\n'
        )
        result = dsl_to_pipeline(source)
        types = [a["type"] for a in result]
        assert types.count("Elif") == 2
