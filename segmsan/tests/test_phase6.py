"""Phase 6 tests: Simple statements parser.

Tests cover TAL Section 12 simple statements:
  Compound, Assignment (incl. multi-target), CALL, RETURN, GOTO,
  SCAN/RSCAN, STACK, STORE, USE, DROP, CODE, ASSERT, Labels, MOVE,
  null statement, and bare expression-as-statement.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from segmsan.lexer import Lexer
from segmsan.lexer import to_stmt_stream
from segmsan.transformers.stmt import parse_stmts
from segmsan.ast_nodes import (
    AssignStmt, CallStmt, CompoundStmt, GotoStmt, LabelStmt,
    ReturnStmt, ScanStmt, StackStmt, StoreStmt, UseStmt, DropStmt,
    CodeStmt, AssertStmt, MoveStmt, OtherStmt,
    VarExpr, LiteralExpr, BinOpExpr, IndexExpr, FieldExpr,
    AddressOfExpr, CallExpr, UnaryExpr,
)


_PASS = []
_FAIL = []


def _parse(source: str) -> list:
    toks = Lexer(source).tokenize()
    return parse_stmts(iter(list(to_stmt_stream(toks))))


def _run(name: str, fn):
    try:
        fn()
        _PASS.append(name)
    except Exception as e:
        _FAIL.append((name, e))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _v(n): return VarExpr(name=n)
def _lit(v): return LiteralExpr(value=v)


def _eq(a, b) -> bool:
    """Structural equality ignoring loc."""
    if type(a) != type(b):
        return False
    if isinstance(a, VarExpr):
        return a.name == b.name
    if isinstance(a, LiteralExpr):
        return a.value == b.value
    if isinstance(a, BinOpExpr):
        return a.op == b.op and _eq(a.left, b.left) and _eq(a.right, b.right)
    if isinstance(a, UnaryExpr):
        return a.op == b.op and _eq(a.inner, b.inner)
    if isinstance(a, IndexExpr):
        return _eq(a.array, b.array) and _eq(a.index, b.index)
    if isinstance(a, FieldExpr):
        return a.field_name == b.field_name and _eq(a.obj, b.obj)
    if isinstance(a, AddressOfExpr):
        return _eq(a.inner, b.inner)
    if isinstance(a, CallExpr):
        return a.name == b.name and len(a.args) == len(b.args)
    if isinstance(a, AssignStmt):
        return (len(a.targets) == len(b.targets) and
                all(_eq(x, y) for x, y in zip(a.targets, b.targets)) and
                _eq(a.source, b.source))
    if isinstance(a, CallStmt):
        return a.name == b.name and len(a.args) == len(b.args)
    if isinstance(a, GotoStmt):
        return a.label == b.label
    if isinstance(a, ReturnStmt):
        return (_maybe_eq(a.value, b.value) and
                _maybe_eq(a.cc_expression, b.cc_expression))
    if isinstance(a, ScanStmt):
        return (a.direction == b.direction and a.mode == b.mode and
                _eq(a.variable, b.variable) and _eq(a.test_char, b.test_char))
    if isinstance(a, StackStmt):
        return len(a.values) == len(b.values)
    if isinstance(a, StoreStmt):
        return len(a.variables) == len(b.variables)
    if isinstance(a, UseStmt):
        return a.identifiers == b.identifiers
    if isinstance(a, DropStmt):
        return a.identifiers == b.identifiers
    if isinstance(a, CodeStmt):
        return len(a.instructions) == len(b.instructions)
    if isinstance(a, AssertStmt):
        return True  # presence check
    if isinstance(a, CompoundStmt):
        return (len(a.body) == len(b.body) and
                all(_eq(x, y) for x, y in zip(a.body, b.body)))
    if isinstance(a, LabelStmt):
        return a.name == b.name
    if isinstance(a, MoveStmt):
        return a.direction == b.direction
    if isinstance(a, OtherStmt):
        return a.raw == b.raw
    return a == b


def _maybe_eq(a, b) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return _eq(a, b)


# ─────────────────────────────────────────────────────────────────────────────
# Grupo 1: Compound Statements
# ─────────────────────────────────────────────────────────────────────────────

def test_compound_empty():
    r = _parse("BEGIN END")
    assert len(r) == 1 and isinstance(r[0], CompoundStmt)
    assert r[0].body == []

def test_compound_single():
    r = _parse("BEGIN x := 1 END")
    assert isinstance(r[0], CompoundStmt)
    assert len(r[0].body) == 1
    assert isinstance(r[0].body[0], AssignStmt)

def test_compound_multiple():
    r = _parse("BEGIN x := 1; y := 2; z := 3 END")
    assert isinstance(r[0], CompoundStmt)
    assert len(r[0].body) == 3

def test_compound_nested():
    r = _parse("BEGIN BEGIN x := 1 END; y := 2 END")
    assert isinstance(r[0], CompoundStmt)
    assert isinstance(r[0].body[0], CompoundStmt)
    assert isinstance(r[0].body[1], AssignStmt)

def test_compound_trailing_semi():
    r = _parse("BEGIN x := 1; y := 2; END")
    assert isinstance(r[0], CompoundStmt)
    assert len(r[0].body) == 2

# ─────────────────────────────────────────────────────────────────────────────
# Grupo 2: Assignment
# ─────────────────────────────────────────────────────────────────────────────

def test_assign_simple():
    r = _parse("x := 1")
    s = r[0]
    assert isinstance(s, AssignStmt)
    assert len(s.targets) == 1
    assert _eq(s.targets[0], _v("x"))
    assert _eq(s.source, _lit(1))

def test_assign_multi_target():
    r = _parse("x, y := 0")
    s = r[0]
    assert isinstance(s, AssignStmt)
    assert len(s.targets) == 2
    assert _eq(s.targets[0], _v("x"))
    assert _eq(s.targets[1], _v("y"))
    assert _eq(s.source, _lit(0))

def test_assign_triple_target():
    r = _parse("a, b, c := 42")
    s = r[0]
    assert isinstance(s, AssignStmt)
    assert len(s.targets) == 3

def test_assign_expression():
    r = _parse("result := a + b")
    s = r[0]
    assert isinstance(s, AssignStmt)
    assert isinstance(s.source, BinOpExpr)
    assert s.source.op == "+"

def test_assign_indexed():
    r = _parse("arr[i] := val")
    s = r[0]
    assert isinstance(s, AssignStmt)
    assert isinstance(s.targets[0], IndexExpr)

def test_assign_field():
    r = _parse("rec.field := 99")
    s = r[0]
    assert isinstance(s, AssignStmt)
    assert isinstance(s.targets[0], FieldExpr)
    assert s.targets[0].field_name == "field"

def test_assign_deref_target():
    r = _parse("ptr := @data")
    s = r[0]
    assert isinstance(s, AssignStmt)
    assert isinstance(s.source, AddressOfExpr)

def test_assign_chained_index():
    r = _parse("mat[row][col] := 0")
    s = r[0]
    assert isinstance(s, AssignStmt)
    assert isinstance(s.targets[0], IndexExpr)

def test_assign_multi_indexed():
    r = _parse("buf[0], buf[1] := 0")
    s = r[0]
    assert isinstance(s, AssignStmt)
    assert len(s.targets) == 2
    assert isinstance(s.targets[0], IndexExpr)

def test_assign_call_result():
    r = _parse("x := my_func(a, b)")
    s = r[0]
    assert isinstance(s, AssignStmt)
    assert isinstance(s.source, CallExpr)
    assert s.source.name == "my_func"

# ─────────────────────────────────────────────────────────────────────────────
# Grupo 3: CALL
# ─────────────────────────────────────────────────────────────────────────────

def test_call_explicit_no_args():
    r = _parse("CALL my_proc")
    s = r[0]
    assert isinstance(s, CallStmt)
    assert s.name == "my_proc"
    assert s.args == []

def test_call_explicit_with_args():
    r = _parse("CALL my_proc(a, b, c)")
    s = r[0]
    assert isinstance(s, CallStmt)
    assert s.name == "my_proc"
    assert len(s.args) == 3

def test_call_bare_no_parens():
    r = _parse("error_handler")
    s = r[0]
    assert isinstance(s, CallStmt)
    assert s.name == "error_handler"
    assert s.args == []

def test_call_bare_with_args():
    r = _parse("my_proc(x, y)")
    s = r[0]
    assert isinstance(s, CallStmt)
    assert s.name == "my_proc"
    assert len(s.args) == 2

def test_call_explicit_empty_parens():
    r = _parse("CALL do_work()")
    s = r[0]
    assert isinstance(s, CallStmt)
    assert s.name == "do_work"
    assert s.args == []

def test_call_param_pair():
    r = _parse("CALL write(buf: len)")
    s = r[0]
    assert isinstance(s, CallStmt)
    assert s.name == "write"
    assert len(s.param_pairs) == 1

def test_call_mixed_args():
    r = _parse("CALL my_proc(a, b: len, c)")
    s = r[0]
    assert isinstance(s, CallStmt)
    assert len(s.args) + len(s.param_pairs) == 3

def test_call_in_compound():
    r = _parse("BEGIN CALL init; CALL run(x) END")
    c = r[0]
    assert isinstance(c, CompoundStmt)
    assert len(c.body) == 2
    assert all(isinstance(s, CallStmt) for s in c.body)

# ─────────────────────────────────────────────────────────────────────────────
# Grupo 4: RETURN
# ─────────────────────────────────────────────────────────────────────────────

def test_return_bare():
    r = _parse("RETURN")
    s = r[0]
    assert isinstance(s, ReturnStmt)
    assert s.value is None
    assert s.cc_expression is None

def test_return_value():
    r = _parse("RETURN x + 1")
    s = r[0]
    assert isinstance(s, ReturnStmt)
    assert s.value is not None
    assert s.cc_expression is None

def test_return_cc_only():
    r = _parse("RETURN , cc_val")
    s = r[0]
    assert isinstance(s, ReturnStmt)
    assert s.value is None
    assert s.cc_expression is not None

def test_return_value_cc():
    r = _parse("RETURN x, cc_val")
    s = r[0]
    assert isinstance(s, ReturnStmt)
    assert s.value is not None
    assert s.cc_expression is not None

def test_return_zero():
    r = _parse("RETURN 0")
    s = r[0]
    assert isinstance(s, ReturnStmt)
    assert _eq(s.value, _lit(0))

# ─────────────────────────────────────────────────────────────────────────────
# Grupo 5: GOTO
# ─────────────────────────────────────────────────────────────────────────────

def test_goto_simple():
    r = _parse("GOTO done")
    s = r[0]
    assert isinstance(s, GotoStmt)
    assert s.label == "done"

def test_goto_in_compound():
    r = _parse("BEGIN x := 1; GOTO loop END")
    c = r[0]
    assert isinstance(c, CompoundStmt)
    assert isinstance(c.body[-1], GotoStmt)
    assert c.body[-1].label == "loop"

# ─────────────────────────────────────────────────────────────────────────────
# Grupo 6: SCAN / RSCAN
# ─────────────────────────────────────────────────────────────────────────────

def test_scan_while():
    r = _parse("SCAN buf WHILE 0")
    s = r[0]
    assert isinstance(s, ScanStmt)
    assert s.direction == "SCAN"
    assert s.mode == "WHILE"
    assert _eq(s.variable, _v("buf"))

def test_rscan_until():
    r = _parse("RSCAN buf UNTIL 255")
    s = r[0]
    assert isinstance(s, ScanStmt)
    assert s.direction == "RSCAN"
    assert s.mode == "UNTIL"

def test_scan_with_next_addr():
    r = _parse("SCAN buf WHILE 0 -> next_ptr")
    s = r[0]
    assert isinstance(s, ScanStmt)
    assert s.next_addr is not None
    assert _eq(s.next_addr, _v("next_ptr"))

def test_scan_indexed():
    r = _parse("SCAN buf[0] WHILE ch")
    s = r[0]
    assert isinstance(s, ScanStmt)
    assert isinstance(s.variable, IndexExpr)

def test_scan_until_expr():
    r = _parse("SCAN str UNTIL separator_char")
    s = r[0]
    assert isinstance(s, ScanStmt)
    assert s.mode == "UNTIL"
    assert _eq(s.test_char, _v("separator_char"))

# ─────────────────────────────────────────────────────────────────────────────
# Grupo 7: STACK
# ─────────────────────────────────────────────────────────────────────────────

def test_stack_single():
    r = _parse("STACK a")
    s = r[0]
    assert isinstance(s, StackStmt)
    assert len(s.values) == 1
    assert _eq(s.values[0], _v("a"))

def test_stack_multiple():
    r = _parse("STACK a, b, c")
    s = r[0]
    assert isinstance(s, StackStmt)
    assert len(s.values) == 3

def test_stack_expression():
    r = _parse("STACK x + 1")
    s = r[0]
    assert isinstance(s, StackStmt)
    assert isinstance(s.values[0], BinOpExpr)

# ─────────────────────────────────────────────────────────────────────────────
# Grupo 8: STORE
# ─────────────────────────────────────────────────────────────────────────────

def test_store_single():
    r = _parse("STORE x")
    s = r[0]
    assert isinstance(s, StoreStmt)
    assert len(s.variables) == 1

def test_store_multiple():
    r = _parse("STORE a, b, c")
    s = r[0]
    assert isinstance(s, StoreStmt)
    assert len(s.variables) == 3

def test_store_indexed():
    r = _parse("STORE arr[i]")
    s = r[0]
    assert isinstance(s, StoreStmt)
    assert isinstance(s.variables[0], IndexExpr)

# ─────────────────────────────────────────────────────────────────────────────
# Grupo 9: USE / DROP
# ─────────────────────────────────────────────────────────────────────────────

def test_use_single():
    r = _parse("USE reg1")
    s = r[0]
    assert isinstance(s, UseStmt)
    assert s.identifiers == ["reg1"]

def test_use_multiple():
    r = _parse("USE reg1, reg2, reg3")
    s = r[0]
    assert isinstance(s, UseStmt)
    assert s.identifiers == ["reg1", "reg2", "reg3"]

def test_drop_single():
    r = _parse("DROP reg1")
    s = r[0]
    assert isinstance(s, DropStmt)
    assert s.identifiers == ["reg1"]

def test_drop_multiple():
    r = _parse("DROP reg1, reg2")
    s = r[0]
    assert isinstance(s, DropStmt)
    assert s.identifiers == ["reg1", "reg2"]

# ─────────────────────────────────────────────────────────────────────────────
# Grupo 10: CODE
# ─────────────────────────────────────────────────────────────────────────────

def test_code_single():
    r = _parse("CODE (17)")
    s = r[0]
    assert isinstance(s, CodeStmt)
    assert len(s.instructions) == 1

def test_code_multiple():
    r = _parse("CODE (17; 20; 37)")
    s = r[0]
    assert isinstance(s, CodeStmt)
    assert len(s.instructions) == 3

def test_code_multi_word():
    r = _parse("CODE (17 20; 37 40)")
    s = r[0]
    assert isinstance(s, CodeStmt)
    assert len(s.instructions) == 2
    assert "17" in s.instructions[0]
    assert "20" in s.instructions[0]

# ─────────────────────────────────────────────────────────────────────────────
# Grupo 11: ASSERT
# ─────────────────────────────────────────────────────────────────────────────

def test_assert_simple():
    r = _parse("ASSERT 0: x > 0")
    s = r[0]
    assert isinstance(s, AssertStmt)
    assert s.level is not None
    assert s.condition is not None

def test_assert_expression_level():
    r = _parse("ASSERT err_level: ptr <> 0")
    s = r[0]
    assert isinstance(s, AssertStmt)
    assert _eq(s.level, _v("err_level"))

# ─────────────────────────────────────────────────────────────────────────────
# Grupo 12: Labels
# ─────────────────────────────────────────────────────────────────────────────

def test_label_simple():
    r = _parse("loop: x := x + 1")
    s = r[0]
    assert isinstance(s, CompoundStmt)
    assert isinstance(s.body[0], LabelStmt)
    assert s.body[0].name == "loop"
    assert isinstance(s.body[1], AssignStmt)

def test_label_before_compound():
    r = _parse("main_body: BEGIN x := 1 END")
    s = r[0]
    assert isinstance(s, CompoundStmt)
    assert isinstance(s.body[0], LabelStmt)
    assert s.body[0].name == "main_body"
    assert isinstance(s.body[1], CompoundStmt)

def test_label_before_goto():
    r = _parse("exit_point: GOTO done")
    s = r[0]
    assert isinstance(s, CompoundStmt)
    assert isinstance(s.body[0], LabelStmt)
    assert isinstance(s.body[1], GotoStmt)

def test_label_in_compound():
    r = _parse("BEGIN loop: x := x + 1; GOTO loop END")
    c = r[0]
    assert isinstance(c, CompoundStmt)
    # First item is a labeled assign wrapped in CompoundStmt
    assert any(isinstance(s, CompoundStmt) or isinstance(s, LabelStmt)
               for s in c.body)

def test_label_multiple_in_list():
    r = _parse("start: x := 0; finish: y := 1")
    assert len(r) == 2
    assert all(isinstance(s, CompoundStmt) for s in r)
    assert r[0].body[0].name == "start"
    assert r[1].body[0].name == "finish"

# ─────────────────────────────────────────────────────────────────────────────
# Grupo 13: MOVE
# ─────────────────────────────────────────────────────────────────────────────

def test_move_lr_simple():
    r = _parse("dest ':=' src")
    s = r[0]
    assert isinstance(s, MoveStmt)
    assert s.direction == "LR"
    assert _eq(s.dest, _v("dest"))

def test_move_rl_simple():
    r = _parse("dest '=:' src")
    s = r[0]
    assert isinstance(s, MoveStmt)
    assert s.direction == "RL"

def test_move_lr_for_bytes():
    r = _parse("dst ':=' src FOR n BYTES")
    s = r[0]
    assert isinstance(s, MoveStmt)
    assert s.direction == "LR"
    assert s.unit == "BYTES"
    assert s.count is not None

def test_move_lr_for_words():
    r = _parse("dst ':=' src FOR n WORDS")
    s = r[0]
    assert isinstance(s, MoveStmt)
    assert s.unit == "WORDS"

def test_move_lr_for_elements():
    r = _parse("dst ':=' src FOR n ELEMENTS")
    s = r[0]
    assert isinstance(s, MoveStmt)
    assert s.unit == "ELEMENTS"

def test_move_lr_for_next_addr():
    r = _parse("dst ':=' src FOR n BYTES -> next")
    s = r[0]
    assert isinstance(s, MoveStmt)
    assert s.unit == "BYTES"
    assert s.next_addr is not None

def test_move_lr_for_no_unit():
    r = _parse("dst ':=' src FOR n")
    s = r[0]
    assert isinstance(s, MoveStmt)
    assert s.count is not None
    assert s.unit == ""

def test_move_lr_fill_list():
    r = _parse("dst ':=' [0, 1, 2]")
    s = r[0]
    assert isinstance(s, MoveStmt)
    assert s.direction == "LR"
    assert isinstance(s.source, list)

# ─────────────────────────────────────────────────────────────────────────────
# Grupo 14: Null statement and bare expressions
# ─────────────────────────────────────────────────────────────────────────────

def test_null_stmt_in_compound():
    r = _parse("BEGIN ; x := 1 END")
    c = r[0]
    assert isinstance(c, CompoundStmt)
    # Null SEMI is consumed by _stmt_item, not produced as a node
    # Only AssignStmt visible in body
    stmts = [s for s in c.body if isinstance(s, AssignStmt)]
    assert len(stmts) == 1

def test_null_stmt_multiple():
    r = _parse("BEGIN ; ; x := 1 END")
    c = r[0]
    assert isinstance(c, CompoundStmt)
    assigns = [s for s in c.body if isinstance(s, AssignStmt)]
    assert len(assigns) == 1

def test_bare_call_no_args():
    r = _parse("error_handler")
    s = r[0]
    assert isinstance(s, CallStmt)
    assert s.name == "error_handler"

def test_bare_call_with_args():
    r = _parse("write_line(buf, len)")
    s = r[0]
    assert isinstance(s, CallStmt)
    assert s.name == "write_line"
    assert len(s.args) == 2

def test_multiple_stmts_in_list():
    r = _parse("x := 1; y := 2; CALL my_proc")
    assert len(r) == 3
    assert isinstance(r[0], AssignStmt)
    assert isinstance(r[1], AssignStmt)
    assert isinstance(r[2], CallStmt)


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

_ALL_TESTS = [
    # Grupo 1: Compound
    ("test_compound_empty",          test_compound_empty),
    ("test_compound_single",         test_compound_single),
    ("test_compound_multiple",       test_compound_multiple),
    ("test_compound_nested",         test_compound_nested),
    ("test_compound_trailing_semi",  test_compound_trailing_semi),
    # Grupo 2: Assignment
    ("test_assign_simple",           test_assign_simple),
    ("test_assign_multi_target",     test_assign_multi_target),
    ("test_assign_triple_target",    test_assign_triple_target),
    ("test_assign_expression",       test_assign_expression),
    ("test_assign_indexed",          test_assign_indexed),
    ("test_assign_field",            test_assign_field),
    ("test_assign_deref_target",     test_assign_deref_target),
    ("test_assign_chained_index",    test_assign_chained_index),
    ("test_assign_multi_indexed",    test_assign_multi_indexed),
    ("test_assign_call_result",      test_assign_call_result),
    # Grupo 3: CALL
    ("test_call_explicit_no_args",   test_call_explicit_no_args),
    ("test_call_explicit_with_args", test_call_explicit_with_args),
    ("test_call_bare_no_parens",     test_call_bare_no_parens),
    ("test_call_bare_with_args",     test_call_bare_with_args),
    ("test_call_explicit_empty",     test_call_explicit_empty_parens),
    ("test_call_param_pair",         test_call_param_pair),
    ("test_call_mixed_args",         test_call_mixed_args),
    ("test_call_in_compound",        test_call_in_compound),
    # Grupo 4: RETURN
    ("test_return_bare",             test_return_bare),
    ("test_return_value",            test_return_value),
    ("test_return_cc_only",          test_return_cc_only),
    ("test_return_value_cc",         test_return_value_cc),
    ("test_return_zero",             test_return_zero),
    # Grupo 5: GOTO
    ("test_goto_simple",             test_goto_simple),
    ("test_goto_in_compound",        test_goto_in_compound),
    # Grupo 6: SCAN/RSCAN
    ("test_scan_while",              test_scan_while),
    ("test_rscan_until",             test_rscan_until),
    ("test_scan_with_next_addr",     test_scan_with_next_addr),
    ("test_scan_indexed",            test_scan_indexed),
    ("test_scan_until_expr",         test_scan_until_expr),
    # Grupo 7: STACK
    ("test_stack_single",            test_stack_single),
    ("test_stack_multiple",          test_stack_multiple),
    ("test_stack_expression",        test_stack_expression),
    # Grupo 8: STORE
    ("test_store_single",            test_store_single),
    ("test_store_multiple",          test_store_multiple),
    ("test_store_indexed",           test_store_indexed),
    # Grupo 9: USE/DROP
    ("test_use_single",              test_use_single),
    ("test_use_multiple",            test_use_multiple),
    ("test_drop_single",             test_drop_single),
    ("test_drop_multiple",           test_drop_multiple),
    # Grupo 10: CODE
    ("test_code_single",             test_code_single),
    ("test_code_multiple",           test_code_multiple),
    ("test_code_multi_word",         test_code_multi_word),
    # Grupo 11: ASSERT
    ("test_assert_simple",           test_assert_simple),
    ("test_assert_expression_level", test_assert_expression_level),
    # Grupo 12: Labels
    ("test_label_simple",            test_label_simple),
    ("test_label_before_compound",   test_label_before_compound),
    ("test_label_before_goto",       test_label_before_goto),
    ("test_label_in_compound",       test_label_in_compound),
    ("test_label_multiple",          test_label_multiple_in_list),
    # Grupo 13: MOVE
    ("test_move_lr_simple",          test_move_lr_simple),
    ("test_move_rl_simple",          test_move_rl_simple),
    ("test_move_lr_for_bytes",       test_move_lr_for_bytes),
    ("test_move_lr_for_words",       test_move_lr_for_words),
    ("test_move_lr_for_elements",    test_move_lr_for_elements),
    ("test_move_lr_for_next_addr",   test_move_lr_for_next_addr),
    ("test_move_lr_for_no_unit",     test_move_lr_for_no_unit),
    ("test_move_lr_fill_list",       test_move_lr_fill_list),
    # Grupo 14: Null / bare
    ("test_null_in_compound",        test_null_stmt_in_compound),
    ("test_null_multiple",           test_null_stmt_multiple),
    ("test_bare_call_no_args",       test_bare_call_no_args),
    ("test_bare_call_with_args",     test_bare_call_with_args),
    ("test_multiple_stmts",          test_multiple_stmts_in_list),
]


if __name__ == "__main__":
    for name, fn in _ALL_TESTS:
        _run(name, fn)

    total = len(_ALL_TESTS)
    passed = len(_PASS)
    failed = len(_FAIL)

    for name, err in _FAIL:
        print(f"  FAIL  {name}: {err}")
    for name in _PASS:
        print(f"  OK  {name}")

    print(f"\n{passed}/{total} passed, {failed} failed")
    if _FAIL:
        sys.exit(1)
