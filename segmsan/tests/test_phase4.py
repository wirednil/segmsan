"""Phase 4 tests: Expression parser (10 precedence levels) + constant evaluator."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from segmsan.lexer import Lexer
from segmsan.lexer import to_lark_stream
from segmsan.transformers.expr import parse_expr, eval_const_expr
from segmsan.transformers.var_decl import parse_var_decl
from segmsan.transformers.literal_decl import parse_literal_decl
from segmsan.ast_nodes import (
    Expr, LiteralExpr, VarExpr, BinOpExpr, UnaryExpr, BitExtractExpr,
    AssignExpr, IfExpr, CaseExpr, ConditionCodeExpr,
    FieldExpr, IndexExpr, AddressOfExpr, DollarFuncExpr,
    ArrayBounds,
)


def _parse(source: str) -> Expr:
    raw = Lexer(source).tokenize()
    return parse_expr(iter(list(to_lark_stream(raw))))


def _lit(v): return LiteralExpr(value=v)
def _var(n): return VarExpr(name=n)
def _bin(op, l, r): return BinOpExpr(op=op, left=l, right=r)


def _eq_expr(a: Expr, b: Expr) -> bool:
    """Structural equality ignoring SourceLocation."""
    if type(a) is not type(b):
        return False
    if isinstance(a, LiteralExpr):
        return a.value == b.value
    if isinstance(a, VarExpr):
        return a.name == b.name
    if isinstance(a, BinOpExpr):
        return a.op == b.op and _eq_expr(a.left, b.left) and _eq_expr(a.right, b.right)
    if isinstance(a, UnaryExpr):
        return a.op == b.op and _eq_expr(a.inner, b.inner)
    if isinstance(a, BitExtractExpr):
        return (a.left_bit == b.left_bit and a.right_bit == b.right_bit
                and _eq_expr(a.base, b.base))
    if isinstance(a, AssignExpr):
        return (_eq_expr(a.value, b.value)
                and len(a.targets) == len(b.targets)
                and all(_eq_expr(x, y) for x, y in zip(a.targets, b.targets)))
    if isinstance(a, IfExpr):
        return (_eq_expr(a.condition, b.condition)
                and _eq_expr(a.then_expr, b.then_expr)
                and _eq_expr(a.else_expr, b.else_expr))
    if isinstance(a, CaseExpr):
        ok = _eq_expr(a.selector, b.selector) and len(a.alternatives) == len(b.alternatives)
        ok = ok and all(_eq_expr(x, y) for x, y in zip(a.alternatives, b.alternatives))
        if a.otherwise is None:
            return ok and b.otherwise is None
        return ok and b.otherwise is not None and _eq_expr(a.otherwise, b.otherwise)
    if isinstance(a, ConditionCodeExpr):
        return a.op == b.op
    if isinstance(a, FieldExpr):
        return a.field_name == b.field_name and _eq_expr(a.obj, b.obj)
    if isinstance(a, IndexExpr):
        return _eq_expr(a.array, b.array) and _eq_expr(a.index, b.index)
    if isinstance(a, AddressOfExpr):
        return _eq_expr(a.inner, b.inner)
    if isinstance(a, DollarFuncExpr):
        return (a.name == b.name and len(a.args) == len(b.args)
                and all(_eq_expr(x, y) for x, y in zip(a.args, b.args)))
    return a == b


def _assert_eq(actual: Expr, expected: Expr):
    assert _eq_expr(actual, expected), f"\nActual:   {actual}\nExpected: {expected}"


# ---------------------------------------------------------------------------
# Grupo 1 — Literales y primarias
# ---------------------------------------------------------------------------

def test_lit_int():
    _assert_eq(_parse("42"), _lit(42))

def test_lit_int_octal():
    _assert_eq(_parse("%1000"), _lit(0o1000))   # 512

def test_lit_int_hex():
    _assert_eq(_parse("%HFF"), _lit(0xFF))       # 255

def test_lit_int_binary():
    _assert_eq(_parse("%B1010"), _lit(0b1010))   # 10

def test_lit_int32():
    _assert_eq(_parse("14769D"), _lit(14769))

def test_lit_fixed():
    _assert_eq(_parse("1200F"), _lit(1200))

def test_lit_negative():
    _assert_eq(_parse("-1"), UnaryExpr(op="-", inner=_lit(1)))

def test_var_ref():
    _assert_eq(_parse("x"), _var("x"))

def test_var_ref_caret():
    _assert_eq(_parse("my^var"), _var("my^var"))

def test_address_of():
    _assert_eq(_parse("@x"), AddressOfExpr(inner=_var("x")))

def test_dollar_func_no_args():
    e = _parse("$CARRY")
    assert isinstance(e, DollarFuncExpr)
    assert e.name == "CARRY"
    assert e.args == []

def test_dollar_func_args():
    e = _parse("$LEN(arr)")
    assert isinstance(e, DollarFuncExpr)
    assert e.name == "LEN"
    assert len(e.args) == 1
    assert isinstance(e.args[0], VarExpr)

def test_paren_expr():
    _assert_eq(_parse("(x + 1)"), _bin("+", _var("x"), _lit(1)))


# ---------------------------------------------------------------------------
# Grupo 2 — Postfix (field access, index, bit extract)
# ---------------------------------------------------------------------------

def test_field_access():
    e = _parse("rec.field")
    assert isinstance(e, FieldExpr)
    assert e.field_name == "field"
    assert _eq_expr(e.obj, _var("rec"))

def test_index_access():
    e = _parse("arr[i]")
    assert isinstance(e, IndexExpr)
    assert _eq_expr(e.array, _var("arr"))
    assert _eq_expr(e.index, _var("i"))

def test_chained_postfix():
    # arr[i].field  →  FieldExpr(IndexExpr(arr, i), "field")
    e = _parse("arr[i].field")
    assert isinstance(e, FieldExpr)
    assert e.field_name == "field"
    assert isinstance(e.obj, IndexExpr)

def test_bit_extract_single():
    e = _parse("x.<15>")
    assert isinstance(e, BitExtractExpr)
    assert e.left_bit == 15
    assert e.right_bit == 15

def test_bit_extract_range():
    e = _parse("x.<4:7>")
    assert isinstance(e, BitExtractExpr)
    assert e.left_bit == 4
    assert e.right_bit == 7

def test_bit_extract_on_expr():
    e = _parse("(a + b).<8:15>")
    assert isinstance(e, BitExtractExpr)
    assert isinstance(e.base, BinOpExpr)
    assert e.left_bit == 8
    assert e.right_bit == 15

def test_deep_postfix_chain():
    # arr[i].sub[j].<0:7>
    e = _parse("arr[i].sub[j].<0:7>")
    assert isinstance(e, BitExtractExpr)


# ---------------------------------------------------------------------------
# Grupo 3 — Bit shifts (nivel 2)
# ---------------------------------------------------------------------------

def test_shift_left():
    _assert_eq(_parse("a << 3"), _bin("<<", _var("a"), _lit(3)))

def test_shift_right():
    _assert_eq(_parse("b >> 2"), _bin(">>", _var("b"), _lit(2)))

def test_unsigned_shift_left():
    _assert_eq(_parse("a '<<' 3"), _bin("'<<'", _var("a"), _lit(3)))

def test_unsigned_shift_right():
    _assert_eq(_parse("b '>>' 2"), _bin("'>>'", _var("b"), _lit(2)))

def test_shift_binds_tighter_than_add():
    # a << 1 + b  →  (a << 1) + b  (shift is level 2, add is level 4)
    e = _parse("a << 1 + b")
    assert isinstance(e, BinOpExpr) and e.op == "+"
    assert isinstance(e.left, BinOpExpr) and e.left.op == "<<"


# ---------------------------------------------------------------------------
# Grupo 4 — Multiplicativo (nivel 3)
# ---------------------------------------------------------------------------

def test_mul():
    _assert_eq(_parse("a * b"), _bin("*", _var("a"), _var("b")))

def test_div():
    _assert_eq(_parse("a / b"), _bin("/", _var("a"), _var("b")))

def test_unsigned_mul():
    _assert_eq(_parse("a '*' b"), _bin("'*'", _var("a"), _var("b")))

def test_unsigned_div():
    _assert_eq(_parse("a '/' b"), _bin("'/'", _var("a"), _var("b")))

def test_unsigned_mod():
    _assert_eq(_parse("a '\\' b"), _bin("'\\'" , _var("a"), _var("b")))

def test_mul_precedence():
    # a + b * c  →  a + (b * c)
    e = _parse("a + b * c")
    assert isinstance(e, BinOpExpr) and e.op == "+"
    assert isinstance(e.right, BinOpExpr) and e.right.op == "*"


# ---------------------------------------------------------------------------
# Grupo 5 — Aditivo + Bitwise (nivel 4)
# ---------------------------------------------------------------------------

def test_add():
    _assert_eq(_parse("a + b"), _bin("+", _var("a"), _var("b")))

def test_sub():
    _assert_eq(_parse("a - b"), _bin("-", _var("a"), _var("b")))

def test_unsigned_add():
    _assert_eq(_parse("a '+' b"), _bin("'+'", _var("a"), _var("b")))

def test_unsigned_sub():
    _assert_eq(_parse("a '-' b"), _bin("'-'", _var("a"), _var("b")))

def test_lor():
    _assert_eq(_parse("a LOR b"), _bin("LOR", _var("a"), _var("b")))

def test_land():
    _assert_eq(_parse("a LAND b"), _bin("LAND", _var("a"), _var("b")))

def test_xor():
    _assert_eq(_parse("a XOR b"), _bin("XOR", _var("a"), _var("b")))

def test_lor_same_precedence_as_add():
    # a + b LOR c  →  (a + b) LOR c  (left-associative at level 4)
    e = _parse("a + b LOR c")
    assert e.op == "LOR"
    assert isinstance(e.left, BinOpExpr) and e.left.op == "+"

def test_add_left_assoc():
    # a - b + c  →  (a - b) + c
    e = _parse("a - b + c")
    assert e.op == "+"
    assert isinstance(e.left, BinOpExpr) and e.left.op == "-"


# ---------------------------------------------------------------------------
# Grupo 6 — Comparación (nivel 5)
# ---------------------------------------------------------------------------

def test_lt():
    _assert_eq(_parse("a < b"), _bin("<", _var("a"), _var("b")))

def test_eq():
    _assert_eq(_parse("a = b"), _bin("=", _var("a"), _var("b")))

def test_neq():
    _assert_eq(_parse("a <> b"), _bin("<>", _var("a"), _var("b")))

def test_unsigned_lt():
    _assert_eq(_parse("a '<' b"), _bin("'<'", _var("a"), _var("b")))

def test_unsigned_eq():
    _assert_eq(_parse("a '=' b"), _bin("'='", _var("a"), _var("b")))

def test_cmp_precedence():
    # a + b < c  →  (a + b) < c
    e = _parse("a + b < c")
    assert e.op == "<"
    assert isinstance(e.left, BinOpExpr) and e.left.op == "+"

def test_condition_code_lt():
    _assert_eq(_parse("<"), ConditionCodeExpr(op="<"))

def test_condition_code_ge():
    _assert_eq(_parse(">="), ConditionCodeExpr(op=">="))


# ---------------------------------------------------------------------------
# Grupo 7 — Booleanos (niveles 6-8)
# ---------------------------------------------------------------------------

def test_not():
    e = _parse("NOT a")
    assert isinstance(e, UnaryExpr) and e.op == "NOT"

def test_and():
    _assert_eq(_parse("a AND b"), _bin("AND", _var("a"), _var("b")))

def test_or():
    _assert_eq(_parse("a OR b"), _bin("OR", _var("a"), _var("b")))

def test_not_precedence():
    # NOT a AND b  →  (NOT a) AND b
    e = _parse("NOT a AND b")
    assert e.op == "AND"
    assert isinstance(e.left, UnaryExpr) and e.left.op == "NOT"

def test_and_precedence():
    # a AND b OR c  →  (a AND b) OR c
    e = _parse("a AND b OR c")
    assert e.op == "OR"
    assert isinstance(e.left, BinOpExpr) and e.left.op == "AND"

def test_lor_vs_or_different_levels():
    # LOR is level 4 (with +), OR is level 8 — LOR binds tighter
    # a + b LOR c OR d  →  ((a+b) LOR c) OR d
    e = _parse("a + b LOR c OR d")
    assert e.op == "OR"
    assert e.left.op == "LOR"
    assert e.left.left.op == "+"


# ---------------------------------------------------------------------------
# Grupo 8 — Assignment expression (nivel 9)
# ---------------------------------------------------------------------------

def test_assign_expr():
    e = _parse("(a := b)")
    assert isinstance(e, AssignExpr)
    assert len(e.targets) == 1
    assert _eq_expr(e.targets[0], _var("a"))
    assert _eq_expr(e.value, _var("b"))

def test_assign_chain():
    # (a := b := 0)  — right-associative
    e = _parse("(a := b := 0)")
    assert isinstance(e, AssignExpr)
    assert isinstance(e.value, AssignExpr)

def test_assign_in_index():
    # arr[a := a - 1]
    e = _parse("arr[a := a - 1]")
    assert isinstance(e, IndexExpr)
    assert isinstance(e.index, AssignExpr)


# ---------------------------------------------------------------------------
# Grupo 9 — IF expression
# ---------------------------------------------------------------------------

def test_if_expr():
    e = _parse("IF x > 0 THEN x ELSE 0 - x")
    assert isinstance(e, IfExpr)
    assert isinstance(e.condition, BinOpExpr) and e.condition.op == ">"
    assert _eq_expr(e.then_expr, _var("x"))

def test_if_expr_in_assign():
    e = _parse("(v := IF length > 0 THEN 10 ELSE 20)")
    assert isinstance(e, AssignExpr)
    assert isinstance(e.value, IfExpr)

def test_if_expr_in_arithmetic():
    e = _parse("x + (IF a THEN 1 ELSE 2)")
    assert isinstance(e, BinOpExpr) and e.op == "+"
    assert isinstance(e.right, IfExpr)


# ---------------------------------------------------------------------------
# Grupo 10 — CASE expression
# ---------------------------------------------------------------------------

def test_case_expr():
    e = _parse("CASE a OF BEGIN 10; 20; OTHERWISE 0; END")
    assert isinstance(e, CaseExpr)
    assert _eq_expr(e.selector, _var("a"))
    assert len(e.alternatives) == 2
    assert e.otherwise is not None

def test_case_expr_no_otherwise():
    e = _parse("CASE a OF BEGIN 10; 20; END")
    assert isinstance(e, CaseExpr)
    assert e.otherwise is None

def test_case_expr_in_assign():
    e = _parse("(x := CASE a OF BEGIN 10; 20; END)")
    assert isinstance(e, AssignExpr)
    assert isinstance(e.value, CaseExpr)


# ---------------------------------------------------------------------------
# Grupo 11 — Expresiones compuestas
# ---------------------------------------------------------------------------

def test_mixed_signed_unsigned():
    # a + b '*' c  →  a + (b '*' c)  (unsigned mul binds tighter)
    e = _parse("a + b '*' c")
    assert e.op == "+"
    assert e.right.op == "'*'"

def test_dollar_func_in_expr():
    e = _parse("$LEN(arr) + 1")
    assert isinstance(e, BinOpExpr) and e.op == "+"
    assert isinstance(e.left, DollarFuncExpr)

def test_base_address_indexed():
    # 'G'[100]  →  IndexExpr(VarExpr("'G'"), LiteralExpr(100))
    e = _parse("'G'[100]")
    assert isinstance(e, IndexExpr)
    assert isinstance(e.array, VarExpr) and e.array.name == "'G'"
    assert _eq_expr(e.index, _lit(100))

def test_full_precedence_chain():
    # a OR b AND NOT c < d + e * f >> 3
    # Parses without error and produces a tree
    e = _parse("a OR b AND NOT c < d + e * f >> 3")
    assert isinstance(e, BinOpExpr) and e.op == "OR"

def test_nested_if_expr():
    # IF a THEN b ELSE IF c THEN d ELSE e
    e = _parse("IF a THEN b ELSE IF c THEN d ELSE e")
    assert isinstance(e, IfExpr)
    assert isinstance(e.else_expr, IfExpr)


# ---------------------------------------------------------------------------
# Grupo 12 — Constant evaluator
# ---------------------------------------------------------------------------

def test_eval_literal_int():
    assert eval_const_expr(_lit(5), {}) == 5

def test_eval_literal_zero():
    assert eval_const_expr(_lit(0), {}) == 0

def test_eval_var_in_literals():
    assert eval_const_expr(_var("N"), {"N": 10}) == 10

def test_eval_var_uppercase():
    assert eval_const_expr(_var("max_len"), {"MAX_LEN": 80}) == 80

def test_eval_var_missing():
    assert eval_const_expr(_var("x"), {}) is None

def test_eval_binop_add():
    assert eval_const_expr(_bin("+", _lit(3), _lit(4)), {}) == 7

def test_eval_binop_sub():
    assert eval_const_expr(_bin("-", _lit(10), _lit(3)), {}) == 7

def test_eval_binop_mul():
    assert eval_const_expr(_bin("*", _lit(3), _lit(4)), {}) == 12

def test_eval_binop_div():
    assert eval_const_expr(_bin("/", _lit(10), _lit(3)), {}) == 3

def test_eval_binop_lor():
    assert eval_const_expr(_bin("LOR", _lit(0xFF), _lit(0x0F)), {}) == 0xFF

def test_eval_binop_land():
    assert eval_const_expr(_bin("LAND", _lit(0xFF), _lit(0x0F)), {}) == 0x0F

def test_eval_binop_xor():
    assert eval_const_expr(_bin("XOR", _lit(0xFF), _lit(0x0F)), {}) == 0xF0

def test_eval_binop_shl():
    assert eval_const_expr(_bin("<<", _lit(1), _lit(3)), {}) == 8

def test_eval_unary_minus():
    assert eval_const_expr(UnaryExpr(op="-", inner=_lit(7)), {}) == -7

def test_eval_unary_plus():
    assert eval_const_expr(UnaryExpr(op="+", inner=_lit(7)), {}) == 7

def test_eval_complex_expr():
    # a + b * 2 where a=3, b=4 → 3 + 4*2 = 11
    e = _parse("a + b * 2")
    assert eval_const_expr(e, {"A": 3, "B": 4}) == 11

def test_eval_non_const_var():
    assert eval_const_expr(_var("x"), {}) is None

def test_eval_non_const_with_non_evaluable():
    # a + non_existent → None (non_existent not in literals)
    e = _bin("+", _lit(1), _var("MISSING"))
    assert eval_const_expr(e, {}) is None

def test_eval_literal_expr_not_int():
    # Real literal stored as string → not int → None
    e = LiteralExpr(value="2.0E0")
    assert eval_const_expr(e, {}) is None


# ─────────────────────────────────────────────────────────────────────────────
# Grupo 13 — bound_expr arithmetic (var_decl cross-phase)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_var(source: str):
    raw = Lexer(source).tokenize()
    return parse_var_decl(iter(list(to_lark_stream(raw))))


def test_bound_simple():
    decls = _parse_var("INT a[0:9];")
    assert decls[0].array_bounds == ArrayBounds(lo=0, hi=9)

def test_bound_arith_add():
    decls = _parse_var("INT a[0:5+3];")
    assert decls[0].array_bounds == ArrayBounds(lo=0, hi=8)

def test_bound_arith_sub():
    decls = _parse_var("INT a[0:10-1];")
    assert decls[0].array_bounds == ArrayBounds(lo=0, hi=9)

def test_bound_arith_mul():
    decls = _parse_var("INT a[0:10*2];")
    assert decls[0].array_bounds == ArrayBounds(lo=0, hi=20)

def test_bound_arith_div():
    decls = _parse_var("INT a[0:10/2];")
    assert decls[0].array_bounds == ArrayBounds(lo=0, hi=5)

def test_bound_arith_compound():
    # 10*2-1 = 19 (operator precedence: mul before sub)
    decls = _parse_var("INT a[0:10*2-1];")
    assert decls[0].array_bounds == ArrayBounds(lo=0, hi=19)

def test_bound_arith_paren():
    # (5+3)*2 = 16
    decls = _parse_var("INT a[0:(5+3)*2];")
    assert decls[0].array_bounds == ArrayBounds(lo=0, hi=16)

def test_bound_negative_lo():
    # Negative lower bound
    decls = _parse_var("INT a[-5:5];")
    assert decls[0].array_bounds == ArrayBounds(lo=-5, hi=5)

def test_bound_name_unresolvable():
    # NAME in Phase 1 → 0 (no literals dict available)
    decls = _parse_var("INT a[0:size];")
    assert decls[0].array_bounds == ArrayBounds(lo=0, hi=0)

def test_bound_div_zero():
    # Division by zero → 0 fallback
    decls = _parse_var("INT a[0:10/0];")
    assert decls[0].array_bounds == ArrayBounds(lo=0, hi=0)

def test_bound_both_arith():
    # Both lo and hi are arithmetic
    decls = _parse_var("INT a[1*2:3+4*2];")
    assert decls[0].array_bounds == ArrayBounds(lo=2, hi=11)


# ─────────────────────────────────────────────────────────────────────────────
# Grupo 14 — literal_value arithmetic (literal_decl cross-phase)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_lit(source: str):
    raw = Lexer(source).tokenize()
    return parse_literal_decl(iter(list(to_lark_stream(raw))))


def test_literal_arith_add():
    pairs = _parse_lit("LITERAL x = 3 + 7;")
    assert pairs == [("X", 10)]

def test_literal_arith_sub():
    pairs = _parse_lit("LITERAL x = 10 - 3;")
    assert pairs == [("X", 7)]

def test_literal_arith_mul():
    pairs = _parse_lit("LITERAL x = 10 * 4;")
    assert pairs == [("X", 40)]

def test_literal_arith_div():
    pairs = _parse_lit("LITERAL x = 10 / 3;")
    assert pairs == [("X", 3)]

def test_literal_arith_compound():
    # 2 + 3 * 4 = 14 (mul before add)
    pairs = _parse_lit("LITERAL x = 2 + 3 * 4;")
    assert pairs == [("X", 14)]

def test_literal_arith_paren():
    # (2 + 3) * 4 = 20
    pairs = _parse_lit("LITERAL x = (2 + 3) * 4;")
    assert pairs == [("X", 20)]

def test_literal_arith_unary_neg():
    # -10 + 3 = -7
    pairs = _parse_lit("LITERAL x = -10 + 3;")
    assert pairs == [("X", -7)]

def test_literal_cross_ref_single():
    # b = a + 5 where a = 10
    pairs = _parse_lit("LITERAL a = 10, b = a + 5;")
    assert pairs == [("A", 10), ("B", 15)]

def test_literal_cross_ref_chain():
    # a=2, b=a*3=6, c=b+a=8
    pairs = _parse_lit("LITERAL a = 2, b = a * 3, c = b + a;")
    assert pairs == [("A", 2), ("B", 6), ("C", 8)]

def test_literal_cross_ref_unresolvable():
    # x references unknown name → eval_const_expr returns None → fallback 0
    pairs = _parse_lit("LITERAL x = unknown + 1;")
    assert pairs == [("X", 0)]

def test_literal_arith_preserves_plain():
    # Plain integer literals still work after grammar change
    pairs = _parse_lit("LITERAL a = 5, b = -1, c = %HFF;")
    assert pairs == [("A", 5), ("B", -1), ("C", 255)]


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  OK  {fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"FAIL  {fn.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
