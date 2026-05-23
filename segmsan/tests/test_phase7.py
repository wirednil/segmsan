"""Phase 7 tests: Complex statements parser.

Tests cover TAL Section 12 complex statements:
  IF...THEN...ELSE, WHILE...DO, FOR (TO/DOWNTO/BY/STEP),
  DO...UNTIL, CASE (labeled, unlabeled, OTHERWISE).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from segmsan.lexer import Lexer
from segmsan.lexer import to_stmt_stream
from segmsan.transformers.stmt import parse_stmts_complex
from segmsan.ast_nodes import (
    AssignStmt, CallStmt, CompoundStmt, GotoStmt, LabelStmt,
    ReturnStmt, OtherStmt,
    IfStmt, WhileStmt, ForStmt, DoStmt, CaseStmt, CaseAlternative, CaseLabel,
    VarExpr, LiteralExpr, BinOpExpr, UnaryExpr, ConditionCodeExpr,
)


_PASS = []
_FAIL = []


def _parse(source: str) -> list:
    toks = Lexer(source).tokenize()
    return parse_stmts_complex(iter(list(to_stmt_stream(toks))))


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
    if isinstance(a, ConditionCodeExpr):
        return a.op == b.op
    if isinstance(a, AssignStmt):
        return (len(a.targets) == len(b.targets) and
                all(_eq(x, y) for x, y in zip(a.targets, b.targets)) and
                _eq(a.source, b.source))
    if isinstance(a, CallStmt):
        return a.name == b.name and len(a.args) == len(b.args)
    if isinstance(a, GotoStmt):
        return a.label == b.label
    if isinstance(a, ReturnStmt):
        return True
    if isinstance(a, CompoundStmt):
        return (len(a.body) == len(b.body) and
                all(_eq(x, y) for x, y in zip(a.body, b.body)))
    if isinstance(a, LabelStmt):
        return a.name == b.name
    if isinstance(a, OtherStmt):
        return a.raw == b.raw
    if isinstance(a, IfStmt):
        return (_eq(a.condition, b.condition) and
                _eq_list(a.then_body, b.then_body) and
                _eq_list(a.else_body, b.else_body))
    if isinstance(a, WhileStmt):
        return _eq(a.condition, b.condition) and _eq_list(a.body, b.body)
    if isinstance(a, ForStmt):
        return (a.var == b.var and a.direction == b.direction and
                _eq(a.from_expr, b.from_expr) and _eq(a.to_expr, b.to_expr))
    if isinstance(a, DoStmt):
        return _eq(a.condition, b.condition) and _eq_list(a.body, b.body)
    if isinstance(a, CaseStmt):
        return (_eq(a.selector, b.selector) and a.is_labeled == b.is_labeled and
                len(a.alternatives) == len(b.alternatives))
    if isinstance(a, CaseAlternative):
        return (len(a.labels) == len(b.labels) and
                all(_eq_label(x, y) for x, y in zip(a.labels, b.labels)) and
                _eq_list(a.body, b.body))
    return a == b


def _eq_list(a: list, b: list) -> bool:
    return len(a) == len(b) and all(_eq(x, y) for x, y in zip(a, b))


def _eq_label(a: CaseLabel, b: CaseLabel) -> bool:
    return a.value == b.value and a.is_range == b.is_range and a.range_high == b.range_high


def _first(src: str):
    stmts = _parse(src)
    assert stmts, f"No statements parsed from: {src!r}"
    return stmts[0]


# ─────────────────────────────────────────────────────────────────────────────
# Grupo 1: IF
# ─────────────────────────────────────────────────────────────────────────────

def test_if_simple():
    s = _first("IF a < b THEN c := 1")
    assert isinstance(s, IfStmt)
    assert isinstance(s.condition, BinOpExpr) and s.condition.op == "<"
    assert len(s.then_body) == 1 and isinstance(s.then_body[0], AssignStmt)
    assert s.else_body == []

_run("test_if_simple", test_if_simple)


def test_if_else():
    s = _first("IF a < b THEN c := 1 ELSE c := 2")
    assert isinstance(s, IfStmt)
    assert len(s.then_body) == 1
    assert len(s.else_body) == 1
    assert isinstance(s.else_body[0], AssignStmt)

_run("test_if_else", test_if_else)


def test_if_nested_dangling_else():
    # IF a THEN IF b THEN s1 ELSE s2 → ELSE binds to inner IF
    s = _first("IF a THEN IF b THEN c := 1 ELSE c := 2")
    assert isinstance(s, IfStmt)
    assert s.else_body == []             # outer IF has no ELSE
    inner = s.then_body[0]
    assert isinstance(inner, IfStmt)
    assert len(inner.else_body) == 1     # inner IF has ELSE

_run("test_if_nested_dangling_else", test_if_nested_dangling_else)


def test_if_compound_bodies():
    s = _first("IF ok THEN BEGIN x := 1; y := 2; END ELSE BEGIN x := 3; END")
    assert isinstance(s, IfStmt)
    assert isinstance(s.then_body[0], CompoundStmt)
    assert len(s.then_body[0].body) == 2
    assert isinstance(s.else_body[0], CompoundStmt)

_run("test_if_compound_bodies", test_if_compound_bodies)


def test_if_condition_code():
    s = _first("IF < THEN GOTO err")
    assert isinstance(s, IfStmt)
    assert isinstance(s.condition, ConditionCodeExpr)
    assert s.condition.op == "<"

_run("test_if_condition_code", test_if_condition_code)


def test_if_and_condition():
    s = _first("IF (a < b) AND (c > d) THEN x := 1")
    assert isinstance(s, IfStmt)
    assert isinstance(s.condition, BinOpExpr) and s.condition.op == "AND"

_run("test_if_and_condition", test_if_and_condition)


def test_if_no_else_semicolon():
    stmts = _parse("IF a THEN x := 1; y := 2")
    assert len(stmts) == 2
    assert isinstance(stmts[0], IfStmt)
    assert isinstance(stmts[1], AssignStmt)

_run("test_if_no_else_semicolon", test_if_no_else_semicolon)


def test_if_nested_else_both():
    s = _first("IF a THEN c := 1 ELSE IF b THEN c := 2 ELSE c := 3")
    assert isinstance(s, IfStmt)
    assert len(s.else_body) == 1
    inner = s.else_body[0]
    assert isinstance(inner, IfStmt)
    assert len(inner.else_body) == 1

_run("test_if_nested_else_both", test_if_nested_else_both)


# ─────────────────────────────────────────────────────────────────────────────
# Grupo 2: WHILE
# ─────────────────────────────────────────────────────────────────────────────

def test_while_simple():
    s = _first("WHILE item < len DO item := item + 1")
    assert isinstance(s, WhileStmt)
    assert isinstance(s.condition, BinOpExpr) and s.condition.op == "<"
    assert len(s.body) == 1 and isinstance(s.body[0], AssignStmt)

_run("test_while_simple", test_while_simple)


def test_while_compound():
    s = _first("WHILE cond DO BEGIN x := x + 1; y := y - 1; END")
    assert isinstance(s, WhileStmt)
    assert isinstance(s.body[0], CompoundStmt)
    assert len(s.body[0].body) == 2

_run("test_while_compound", test_while_compound)


def test_while_condition_code():
    s = _first("WHILE > DO count := count + 1")
    assert isinstance(s, WhileStmt)
    assert isinstance(s.condition, ConditionCodeExpr)

_run("test_while_condition_code", test_while_condition_code)


def test_while_nested():
    s = _first("WHILE a DO WHILE b DO x := 1")
    assert isinstance(s, WhileStmt)
    inner = s.body[0]
    assert isinstance(inner, WhileStmt)

_run("test_while_nested", test_while_nested)


def test_while_followed_by_stmt():
    stmts = _parse("WHILE c DO x := 1; y := 2")
    assert len(stmts) == 2
    assert isinstance(stmts[0], WhileStmt)
    assert isinstance(stmts[1], AssignStmt)

_run("test_while_followed_by_stmt", test_while_followed_by_stmt)


# ─────────────────────────────────────────────────────────────────────────────
# Grupo 3: FOR
# ─────────────────────────────────────────────────────────────────────────────

def test_for_simple_to():
    s = _first("FOR i := 0 TO 9 DO arr := arr + 1")
    assert isinstance(s, ForStmt)
    assert s.var == "i"
    assert s.direction == "TO"
    assert _eq(s.from_expr, _lit(0))
    assert _eq(s.to_expr, _lit(9))
    assert s.step is None

_run("test_for_simple_to", test_for_simple_to)


def test_for_downto():
    s = _first("FOR i := 9 DOWNTO 0 DO x := x - 1")
    assert isinstance(s, ForStmt)
    assert s.var == "i"
    assert s.direction == "DOWNTO"
    assert _eq(s.from_expr, _lit(9))
    assert _eq(s.to_expr, _lit(0))

_run("test_for_downto", test_for_downto)


def test_for_by():
    s = _first("FOR i := 0 TO 100 BY 2 DO x := x + 1")
    assert isinstance(s, ForStmt)
    assert s.direction == "TO"
    assert s.step is not None
    assert _eq(s.step, _lit(2))

_run("test_for_by", test_for_by)


def test_for_step():
    s = _first("FOR i := 0 TO 100 STEP 5 DO x := x + 1")
    assert isinstance(s, ForStmt)
    assert s.step is not None
    assert _eq(s.step, _lit(5))

_run("test_for_step", test_for_step)


def test_for_nested():
    s = _first("FOR i := 0 TO 9 DO FOR j := 0 TO 9 DO x := x + 1")
    assert isinstance(s, ForStmt) and s.var == "i"
    inner = s.body[0]
    assert isinstance(inner, ForStmt) and inner.var == "j"

_run("test_for_nested", test_for_nested)


def test_for_compound():
    s = _first("FOR i := 0 TO 9 DO BEGIN arr := arr + 1; count := count + 1; END")
    assert isinstance(s, ForStmt)
    assert isinstance(s.body[0], CompoundStmt)
    assert len(s.body[0].body) == 2

_run("test_for_compound", test_for_compound)


def test_for_limit_expr():
    s = _first("FOR i := 0 TO len - 1 DO x := x + 1")
    assert isinstance(s, ForStmt)
    assert isinstance(s.to_expr, BinOpExpr) and s.to_expr.op == "-"

_run("test_for_limit_expr", test_for_limit_expr)


def test_for_negative_step():
    s = _first("FOR i := 100 TO 0 BY -1 DO x := x + 1")
    assert isinstance(s, ForStmt)
    assert s.step is not None
    assert isinstance(s.step, UnaryExpr) and s.step.op == "-"

_run("test_for_negative_step", test_for_negative_step)


def test_for_multiple_stmts():
    stmts = _parse("FOR i := 0 TO 9 DO x := 1; y := 2")
    assert len(stmts) == 2
    assert isinstance(stmts[0], ForStmt)
    assert isinstance(stmts[1], AssignStmt)

_run("test_for_multiple_stmts", test_for_multiple_stmts)


def test_for_downto_by():
    s = _first("FOR i := 10 DOWNTO 0 BY 2 DO x := x + i")
    assert isinstance(s, ForStmt)
    assert s.direction == "DOWNTO"
    assert s.step is not None

_run("test_for_downto_by", test_for_downto_by)


# ─────────────────────────────────────────────────────────────────────────────
# Grupo 4: DO...UNTIL
# ─────────────────────────────────────────────────────────────────────────────

def test_do_simple():
    s = _first("DO index := index + 1 UNTIL index > 10")
    assert isinstance(s, DoStmt)
    assert len(s.body) == 1 and isinstance(s.body[0], AssignStmt)
    assert isinstance(s.condition, BinOpExpr) and s.condition.op == ">"

_run("test_do_simple", test_do_simple)


def test_do_compound():
    s = _first("DO BEGIN a := a + 1; count := count - 1; END UNTIL count = 0")
    assert isinstance(s, DoStmt)
    assert isinstance(s.body[0], CompoundStmt)
    assert len(s.body[0].body) == 2

_run("test_do_compound", test_do_compound)


def test_do_nested():
    s = _first("DO DO x := x + 1 UNTIL x > 5 UNTIL done = 1")
    assert isinstance(s, DoStmt)
    assert isinstance(s.body[0], DoStmt)

_run("test_do_nested", test_do_nested)


def test_do_call_body():
    s = _first("DO CALL fetch UNTIL done = 1")
    assert isinstance(s, DoStmt)
    assert isinstance(s.body[0], CallStmt) and s.body[0].name == "fetch"

_run("test_do_call_body", test_do_call_body)


def test_do_in_while():
    s = _first("WHILE running DO DO count := count - 1 UNTIL count = 0")
    assert isinstance(s, WhileStmt)
    assert isinstance(s.body[0], DoStmt)

_run("test_do_in_while", test_do_in_while)


# ─────────────────────────────────────────────────────────────────────────────
# Grupo 5: CASE labeled
# ─────────────────────────────────────────────────────────────────────────────

def test_case_labeled_simple():
    s = _first("CASE x OF BEGIN 1 -> a := 10; 2 -> a := 20; END")
    assert isinstance(s, CaseStmt)
    assert s.is_labeled
    assert _eq(s.selector, _v("x"))
    assert len(s.alternatives) == 2
    alt0 = s.alternatives[0]
    assert _eq_label(alt0.labels[0], CaseLabel(value=1))
    assert isinstance(alt0.body[0], AssignStmt)

_run("test_case_labeled_simple", test_case_labeled_simple)


def test_case_labeled_multi_label():
    s = _first("CASE x OF BEGIN 408, 415 -> loc := 1; END")
    assert isinstance(s, CaseStmt) and s.is_labeled
    alt = s.alternatives[0]
    assert len(alt.labels) == 2
    assert alt.labels[0].value == 408
    assert alt.labels[1].value == 415

_run("test_case_labeled_multi_label", test_case_labeled_multi_label)


def test_case_labeled_range():
    s = _first("CASE x OF BEGIN 1..5 -> a := 1; END")
    assert isinstance(s, CaseStmt) and s.is_labeled
    lbl = s.alternatives[0].labels[0]
    assert lbl.is_range
    assert lbl.value == 1
    assert lbl.range_high == 5

_run("test_case_labeled_range", test_case_labeled_range)


def test_case_labeled_otherwise():
    s = _first("CASE x OF BEGIN 1 -> a := 1; END OTHERWISE -> a := 0")
    assert isinstance(s, CaseStmt) and s.is_labeled
    assert len(s.alternatives) == 1
    assert len(s.otherwise_body) == 1
    assert isinstance(s.otherwise_body[0], AssignStmt)

_run("test_case_labeled_otherwise", test_case_labeled_otherwise)


def test_case_labeled_negative():
    s = _first("CASE x OF BEGIN -1 -> a := -1; END")
    assert isinstance(s, CaseStmt) and s.is_labeled
    lbl = s.alternatives[0].labels[0]
    assert lbl.value == -1

_run("test_case_labeled_negative", test_case_labeled_negative)


def test_case_labeled_name_label():
    s = _first("CASE x OF BEGIN bay_area -> loc := 1; END")
    assert isinstance(s, CaseStmt) and s.is_labeled
    lbl = s.alternatives[0].labels[0]
    assert lbl.value == "bay_area"

_run("test_case_labeled_name_label", test_case_labeled_name_label)


def test_case_labeled_compound_alt():
    s = _first("CASE x OF BEGIN 1 -> BEGIN a := 1; b := 2; END; END")
    assert isinstance(s, CaseStmt) and s.is_labeled
    assert isinstance(s.alternatives[0].body[0], CompoundStmt)

_run("test_case_labeled_compound_alt", test_case_labeled_compound_alt)


def test_case_labeled_three_alts():
    s = _first("CASE x OF BEGIN 1 -> a := 1; 2 -> a := 2; 3 -> a := 3; END")
    assert isinstance(s, CaseStmt) and s.is_labeled
    assert len(s.alternatives) == 3

_run("test_case_labeled_three_alts", test_case_labeled_three_alts)


# ─────────────────────────────────────────────────────────────────────────────
# Grupo 6: CASE unlabeled
# ─────────────────────────────────────────────────────────────────────────────

def test_case_unlabeled_simple():
    # Unlabeled: items are keyword-started statements (IF/CALL) or assigns
    s = _first("CASE x OF BEGIN CALL proc_a; CALL proc_b; END")
    assert isinstance(s, CaseStmt)
    assert not s.is_labeled
    assert len(s.alternatives) == 2
    assert isinstance(s.alternatives[0].body[0], CallStmt)
    assert s.alternatives[0].labels[0].value == 0
    assert s.alternatives[1].labels[0].value == 1

_run("test_case_unlabeled_simple", test_case_unlabeled_simple)


def test_case_unlabeled_with_assign():
    # Single-target assigns in unlabeled CASE (no COMMA after NAME → no conflict)
    s = _first("CASE x OF BEGIN a := 0; END")
    assert isinstance(s, CaseStmt)
    assert not s.is_labeled
    assert len(s.alternatives) == 1
    assert isinstance(s.alternatives[0].body[0], AssignStmt)

_run("test_case_unlabeled_with_assign", test_case_unlabeled_with_assign)


def test_case_unlabeled_otherwise():
    s = _first("CASE x OF BEGIN CALL proc_a; END OTHERWISE a := -1")
    assert isinstance(s, CaseStmt) and not s.is_labeled
    assert len(s.alternatives) == 1
    assert len(s.otherwise_body) == 1

_run("test_case_unlabeled_otherwise", test_case_unlabeled_otherwise)


def test_case_empty():
    s = _first("CASE x OF BEGIN END")
    assert isinstance(s, CaseStmt)
    assert s.alternatives == []

_run("test_case_empty", test_case_empty)


def test_case_unlabeled_if_items():
    s = _first("CASE x OF BEGIN IF c THEN a := 1; IF c THEN a := 2; END")
    assert isinstance(s, CaseStmt) and not s.is_labeled
    assert len(s.alternatives) == 2
    assert isinstance(s.alternatives[0].body[0], IfStmt)

_run("test_case_unlabeled_if_items", test_case_unlabeled_if_items)


# ─────────────────────────────────────────────────────────────────────────────
# Grupo 7: CASE edge cases
# ─────────────────────────────────────────────────────────────────────────────

def test_case_single_alt():
    s = _first("CASE x OF BEGIN 42 -> a := 42; END")
    assert isinstance(s, CaseStmt) and s.is_labeled
    assert len(s.alternatives) == 1

_run("test_case_single_alt", test_case_single_alt)


def test_case_otherwise_only():
    s = _first("CASE x OF BEGIN END OTHERWISE a := -1")
    assert isinstance(s, CaseStmt)
    assert s.alternatives == []
    assert len(s.otherwise_body) == 1

_run("test_case_otherwise_only", test_case_otherwise_only)


def test_case_selector_expr():
    s = _first("CASE arr[i] OF BEGIN 1 -> a := 1; END")
    assert isinstance(s, CaseStmt)
    from segmsan.ast_nodes import IndexExpr
    assert isinstance(s.selector, IndexExpr)

_run("test_case_selector_expr", test_case_selector_expr)


def test_case_labeled_pos_range():
    # Positive ranges: grammar v3 supports NUMBER_INT DOT_DOT NUMBER_INT
    s = _first("CASE x OF BEGIN 1..5 -> a := 1; END")
    assert isinstance(s, CaseStmt) and s.is_labeled
    lbl = s.alternatives[0].labels[0]
    assert lbl.is_range
    assert lbl.value == 1
    assert lbl.range_high == 5

_run("test_case_labeled_pos_range", test_case_labeled_pos_range)


# ─────────────────────────────────────────────────────────────────────────────
# Grupo 8: Regression — Phase 6 statements still work with Phase 7 grammar
# ─────────────────────────────────────────────────────────────────────────────

def test_regression_assign():
    stmts = _parse("x := 1")
    assert len(stmts) == 1 and isinstance(stmts[0], AssignStmt)

_run("test_regression_assign", test_regression_assign)


def test_regression_call():
    stmts = _parse("CALL my_proc(a, b)")
    assert len(stmts) == 1 and isinstance(stmts[0], CallStmt)

_run("test_regression_call", test_regression_call)


def test_regression_return():
    stmts = _parse("RETURN 0")
    assert len(stmts) == 1 and isinstance(stmts[0], ReturnStmt)

_run("test_regression_return", test_regression_return)


def test_regression_compound():
    stmts = _parse("BEGIN x := 1; y := 2; END")
    assert len(stmts) == 1 and isinstance(stmts[0], CompoundStmt)

_run("test_regression_compound", test_regression_compound)


def test_regression_goto():
    stmts = _parse("GOTO done")
    assert len(stmts) == 1 and isinstance(stmts[0], GotoStmt)

_run("test_regression_goto", test_regression_goto)


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    total = len(_PASS) + len(_FAIL)
    print(f"\nPhase 7 results: {len(_PASS)}/{total} passed")
    if _FAIL:
        print(f"\nFAILED ({len(_FAIL)}):")
        for name, err in _FAIL:
            print(f"  {name}: {err}")
    else:
        print("All tests passed!")
